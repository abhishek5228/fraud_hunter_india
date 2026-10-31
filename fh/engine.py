"""The real-time risk engine: features -> model -> rules -> cost policy -> explained decision."""
import math
import time
from collections import OrderedDict, deque

from . import rules, policy, explain


class Engine:
    def __init__(s, model, store, cfg=None, keep=20000):
        s.m, s.st, s.cfg = model, store, cfg or policy.Cfg()
        s.cases, s.keep, s.seq = OrderedDict(), keep, 0
        s.lat = deque(maxlen=4000)

    def score(s, x, commit=True):
        t0 = time.perf_counter_ns()
        vec, raw = s.st.feats(x)
        lg, con = s.m.contrib(vec)
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, lg))))
        hits = rules.check(x, raw, s.st)
        cost = policy.costs(p, x["amt"], s.cfg)
        dpol = policy.pick(*cost)
        dec = max(dpol, rules.level(hits))
        top = explain.reasons(s.m.names, con, raw)
        s.seq += 1
        res = dict(
            id=x.get("id") or "t%07d" % s.seq, ts=x["ts"], uid=x["uid"], mid=x["mid"], cat=x["cat"], amt=x["amt"],
            chan=x["chan"], city=x.get("city", ""), cty=x["cty"], lat=x["lat"], lon=x["lon"], dev=x["dev"], ip=x["ip"],
            p=p, score=int(round(100 * p)), dec=dec, dname=policy.NAMES[dec], dpol=dpol,
            hits=[dict(lvl=h[0], code=h[1], msg=h[2]) for h in hits], top=top, cost=[round(c, 4) for c in cost],
            logit=lg, base=s.m.b0, why=explain.summary(dec, p, top, hits, cost, x["amt"]),
        )
        res["lat_us"] = (time.perf_counter_ns() - t0) / 1000.0
        s.lat.append(res["lat_us"])
        s.cases[res["id"]] = res
        if len(s.cases) > s.keep:
            s.cases.popitem(last=False)
        if commit:
            s.st.commit(x, upd=dec != 2)
        return res

    def pct(s, q):
        v = sorted(s.lat)
        return v[min(len(v) - 1, int(q * len(v)))] if v else 0.0
