"""Record REAL engine output so the frontend can run with no backend.

Runs the production engine and simulator offline and saves everything the dashboard asks the API for:
a live stream with attacks embedded, an attack library (the "Launch attack" menu), a festival-surge segment,
drift readings for both traffic regimes, a grid of policy-lab results and the model card.
Playground scenarios are captured separately by tools/capture_scenarios.py (they need the UI).

    python tools/build_demo.py        -> dist/demo-data.json
"""
import heapq
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fh import api, drift, policy, whatif, train, backtest, sample   # noqa: E402
from fh.gen import T0, DAY, TYPS                           # noqa: E402
from fh.sim import Sim                                     # noqa: E402

g, w, rep, hold, eng = api.load()
sim = Sim(eng, w, T0 + train.DAYS * DAY, seed=2026)
cases, t0 = {}, time.time()


def step(sec=30):
    sim.clk += sec
    sim.refill()
    out = []
    while sim.hp and sim.hp[0][0] <= sim.clk:
        out.append(sim.proc(heapq.heappop(sim.hp)[2]))
    return out


def keep(msgs):
    for m in msgs:
        cases[m["id"]] = dict(eng.cases[m["id"]], truth=sim.truth[m["id"]])
    return msgs


def run(n, every=None, kinds=()):
    """Process n events; optionally inject an attack every `every` events. Returns recorded messages."""
    got, k = [], 0
    while len(got) < n:
        for m in step():
            got.append(m)
        if every and len(got) >= (k + 1) * every and kinds:
            sim.attack(kinds[k % len(kinds)])
            k += 1
    return keep(got[:n])


def silent(n):
    c = 0
    while c < n:
        c += len(step())


print("warming up on normal traffic ...")
silent(4300)
drift_normal = drift.psi(eng.vecs, g, rep, api.DESC)

print("recording the live stream (with attacks) ...")
story = ["upi_scam", "vishing", "sim_swap", "ato", "card_test", "travel", "mule", "vishing", "upi_scam", "sim_swap"]
base = run(520, every=48, kinds=story)

print("recording the attack library ...")
lib = {}
for kind in TYPS:
    lib[kind] = []
    for _ in range(3):
        evs = w.fraud(sim.r, kind, sim.clk + 1.0)
        sim.push(evs)
        tmax, got = max(e["ts"] for e in evs), []
        while sim.clk < tmax + 5:
            got += step(10)
        lib[kind].append(keep(got))

print("recording festival surge ...")
w.fest = 2.5
silent(4300)
drift_fest = drift.psi(eng.vecs, g, rep, api.DESC)
fest = run(260)
w.fest = 1.0

print("computing the policy-lab grid ...")
labs = {}
for risk in (0.25, 0.5, 1.0, 2.0, 4.0):
    for churn in (150, 400, 1000):
        for stp in (5, 15, 40):
            labs["%g|%g|%g" % (risk, churn, stp)] = whatif.lab(hold, policy.Cfg(risk=risk, churn=churn, step=stp))

print("running the sample backtest ...")
bt, _ = backtest.run(backtest.parse(sample.sample_csv())[0], g, policy.Cfg())
bt.update(problems=[], model=api.model_version(), id="sample", sample=True)

rt = json.load(open(os.path.join(ROOT, "docs", "redteam.json")))
redteam_data = dict(rounds=rt, run=dict(rt["rounds"][0], model=api.model_version()))

shapes = [dict(f=n, desc=api.DESC.get(n, ""), edges=g.el[j], v=g.sl[j]) for j, n in enumerate(g.names)]
data = dict(
    redteam=redteam_data, backtest=bt, base=base, lib=lib, fest=fest, cases=cases, labs=labs, drift=dict(normal=drift_normal, fest=drift_fest),
    model=dict(rep={k: v for k, v in rep.items() if k != "ref"}, shapes=shapes, b0=g.b0, nfeat=len(g.names)),
    meta=dict(cities=[c[0] for c in api.CITY], nin=api.NIN, cats=sorted(api.CATS), kinds=TYPS, cfg=policy.Cfg().dict(), start=T0 + train.DAYS * DAY, fest=1.0),
    cfg=policy.Cfg().dict(), start=T0 + train.DAYS * DAY,
)
os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
out = os.path.join(ROOT, "dist", "demo-data.json")
json.dump(data, open(out, "w"), separators=(",", ":"), default=float)
print("wrote %s  %.1f MB  | %d base events, %d library episodes, %d festival, %d cases, %d labs  [%.0fs]" % (
    out, os.path.getsize(out) / 1e6, len(base), sum(len(v) for v in lib.values()), len(fest), len(cases), len(labs), time.time() - t0))
