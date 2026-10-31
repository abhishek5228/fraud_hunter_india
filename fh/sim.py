"""Live traffic simulator: replays a synthetic world in compressed time, injects attacks on
demand, simulates step-up outcomes and delayed fraud reports, and keeps ground-truth stats."""
import heapq
import random
import time
from collections import OrderedDict, deque

from .gen import World

# probability a fraudster passes a step-up challenge, by typology (bots never do; RATs relay the OTP)
FPASS = {"card_test": 0.02, "mule": 0.05, "ato": 0.08, "ato_soft": 0.15, "hijack": 0.35, "travel": 0.03, "high_value": 0.05}


class Sim:
    def __init__(s, eng, world, t0, seed=99):
        s.eng, s.w, s.r = eng, world, random.Random(seed)
        s.clk, s.gen, s.hp, s.rp, s.k = t0, t0, [], [], 0
        s.spd, s.run, s.boost = 150.0, True, 1.0
        s.truth = OrderedDict()
        s.hist = deque(maxlen=600)  # (wall, n) for throughput
        s.reset()

    def reset(s):
        s.n, s.cm, s.am = 0, [[0, 0] for _ in range(3)], [[0.0, 0.0] for _ in range(3)]
        s.so = dict(lp=0, lf=0, fp=0, ff=0, lfa=0.0, ffa=0.0, fpa=0.0, ap=0)  # step-up outcomes
        s.typ = {}
        s.t_wall = time.time()

    # -- event plumbing
    def push(s, evs):
        for e in evs:
            s.k += 1
            heapq.heappush(s.hp, (e["ts"], s.k, e))

    def refill(s):
        while s.gen < s.clk + 3600:
            s.push(s.w.window(s.r, s.gen, s.gen + 3600, s.boost))
            s.gen += 3600

    def attack(s, kind):
        evs = s.w.fraud(s.r, kind, s.clk + 1.0)
        s.push(evs)
        return len(evs)

    # -- processing
    def proc(s, x):
        eng = s.eng
        while s.rp and s.rp[0][0] <= x["ts"]:
            due, _, rx = heapq.heappop(s.rp)
            eng.st.report(rx, due)
        res = eng.score(x, commit=False)
        lab, typ, dec = x["lab"], x["typ"], res["dec"]
        out = "approved"
        if dec == 1:
            p = eng.cfg.lpass if lab == 0 else FPASS.get(typ, 0.08)
            out = "pass" if s.r.random() < p else "fail"
        elif dec == 2:
            out = "declined"
        eng.st.commit(x, upd=out in ("approved", "pass"))
        if lab and s.r.random() < 0.8:
            s.k += 1
            heapq.heappush(s.rp, (x["ts"] + s.r.uniform(3600, 43200), s.k, x))
        a = x["amt"]
        s.n += 1
        s.cm[dec][lab] += 1
        s.am[dec][lab] += a
        if dec == 1:
            key = ("l" if lab == 0 else "f") + ("p" if out == "pass" else "f")
            s.so[key] += 1
            s.so[key + "a"] = s.so.get(key + "a", 0.0) + a
        t = s.typ.setdefault(typ, [0, 0, 0, 0])
        t[0 if out == "approved" or out == "pass" else 1] += 1  # got through / stopped
        t[2] += 1
        t[3] += a
        s.truth[res["id"]] = dict(lab=lab, typ=typ, out=out)
        if len(s.truth) > 20000:
            s.truth.popitem(last=False)
        return dict(id=res["id"], ts=x["ts"], uid=x["uid"], cat=x["cat"], amt=a, chan=x["chan"], city=x["city"], cty=x["cty"],
                    lat=x["lat"], lon=x["lon"], p=round(res["p"], 5), dec=dec, hits=[h["code"] for h in res["hits"]],
                    top=[dict(c=t["c"], txt=t["txt"]) for t in res["top"][:3]], lab=lab, typ=typ, out=out,
                    us=round(res["lat_us"]))

    def tick(s, dt):
        if not s.run:
            return []
        s.clk += dt * s.spd
        s.refill()
        out = []
        while s.hp and s.hp[0][0] <= s.clk:
            out.append(s.proc(heapq.heappop(s.hp)[2]))
        s.hist.append((time.time(), s.n))
        return out

    # -- stats
    def snap(s):
        cm, am, so = s.cm, s.am, s.so
        fr_stop = am[2][1] + so["ffa"]
        fr_leak = am[0][1] + so["fpa"]
        lg_lost = am[2][0] + so["lfa"]
        vol = sum(am[d][l] for d in range(3) for l in range(2))
        fn = cm[0][1] + so["fp"]
        tp = cm[2][1] + so["ff"]
        lg_n = sum(cm[d][0] for d in range(3))
        fr_n = sum(cm[d][1] for d in range(3))
        w0 = s.hist[0] if s.hist else (time.time(), s.n)
        dt = max(time.time() - w0[0], 1e-6)
        e = s.eng
        return dict(
            ts=s.clk, n=s.n, vol=vol, cm=cm, am=am, so=so, fr_stop=fr_stop, fr_leak=fr_leak, lg_lost=lg_lost,
            lg_fric=cm[1][0], fr_n=fr_n, lg_n=lg_n, fr_tp=tp, fr_fn=fn,
            recall=tp / fr_n if fr_n else 0.0, tps=(s.n - w0[1]) / dt, p50=e.pct(0.5), p99=e.pct(0.99),
            spd=s.spd, run=s.run, boost=s.boost, typ=s.typ, queue=len(s.hp),
            bps=1e4 * fr_leak / vol if vol else 0.0,
        )
