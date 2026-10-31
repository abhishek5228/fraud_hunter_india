"""Red team: let an automated fraudster attack the engine, find what slips through, then harden the engine against it.

An attack is a *genome*: a handful of levers a real fraudster controls (which rail, how many payments, how much,
whether to split under a limit, which kind of payee, which device and network, whether a screen-share app is
visible, what hour, how fast, and whether the customer is tricked into approving a challenge). An evolutionary search
tries thousands of genomes against sandboxed copies of real customers' state, scored by the *production engine*, and
keeps whatever extracts the most rupees.

    python -m fh.redteam                  # attack the shipped model, print what works
    python -m fh.redteam --harden 3       # attack, train on what was found, attack again (3 rounds)

What this is and is not: a search over a fixed menu of levers, against a simulator. It finds holes in the model it is
given and shows whether a patch closes *those* holes. It does not prove robustness against an attacker with levers
this menu does not have.
"""
import argparse
import copy
import json
import os
import random
import sys
import time

from . import feat, policy
from .engine import Engine
from .gen import CAP, LIM, T0, DAY, IST
from .geo import CITY, NIN

LEVERS = dict(
    rail=["upi", "imps"],
    n=[1, 2, 3, 4, 6, 8],
    mult=[0.5, 1, 2, 4, 8, 15, 30, 60],        # total, as a multiple of the victim's usual ticket
    split=["equal", "random", "limit"],         # 'limit' = every payment just under Rs 50,000
    payee=["pool", "fresh", "merchant", "contact"],
    dev=["own", "new"],
    ip=["home", "proxy", "foreign"],
    rat=[0, 1],                                  # is a screen-share app visible to the bank
    sim=[0, 1],                                  # did the fraudster just swap the SIM
    hour=list(range(24)),
    gap=[20, 60, 300, 1800, 7200],               # seconds between payments
    social=[0, 1],                               # does the customer approve a challenge themselves
)

WORDS = dict(
    payee=dict(pool="a rented mule account other victims also pay", fresh="a brand-new account", merchant="a gift-card merchant", contact="one of the victim's saved contacts"),
    dev=dict(own="the victim's own phone", new="a new phone"),
    ip=dict(home="the victim's usual network", proxy="a proxy in the victim's city", foreign="a foreign network"),
    split=dict(equal="equal parts", random="uneven parts", limit="parts just under the Rs 50,000 limit"),
)


def norm(g):
    """Drop levers that cannot matter, so identical attacks are not counted twice."""
    g = dict(g)
    if g["n"] == 1:
        g["split"] = "equal"
    if g["split"] == "limit":
        g["mult"] = 0
    return g


def random_genome(rng):
    return norm({k: rng.choice(v) for k, v in LEVERS.items()})


def mutate(g, rng, k=None):
    g = dict(g)
    for key in rng.sample(list(LEVERS), k or rng.choice((1, 1, 2, 3))):
        g[key] = rng.choice(LEVERS[key])
    return norm(g)


def cross(a, b, rng):
    return norm({k: (a if rng.random() < 0.5 else b)[k] for k in LEVERS})


def key(g):
    return tuple(g[k] for k in LEVERS)


def describe(g):
    rail = "UPI" if g["rail"] == "upi" else "IMPS"
    t = ["%d %s payment%s%s" % (g["n"], rail, "" if g["n"] == 1 else "s", (" in " + WORDS["split"][g["split"]]) if g["n"] > 1 else "")]
    if g["split"] != "limit":
        t.append("totalling about %sx the victim's usual ticket" % g["mult"])
    t.append("to " + WORDS["payee"][g["payee"]])
    t.append("from " + WORDS["dev"][g["dev"]] + " on " + WORDS["ip"][g["ip"]])
    t.append("around %02d:00 IST, %s apart" % (g["hour"], "%ds" % g["gap"] if g["gap"] < 300 else "%d min" % (g["gap"] // 60)))
    f = []
    if not g["rat"]:
        f.append("no screen-share visible")
    if g["sim"]:
        f.append("right after a SIM swap")
    if g["social"]:
        f.append("customer completes the OTP")
    return ", ".join(t) + (" (" + ", ".join(f) + ")" if f else "")


def build(w, u, day_ts, g, rng):
    """Turn a genome into concrete payment events against one real customer."""
    mean = w.mean(u)
    ch, n = g["rail"], g["n"]
    if g["split"] == "limit":
        amts = [LIM[0] * rng.uniform(0.95, 0.995) for _ in range(n)]
    else:
        tot = mean * g["mult"]
        if g["split"] == "equal":
            amts = [tot / n] * n
        else:
            cut = [rng.random() + 0.2 for _ in range(n)]
            amts = [tot * c / sum(cut) for c in cut]
    amts = [min(a, CAP[ch]) for a in amts]
    foreign = g["ip"] == "foreign"
    ci = rng.choice([c for c in range(len(CITY)) if c != u["hc"]]) if foreign else u["hc"]
    ip = ("%d.%d.%d" % (rng.choice((45, 91, 103, 178, 194)), rng.randrange(256), rng.randrange(256)) if foreign else
          "%d.%d.%d" % (210 + u["hc"], rng.randrange(256), rng.randrange(256)) if g["ip"] == "proxy" else rng.choice(u["ips"])) + ".%d" % rng.randrange(1, 255)
    dev = rng.choice(u["devs"]) if g["dev"] == "own" else "dn%06d" % rng.randrange(10 ** 6)
    pay, cat, pers = None, ("bank_transfer" if ch == "imps" else "p2p"), True
    if g["payee"] == "pool":
        pay = rng.choice(w.mp)
    elif g["payee"] == "fresh":
        pay = "s%06d@ybl" % rng.randrange(10 ** 6)
    elif g["payee"] == "contact":
        pay = u["ct"][0]
    else:
        m = w.mers[rng.choice([k for k in w.onl if w.mers[k]["cat"] == "gift_cards"] or w.onl)]
        pay, cat, pers = m["mid"], m["cat"], False
    t = day_ts + g["hour"] * 3600 + rng.uniform(0, 3600)
    out = []
    for a in amts:
        e = w.mk(rng, t, u["uid"], dict(mid=pay, cat=cat), a, ch, dev, ip, ci, 1, "evasive", pers=pers, rat=bool(g["rat"]),
                 sim=(3.0 if g["sim"] else 1e4), app=bool(g["social"]))
        out.append(e)
        t += g["gap"] * rng.uniform(0.8, 1.2)
    return out


def sandbox(st, uid, evs):
    """A private copy of just the state this attack can see or change, so thousands of attacks never touch the real store."""
    for _ in range(6):
        try:
            s = feat.Store()
            if uid in st.u:
                s.u[uid] = copy.deepcopy(st.u[uid])
            for e in evs:
                if e["dev"] and e["dev"] in st.du:
                    s.du[e["dev"]] = dict(st.du[e["dev"]])
                ip = feat.ip24(e["ip"])
                if ip and ip in st.iu:
                    s.iu[ip] = dict(st.iu[ip])
                if e["pers"] and e["mid"] in st.pu:
                    s.pu[e["mid"]] = dict(st.pu[e["mid"]])
            s.pf, s.bad, s.blk = set(st.pf), st.bad, st.blk      # read-only here
            return s
        except RuntimeError:      # the live store changed size while we copied it (the simulator runs in another thread): retry
            continue
    raise RuntimeError("could not snapshot customer state")


SOCIAL_PASS = 0.5     # a tricked customer completes a challenge about half the time (see fh/sim.py: 0.45 to 0.6)


def attack(model, st, cfg, evs):
    """Play one attack through the engine. Returns (expected rupees extracted, rupees attempted, payments stopped).
    A challenge is a barrier, not a wall: it lets through cfg.fpass of ordinary fraud and SOCIAL_PASS of fraud the
    customer is tricked into, so the money counted is an expectation, not a coin flip."""
    eng = Engine(model, sandbox(st, evs[0]["uid"], evs), cfg, keep=1)
    got = tried = stopped = 0.0
    for e in evs:
        e = dict(e, id="r")
        res = eng.score(e, commit=False)
        tried += e["amt"]
        dec, social = res["dec"], bool(e["app"])
        keep = 1.0 if dec == 0 else (SOCIAL_PASS if social else cfg.fpass) if dec == 1 else 0.0
        got += keep * e["amt"]
        stopped += 1 if dec == 2 else 0
        eng.st.commit(e, upd=dec == 0 or (dec == 1 and social))
    return got, tried, stopped


def fitness(model, st, cfg, w, g, victims, day_ts, seed):
    got = tried = 0.0
    caught = 0
    for i, u in enumerate(victims):
        evs = build(w, u, day_ts, g, random.Random(seed * 7919 + i))
        a, b, s = attack(model, st, cfg, evs)
        got += a
        tried += b
        caught += 1 if a < 0.25 * b else 0
    n = len(victims)
    return dict(got=got / n, frac=got / max(tried, 1), caught=caught / n)


def pick_victims(w, st, k, rng):
    """Established customers: the ones whose history the engine judges payments against."""
    pool = [u for u in w.users if u["uid"] in st.u and st.u[u["uid"]].n >= 20]
    return rng.sample(pool, min(k, len(pool)))


def search(model, st, w, cfg=None, seed=1, pop=36, gens=10, k=14, day_ts=None, progress=None):
    cfg = cfg or policy.Cfg()
    rng = random.Random(seed)
    day_ts = day_ts or (T0 + 42 * DAY)
    P = [random_genome(rng) for _ in range(pop)]
    seen, hist, curve, t0 = {}, [], [], time.time()
    for gen in range(gens):
        vic = pick_victims(w, st, k, rng)
        sc = []
        for g in P:
            f = fitness(model, st, cfg, w, g, vic, day_ts, seed * 100 + gen)
            sc.append((f["got"], g, f))
            hist.append((g, f["got"], f["caught"]))
        sc.sort(key=lambda x: -x[0])
        curve.append(dict(gen=gen, best=sc[0][0], mean=sum(x[0] for x in sc) / len(sc), caught=sum(x[2]["caught"] for x in sc) / len(sc)))
        for s, g, f in sc[:12]:
            seen[key(norm(g))] = norm(g)
        if progress:
            progress(gen, gens, curve[-1])
        el = [g for _, g, _ in sc[:max(4, pop // 5)]]
        P = el + [mutate(rng.choice(el), rng) for _ in range(pop // 2)] + [cross(rng.choice(el), rng.choice(el), rng) for _ in range(pop // 5)]
        P = (P + [random_genome(rng) for _ in range(pop)])[:pop]
    # re-check the best on customers the search never saw: guards against flattering luck
    vic = pick_victims(w, st, 40, random.Random(seed + 9999))
    cand = sorted(seen.values(), key=lambda g: 0)
    ranked = sorted(((fitness(model, st, cfg, w, g, vic, day_ts, seed * 31 + 5), g) for g in cand), key=lambda x: -x[0]["got"])
    top, used = [], set()
    for f, g in ranked:
        if len(top) >= 8:
            break
        cls = tuple(g[k] for k in ("rail", "split", "payee", "dev", "ip", "rat", "sim", "social"))   # one row per kind of strategy
        if cls in used:
            continue
        used.add(cls)
        top.append(dict(genome=g, text=describe(g), extracted=f["got"], share=f["frac"], caught=f["caught"]))
    levers = []
    for lv, vals in LEVERS.items():
        rows = []
        buckets = vals if lv not in ("hour", "mult", "gap") else None
        if buckets is None:
            groups = {}
            for g, got, c in hist:
                v = g[lv]
                b = (v // 6 * 6, "%02d-%02d h" % (v // 6 * 6, v // 6 * 6 + 6)) if lv == "hour" else (v, str(v))
                groups.setdefault(b, []).append(got)
            rows = [dict(v=b[1], mean=sum(x) / len(x), n=len(x)) for b, x in sorted(groups.items(), key=lambda kv: kv[0][0])]
        else:
            groups = {}
            for g, got, c in hist:
                groups.setdefault(g[lv], []).append(got)
            rows = [dict(v=str(v), mean=sum(groups[v]) / len(groups[v]), n=len(groups[v])) for v in vals if v in groups]
        levers.append(dict(lever=lv, rows=rows, spread=max(r["mean"] for r in rows) - min(r["mean"] for r in rows)))
    levers.sort(key=lambda d: -d["spread"])
    return dict(curve=curve, top=top, levers=levers, baseline=curve[0]["mean"], best=top[0]["extracted"] if top else 0.0,
                best_caught=top[0]["caught"] if top else 1.0, evaluated=len(hist), victims=len(vic), seconds=round(time.time() - t0, 1),
                mean_ticket=sum(w.mean(u) for u in vic) / len(vic))


def episodes(w, genomes, n, seed, days=42):
    """Adversarial training events: each discovered attack replayed against random customers at random times."""
    rng, out = random.Random(seed), []
    for i in range(n):
        g = genomes[i % len(genomes)]
        u = w.users[rng.randrange(len(w.users))]
        day = T0 + rng.randrange(days) * DAY
        out += build(w, u, day, g, rng)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Attack the fraud engine with an automated fraudster.")
    ap.add_argument("--harden", type=int, default=0, help="rounds of attack, train-on-what-worked, attack again")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    from . import train, api
    out = []
    if not a.harden:
        g, w, rep, h, eng = api.load()
        r = search(g, eng.st, w, progress=lambda i, n, c: print("  gen %d/%d  best Rs %.0f  mean Rs %.0f" % (i + 1, n, c["best"], c["mean"])))
        out = [dict(round=0, model=api.model_version(), **r)]
        print("best attack extracts Rs %.0f per customer (%.0f%% of what it tried); caught in %.0f%% of customers" % (r["best"], 100 * r["top"][0]["share"], 100 * r["best_caught"]))
        print(r["top"][0]["text"])
    else:
        out = harden(a.harden)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1, default=float)


def harden(rounds, seed=1, base=None, seeds=3):
    """Round 0 attacks the shipped model. Each later round trains on what worked, then attacks the new model with a fresh search."""
    import hashlib
    from . import train, api
    res, genomes = [], []
    art = base or train.ART
    os.environ["FH_ART"] = art
    for rd in range(rounds + 1):
        train.ART = art
        g, w, rep, h, eng = api.load()
        ver = hashlib.sha1(open(os.path.join(art, "model.json"), "rb").read()).hexdigest()[:8]
        print("round %d: attacking model %s ..." % (rd, ver))
        # one search is noisy (three seeds against the same model found 2.5, 2.6 and 3.2 lakh), so attack with several seeds and report the middle one
        runs = sorted((search(g, eng.st, w, seed=seed + 17 * rd + 101 * k, progress=lambda i, n, c: None) for k in range(seeds)), key=lambda x: x["best"])
        r = runs[len(runs) // 2]
        r.update(round=rd, model=ver, auc=rep["auc"], ap=rep["ap"], rec1=rep["rec1"], ece=rep["ece"], bests=[x["best"] for x in runs],
                 best_min=runs[0]["best"], best_max=runs[-1]["best"])
        r["regular"] = rep.get("regular")
        res.append(r)
        print("   best extraction Rs %.0f per customer (range %.0f to %.0f over %d searches), caught in %.0f%%" % (r["best"], r["best_min"], r["best_max"], seeds, 100 * r["best_caught"]))
        if rd == rounds:
            break
        genomes += [t["genome"] for t in r["top"][:6]]
        uniq = {key(x): x for x in genomes}
        out_dir = os.path.join(os.path.dirname(art), "artifacts_hard")
        print("   training on %d discovered attack types -> %s" % (len(uniq), out_dir))
        train.main(7, adv=list(uniq.values()), out=out_dir)
        art = out_dir
    return res


if __name__ == "__main__":
    main()
