"""Who bears the friction? Report, per group of customers, how often LEGITIMATE customers were challenged or declined, and how
often fraud against them was caught.

Two uses:
  run()    replay a few simulated days and report behavioural groups (home city, travellers, night users, rail, ticket size, history).
  audit()  join attributes the engine never saw (age band, gender, state, language...) onto real decisions afterwards, which is how a
           real fairness audit is done. CLI:  python -m fh.fairness decisions.csv attributes.csv --by age_band,gender

The simulator has no age, gender, religion or caste, and a real system must not use them as inputs. Flags use a one-sided two-proportion
test with Benjamini-Hochberg correction across every comparison made (false-discovery rate 5%), plus a practical-size rule (at least 1.5x
the average rate), so comparing 40 groups does not manufacture findings. A flag is a lead for a human, never a verdict.
"""
import argparse
import copy
import csv
import json
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


def pvalue(t, n, t0, n0):
    """One-sided two-proportion z-test: is this group's touched rate above everyone else's?"""
    if n == 0 or n0 == 0:
        return 1.0
    p = (t + t0) / (n + n0)
    se = math.sqrt(p * (1 - p) * (1 / n + 1 / n0)) or 1e-12
    z = (t / n - t0 / n0) / se
    return 0.5 * math.erfc(z / math.sqrt(2))


def benjamini_hochberg(ps, q=0.05):
    """Which hypotheses survive a false-discovery rate of q across all comparisons made."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    cut = 0
    for rank, i in enumerate(order, 1):
        if ps[i] <= q * rank / m:
            cut = rank
    keep = set(order[:cut])
    return [i in keep for i in range(m)]


def summarise(lab, dec, groups, min_n=100, fdr=0.05):
    """groups: list of (group, segment, boolean mask) over the same rows. Returns the segment table with corrected flags."""
    lab, dec = np.asarray(lab), np.asarray(dec)
    L = lab == 0
    base = float((dec[L] > 0).mean())
    out, ps = [], []
    for group, name, mask in groups:
        mask = np.asarray(mask)
        m = mask & L
        n, t = int(m.sum()), int((dec[m] > 0).sum())
        rest = L & ~mask
        n0, t0 = int(rest.sum()), int((dec[rest] > 0).sum())
        lo, hi = wilson(t, n)
        f = mask & (lab == 1)
        nf = int(f.sum())
        ratio = (t / n) / base if n and base else None
        ps.append(pvalue(t, n, t0, n0) if n >= min_n else 1.0)
        out.append(dict(group=group, seg=name, n=n, touched=t / n if n else None, lo=lo, hi=hi, declined=float((dec[m] == 2).mean()) if n else None,
                        ratio=ratio, small=n < min_n, fraud_n=nf, caught=float((dec[f] > 0).mean()) if nf >= 10 else None, p=ps[-1]))
    for o, k in zip(out, benjamini_hochberg(ps, fdr)):
        o["flag"] = bool(k and o["ratio"] is not None and o["ratio"] >= 1.5)
    return dict(base=base, legit_n=int(L.sum()), fraud_n=int((lab == 1).sum()), min_n=min_n, fdr=fdr, segments=out,
                flagged=[o for o in out if o["flag"]], compared=len(out))


NOTE = ("A flag means legitimate customers in that group are challenged at least 1.5 times as often as everyone else AND the difference survives a "
        "Benjamini-Hochberg correction across all %d comparisons (5%% false-discovery rate). It is a lead for a human, not a verdict.")


def audit(decisions, attrs, by, min_n=100):
    """Join attributes the engine never saw onto decisions after the fact.

    decisions: dicts with uid, decision (APPROVE/STEP_UP/DECLINE) and label (0/1), e.g. rows of the backtest CSV.
    attrs: dict uid -> {attribute: value}. by: attribute names to report on.
    """
    rows = [(d["uid"], d["decision"], int(float(d["label"]))) for d in decisions if str(d.get("label", "")) != "" and d["uid"] in attrs]
    if not rows:
        raise ValueError("no labelled decisions could be matched to the attributes file (check the uid column and that the decisions have labels)")
    lab = np.array([r[2] for r in rows])
    dec = np.array([{"APPROVE": 0, "STEP_UP": 1, "DECLINE": 2}[r[1]] for r in rows])
    groups = []
    for a in by:
        vals = np.array([str(attrs[r[0]].get(a, "")) for r in rows])
        for v in sorted(set(vals)):
            if v != "":
                groups.append((a, v, vals == v))
    if not groups:
        raise ValueError("none of %s found in the attributes file" % ", ".join(by))
    res = summarise(lab, dec, groups, min_n)
    res.update(matched_rows=len(rows), note=NOTE % res["compared"])
    return res


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
    col = lambda i: np.array([r[i] for r in rows])
    lab, dec = col(0), col(1)
    city, trip, night, chan, amt, hist, nd = col(2), col(3).astype(bool), col(4).astype(bool), col(5), col(6).astype(float), col(7).astype(float), col(8)
    t1 = np.array([c in TIER1 for c in city])
    G = [("Home city", c, city == c) for c in sorted(set(city), key=lambda c: -(city == c).sum())]
    G += [("City tier", "Large metro", t1), ("City tier", "Smaller city", ~t1), ("Travel", "Travelled this period", trip), ("Travel", "Stayed home", ~trip),
          ("Hours", "Night-time user", night), ("Hours", "Daytime user", ~night)]
    G += [("Rail", c.upper(), chan == c) for c in ("upi", "ecom", "pos", "atm", "imps")]
    G += [("Ticket size", "under ₹500", amt < 500), ("Ticket size", "₹500 to ₹5,000", (amt >= 500) & (amt < 5000)),
          ("Ticket size", "₹5,000 to ₹50,000", (amt >= 5000) & (amt < 50000)), ("Ticket size", "over ₹50,000", amt >= 50000)]
    G += [("History", "Thin (under 10 payments)", hist < 10), ("History", "Established", hist >= 10), ("Devices", "One device", nd == 1), ("Devices", "Two devices", nd == 2)]
    res = summarise(lab, dec, G, min_n)
    res.update(days=days, note="Groups are behavioural, from the simulator. " + NOTE % res["compared"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fairness audit: join attributes onto decisions after the fact.")
    ap.add_argument("decisions", help="CSV with uid, decision, label (the backtest 'download every decision' file works if you add a uid)")
    ap.add_argument("attributes", help="CSV with uid plus the attribute columns")
    ap.add_argument("--by", required=True, help="comma-separated attribute columns to report on")
    ap.add_argument("--json", help="write the full report here")
    a = ap.parse_args(argv)
    dec = list(csv.DictReader(open(a.decisions, encoding="utf-8-sig")))
    attrs = {r["uid"]: r for r in csv.DictReader(open(a.attributes, encoding="utf-8-sig"))}
    res = audit(dec, attrs, [x.strip() for x in a.by.split(",")])
    print("%d decisions matched; legitimate customers challenged or declined on average: %.2f%%" % (res["matched_rows"], 100 * res["base"]))
    for s in res["segments"]:
        print("  %-14s %-18s n=%-6d touched %5.2f%%  %s  %s" % (s["group"], s["seg"], s["n"], 100 * (s["touched"] or 0), "%.2fx" % s["ratio"] if s["ratio"] else "-", "FLAG" if s["flag"] else ("(too few)" if s["small"] else "")))
    print(res["note"])
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
