"""Who bears the friction? Replay a few days of simulated traffic and report, per group of customers, how often LEGITIMATE
customers were challenged or declined, and how often fraud against them was caught.

The simulator has no age, gender, religion or caste (and a real system must not use them as inputs). It does have behavioural
groups that real fairness audits also look at: home city, travellers, night-time users, small and large tickets, thin history.
A real audit needs the protected attributes joined in afterwards, with a lawful basis. This module is the harness for that.
"""
import copy
import math
import random

import numpy as np

from .engine import Engine
from .geo import CITY

TIER1 = {"Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"}


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def run(model, store, world, cfg, now, days=3, seed=11, min_n=100):
    eng = Engine(model, copy.deepcopy(store), cfg, keep=1)
    rng = random.Random(seed)
    users = {u["uid"]: u for u in world.users}
    evs = world.window(rng, now, now + days * 86400, 1.0)
    rows = []
    for x in evs:
        pre = eng.st.u.get(x["uid"])
        res = eng.score(x, commit=False)
        d = res["dec"]
        passed = d == 1 and rng.random() < (cfg.lpass if not x["lab"] else cfg.fpass)
        eng.st.commit(x, upd=d == 0 or passed)
        u = users.get(x["uid"])
        if u is None:
            continue
        w = u["w"]
        night = max(range(24), key=lambda h: w[h]) in (22, 23, 0, 1, 2, 3)
        rows.append((x["lab"], d, CITY[u["hc"]][0], bool(u["trip"]), night, x["chan"], x["amt"], (pre.n if pre else 0), len(u["devs"])))
    if not rows:
        raise ValueError("no traffic generated")
    lab = np.array([r[0] for r in rows])
    dec = np.array([r[1] for r in rows])
    L = lab == 0
    base = float((dec[L] > 0).mean())

    def seg(group, name, mask):
        m = mask & L
        n = int(m.sum())
        t = int((dec[m] > 0).sum())
        lo, hi = wilson(t, n)
        f = mask & (lab == 1)
        nf = int(f.sum())
        ratio = (t / n) / base if n and base else None
        lo99 = wilson(t, n, 2.576)[0]
        flag = bool(n >= min_n and ratio is not None and ratio >= 1.5 and lo99 > base)   # 99% bound: about 40 groups are compared at once
        return dict(group=group, seg=name, n=n, touched=t / n if n else None, lo=lo, hi=hi, declined=float((dec[m] == 2).mean()) if n else None,
                    ratio=ratio, flag=flag, small=n < min_n, fraud_n=nf, caught=float((dec[f] > 0).mean()) if nf >= 10 else None)
    col = lambda i: np.array([r[i] for r in rows])
    city, trip, night, chan, amt, hist, nd = col(2), col(3).astype(bool), col(4).astype(bool), col(5), col(6).astype(float), col(7).astype(float), col(8)
    out = []
    for c in sorted(set(city), key=lambda c: -(city == c).sum()):
        out.append(seg("Home city", c, city == c))
    t1 = np.array([c in TIER1 for c in city])
    out += [seg("City tier", "Large metro", t1), seg("City tier", "Smaller city", ~t1),
            seg("Travel", "Travelled this period", trip), seg("Travel", "Stayed home", ~trip),
            seg("Hours", "Night-time user", night), seg("Hours", "Daytime user", ~night)]
    out += [seg("Rail", c.upper(), chan == c) for c in ("upi", "ecom", "pos", "atm", "imps")]
    out += [seg("Ticket size", "under ₹500", amt < 500), seg("Ticket size", "₹500 to ₹5,000", (amt >= 500) & (amt < 5000)),
            seg("Ticket size", "₹5,000 to ₹50,000", (amt >= 5000) & (amt < 50000)), seg("Ticket size", "over ₹50,000", amt >= 50000)]
    out += [seg("History", "Thin (under 10 payments)", hist < 10), seg("History", "Established", hist >= 10)]
    out += [seg("Devices", "One device", nd == 1), seg("Devices", "Two devices", nd == 2)]
    return dict(base=base, legit_n=int(L.sum()), fraud_n=int((lab == 1).sum()), days=days, min_n=min_n, segments=out,
                flagged=[s for s in out if s["flag"]],
                note="Groups are behavioural, from the simulator. A flag means legitimate customers in that group are challenged at least 1.5 times as often as average, with the lower end of a 99% interval above the overall rate. About 40 groups are compared, so treat a single marginal flag as a lead to look at, not a finding.")
