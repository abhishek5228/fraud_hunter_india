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
        s.vecs = deque(maxlen=4000)   # recent feature vectors, for drift monitoring

    def score(s, x, commit=True):
        t0 = time.perf_counter_ns()
        vec, raw = s.st.feats(x)
        lg, con = s.m.contrib(vec)
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, lg))))
        hits = rules.check(x, raw, s.st)
        cost = policy.costs(p, x["amt"], s.cfg, policy.rail_k(x["chan"], x["amt"], x.get("pers")))
        dpol = policy.pick(*cost)
        dec = max(dpol, rules.level(hits))
        top = explain.reasons(s.m.names, con, raw)
        s.seq += 1
        codes = [h[1] for h in hits]
        res = dict(
            id=x.get("id") or "t%07d" % s.seq, ts=x["ts"], uid=x["uid"], mid=x["mid"], cat=x["cat"], amt=x["amt"],
            chan=x["chan"], city=x.get("city", ""), cty=x["cty"], lat=x["lat"], lon=x["lon"], dev=x["dev"], ip=x["ip"],
            sim=raw["sim"] if raw["sim"] < 1e3 else None, rat=bool(raw["ratf"]), coll=bool(raw["coll"]), pers=bool(raw["pers"]),
            p=p, score=int(round(100 * p)), dec=dec, dname=policy.NAMES[dec], dpol=dpol,
            hits=[dict(lvl=h[0], code=h[1], msg=h[2]) for h in hits], top=top, cost=[round(c, 4) for c in cost],
            logit=lg, base=s.m.b0, why=explain.summary(dec, p, top, hits, cost, x["amt"]),
            msg=explain.customer_msg(dec, x["amt"], x["mid"], codes),
        )
        res["lat_us"] = (time.perf_counter_ns() - t0) / 1000.0
        s.lat.append(res["lat_us"])
        s.vecs.append(vec)
        s.cases[res["id"]] = res
        if len(s.cases) > s.keep:
            s.cases.popitem(last=False)
        if commit:
            # Only an approved payment teaches us what the customer normally does. A challenged one is pending:
            # the graph learns who touched what, but the device is not trusted until `confirm` says it passed.
            s.st.commit(x, upd=dec == 0)
        return res

    def confirm(s, cid, passed):
        """Second phase for a challenged payment: the customer passed (or abandoned) the step-up."""
        res = s.cases.get(cid)
        if not res or res["dec"] != 1:
            return False
        if passed:
            s.st.commit(res, upd=True)
        return True

    def pct(s, q):
        v = sorted(s.lat)
        return v[min(len(v) - 1, int(q * len(v)))] if v else 0.0
