"""Backtest: replay YOUR historical transactions through the engine and report what it would have done.

No live system is touched. A fresh, isolated feature store is built from the file itself, so the same code
path as production decides every row, in time order.

    python -m fh.backtest transactions.csv --out decisions.csv --json summary.json

Required columns : ts (epoch seconds or ISO-8601), uid, amt, chan (upi|ecom|pos|atm|imps), mid (payee or merchant id)
Location         : city (one of the known city names) OR lat + lon (+ cty, default IN)
Optional         : cat, dev, ip, pers (1 if the payee is a person/account), coll, rat, sim (hours since SIM change),
                   label (0 = good, 1 = confirmed fraud the customer did not make, 2 = confirmed fraud the customer was tricked
                   into making, i.e. an authorised scam). With labels you also get catch rates and money saved.
                   The 1-versus-2 split matters: a complaint about a tricked customer taints the PAYEE, never the victim's own phone.

The model was trained on synthetic data. Treat the output as a demonstration of the method until it is
retrained on your own history.
"""
import argparse
import csv
import datetime as dt
import heapq
import io
import json
import random
import sys
import time

import numpy as np

from . import feat, model as mdl, policy, whatif
from .engine import Engine
from .gen import CATS, PERS_CATS
from .geo import CITY

MAX_ROWS = 150_000
CHANS = ("upi", "ecom", "pos", "atm", "imps")
_CITY = {c[0].lower(): c for c in CITY}


def _f(v, d=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _ts(v):
    t = _f(v)
    if t is not None:
        return t / 1000.0 if t > 1e11 else t      # accept milliseconds
    s = str(v).strip().replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:                            # no zone given: assume India Standard Time
        d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30)))
    return d.timestamp()


def _bool(v):
    return str(v).strip().lower() in ("1", "true", "t", "yes", "y")


def parse(text):
    """CSV text -> (rows, problems). A bad row is skipped and explained, never silently guessed."""
    rd = csv.DictReader(io.StringIO(text))
    cols = {(c or "").strip().lower() for c in (rd.fieldnames or [])}
    need = {"ts", "uid", "amt", "chan", "mid"}
    if not need <= cols:
        raise ValueError("missing required column(s): %s. Found: %s" % (", ".join(sorted(need - cols)), ", ".join(sorted(cols)) or "none"))
    if not ({"city"} <= cols or {"lat", "lon"} <= cols):
        raise ValueError("give a location: either a city column, or lat and lon columns")
    rows, bad, cat_default = [], [], 0
    for i, raw in enumerate(rd, start=2):                     # line 1 is the header
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if len(rows) >= MAX_ROWS:
            bad.append("stopped at %d rows (limit)" % MAX_ROWS)
            break
        try:
            ts, amt = _ts(r["ts"]), _f(r["amt"])
            if amt is None or amt <= 0:
                raise ValueError("amount must be a positive number")
            ch = r["chan"].lower()
            if ch not in CHANS:
                raise ValueError("chan %r is not one of %s" % (r["chan"], "/".join(CHANS)))
            if not r["uid"] or not r["mid"]:
                raise ValueError("uid and mid are required")
            c = _CITY.get(r.get("city", "").lower())
            lat, lon, cty = (c[1], c[2], c[3]) if c else (_f(r.get("lat")), _f(r.get("lon")), r.get("cty") or "IN")
            if lat is None or lon is None:
                raise ValueError("unknown city %r and no lat/lon" % r.get("city"))
            cat = r.get("cat", "")
            if cat not in CATS:
                cat, cat_default = ("p2p" if _bool(r.get("pers")) else "digital"), cat_default + 1
            pers = _bool(r["pers"]) if r.get("pers", "") != "" else cat in PERS_CATS
            lab = r.get("label", "")
            lv = _f(lab)
            if lv is not None and lv not in (0, 1, 2):
                raise ValueError("label must be 0, 1 or 2")
            rows.append(dict(line=i, ts=ts, uid=r["uid"], mid=r["mid"], cat=cat, amt=amt, chan=ch, dev=r.get("dev") or None,
                             ip=r.get("ip") or None, lat=lat, lon=lon, cty=cty, city=c[0] if c else r.get("city", ""), pers=pers,
                             coll=_bool(r.get("coll")), rat=_bool(r.get("rat")), sim=_f(r.get("sim"), 1e4),
                             lab=None if lv is None else (1 if lv else 0), app=lv == 2))
        except (ValueError, KeyError) as e:
            if len(bad) < 25:
                bad.append("line %d: %s" % (i, e))
    if cat_default:
        bad.append("%d row(s) had an unknown or missing category and were treated as %s" % (cat_default, "digital/p2p"))
    return rows, bad


def run(rows, g, cfg=None, report_lag=6 * 3600, seed=1, warmup_days=None):
    """Replay rows in time order through a fresh engine. Returns (summary, per_row_results)."""
    cfg = cfg or policy.Cfg()
    t0 = time.time()
    rows = sorted(rows, key=lambda r: r["ts"])
    if not rows:
        raise ValueError("no usable rows")
    span = (rows[-1]["ts"] - rows[0]["ts"]) / 86400
    # The engine judges "new payee", "new device" and "unusual amount" against each customer's history, and some rules
    # (payee fan-in) assume a mature store. A fresh store has none, so the start of any file looks suspicious.
    # Learn from the first 3 weeks of a long file, or the first half of a shorter one.
    wd = (min(21.0, round(span / 2, 1)) if span >= 4 else 0.0) if warmup_days is None else warmup_days
    cut = rows[0]["ts"] + wd * 86400
    eng, rng, pend = Engine(g, feat.Store(), cfg, keep=1), random.Random(seed), []
    labelled = any(r["lab"] is not None for r in rows)
    out = []
    for k, r in enumerate(rows):
        while pend and pend[0][0] <= r["ts"]:
            due, _, rx = heapq.heappop(pend)
            eng.st.report(rx, due)
        x = dict(r, id="b%d" % k, typ="backtest")
        res = eng.score(x, commit=False)
        dec = res["dec"]
        passed = dec == 1 and rng.random() < (cfg.lpass if not r["lab"] else cfg.fpass)   # assume a challenge behaves like the policy expects
        eng.st.commit(x, upd=dec == 0 or passed)
        if r["lab"] == 1 and rng.random() < 0.8:
            heapq.heappush(pend, (r["ts"] + report_lag, k, x))
        drv = next((t["f"] for t in res["top"] if t["c"] > 0 and t["f"] != "lamt"), "")
        out.append(dict(i=k, line=r["line"], ts=r["ts"], uid=r["uid"], amt=r["amt"], chan=r["chan"], mid=r["mid"], p=res["p"], dec=dec,
                        codes=[h["code"] for h in res["hits"]], drv=drv, lab=r["lab"], scored=r["ts"] >= cut, cold=eng.st.u.get(r["uid"]) is None or eng.st.u[r["uid"]].n < 4))
    S = [o for o in out if o["scored"]]
    if not S:
        raise ValueError("all rows fell inside the warm-up window; use a longer file")
    p, a = np.array([o["p"] for o in S]), np.array([o["amt"] for o in S])
    dec = np.array([o["dec"] for o in S])
    k = policy.kvec([o["chan"] for o in S], a, [rows[o["i"]]["pers"] for o in S])
    ch = np.array([o["chan"] for o in S])
    sm = dict(n=len(rows), scored=len(S), warm=len(rows) - len(S), span_days=round(span, 1), labelled=labelled, warmup_days=wd,
              decisions=dict(approve=int((dec == 0).sum()), step=int((dec == 1).sum()), decline=int((dec == 2).sum())),
              cold_share=float(np.mean([o["cold"] for o in S])), model_note="trained on synthetic data", seconds=round(time.time() - t0, 1),
              amount_total=float(a.sum()), flagged_amount=float(a[dec > 0].sum()), cfg=cfg.dict())
    sm["warnings"] = []
    if sm["cold_share"] > 0.15:
        sm["warnings"].append("%.0f%% of scored payments are from customers with fewer than 4 trusted payments in this file, so the engine is judging them with little history. Expect extra friction; a longer file (a month or more) gives fairer numbers." % (100 * sm["cold_share"]))
    if span < 28:
        sm["warnings"].append("This file spans %.0f days. The engine was developed against stores with 5+ weeks of history; shorter files overstate friction (new payees and devices look suspicious until history builds up)." % span)
    if wd == 0:
        sm["warnings"].append("This file spans under 4 days, so no warm-up was used: every customer starts with no history.")
    if labelled:
        y = np.array([1.0 if o["lab"] == 1 else 0.0 for o in S])
        sm["fraud_n"] = int(y.sum())
        if 0 < y.sum() < len(y):
            sm["auc"], sm["ap"] = mdl.roc_auc(y, p), mdl.avg_prec(y, p)
        real = lambda d: whatif.realised(d, y, a, cfg, k)
        cur = real(dec)
        ths = np.exp(np.linspace(np.log(1e-3), np.log(0.95), 40))
        best1 = min((real(np.where(p > t, 2, 0)) for t in ths), key=lambda m: m["cost"])
        sm["impact"] = dict(cur=cur, allow=real(np.zeros_like(dec)), naive=real(np.where(p > 0.5, 2, 0)), best1=best1)
        sm["fraud_amount"] = float(a[y == 1].sum())
        sm["by_rail"] = [dict(rail=c, n=int((ch == c).sum()), fraud=int(y[ch == c].sum()), caught=float(((dec > 0) & (y == 1) & (ch == c)).sum() / max(y[ch == c].sum(), 1)),
                              touched=float(((dec > 0) & (y == 0) & (ch == c)).sum() / max(((y == 0) & (ch == c)).sum(), 1))) for c in CHANS if (ch == c).any()]
    else:
        sm["by_rail"] = [dict(rail=c, n=int((ch == c).sum()), flagged=float(((dec > 0) & (ch == c)).sum() / (ch == c).sum())) for c in CHANS if (ch == c).any()]
    cnt = {}
    for o in S:
        if o["dec"] > 0:
            for c in o["codes"] or ["MODEL_ONLY"]:
                z = cnt.setdefault(c, [0, 0])
                z[0] += 1
                z[1] += 1 if o["lab"] == 1 else 0
    sm["reasons"] = sorted([dict(code=c, n=v[0], fraud_share=(v[1] / v[0] if labelled else None)) for c, v in cnt.items()], key=lambda d: -d["n"])[:10]
    drv = {}
    for o in S:
        if o["dec"] > 0 and o["drv"]:
            drv[o["drv"]] = drv.get(o["drv"], 0) + 1
    sm["drivers"] = sorted([dict(f=f, n=n) for f, n in drv.items()], key=lambda d: -d["n"])[:8]
    top = sorted((o for o in S if o["dec"] > 0), key=lambda o: -o["p"])[:15]
    sm["top_rows"] = [dict(line=o["line"], ts=o["ts"], uid=o["uid"], amt=o["amt"], chan=o["chan"], mid=o["mid"], p=o["p"], dec=o["dec"], codes=o["codes"], label=o["lab"]) for o in top]
    return sm, out


def to_csv(out):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["line", "ts", "uid", "amt", "chan", "mid", "decision", "fraud_probability", "reasons", "top_driver", "label", "scored"])
    for o in out:
        w.writerow([o["line"], "%.0f" % o["ts"], o["uid"], o["amt"], o["chan"], o["mid"], policy.NAMES[o["dec"]], "%.5f" % o["p"], "|".join(o["codes"]),
                    o["drv"], "" if o["lab"] is None else o["lab"], int(o["scored"])])
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay a transactions CSV through the fraud engine.")
    ap.add_argument("csv")
    ap.add_argument("--out", help="write per-row decisions to this CSV")
    ap.add_argument("--json", help="write the summary to this JSON file")
    a = ap.parse_args(argv)
    import os
    from . import train
    g = mdl.GAM.load(json.load(open(os.path.join(train.ART, "model.json"))))
    rows, bad = parse(open(a.csv, encoding="utf-8-sig").read())
    for b in bad:
        print("warning:", b, file=sys.stderr)
    sm, out = run(rows, g)
    d = sm["decisions"]
    print("%d rows (%d scored after a %.0f-day warm-up) in %.1fs: %d approve, %d step-up, %d decline" % (sm["n"], sm["scored"], sm["warmup_days"], sm["seconds"], d["approve"], d["step"], d["decline"]))
    if sm["labelled"]:
        c = sm["impact"]["cur"]
        print("fraud caught %.1f%%, good customers touched %.2f%%, cost Rs %.0f vs Rs %.0f approving everything" % (100 * c["caught"], 100 * c["touched"], c["cost"], sm["impact"]["allow"]["cost"]))
    if a.out:
        open(a.out, "w").write(to_csv(out))
    if a.json:
        json.dump(sm, open(a.json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
