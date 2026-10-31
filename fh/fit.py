"""Fit the risk model to YOUR csv.

    python -m fh.fit data.csv --out artifacts_mine            # auto-detect columns, train, report
    python -m fh.fit data.csv --map uid=sender_id,label=fraud # fix a column the detector got wrong
    python -m fh.fit data.csv --mode tabular                  # rows already carry engineered features (no customer history)
    python -m fh.fit --predict artifacts_mine new.csv --out scored.csv

Two paths, chosen automatically (override with --mode):
  events   the file has a customer id + timestamp. Rows are replayed in time order through the same feature store the
           live engine uses (44 behavioural features, reputation, payee graph, guardrails). The saved model.json drops
           straight into the backtest:   FH_ART=artifacts_mine python -m fh.backtest new.csv
  tabular  no usable customer/time structure. A GAM is fitted on the file's own columns (numbers, categories, lists).

Splits are by TIME when the file has time, random otherwise (and the report says which, because random splits flatter).
Columns that give the answer away are removed and listed, never trained on.
"""
import argparse
import csv
import heapq
import io
import json
import math
import os
import random
import re
import sys
import time

import numpy as np

from . import backtest as bt, feat, ingest, model as mdl, policy, rules, train

MIN_POS = 30


def _split_time(ts, y, burn_frac=0.15, burn_cap=7 * 86400):
    """Index masks (burn, train, val, test) by time. Burn-in rows still update history but are never fitted."""
    o = np.argsort(ts, kind="stable")
    t0, t1 = ts[o[0]], ts[o[-1]]
    burn = ts < t0 + min((t1 - t0) * burn_frac, burn_cap)
    rest = np.where(~burn)[0]
    rest = rest[np.argsort(ts[rest], kind="stable")]
    a, b = int(len(rest) * 0.65), int(len(rest) * 0.80)
    m = lambda ix: np.isin(np.arange(len(ts)), ix)
    return burn, m(rest[:a]), m(rest[a:b]), m(rest[b:])


def _check_split(y, tr, va, te, what):
    for nm, mk in (("train", tr), ("validation", va), ("test", te)):
        pos = int(y[mk].sum())
        if mk.sum() == 0 or pos < (MIN_POS if nm == "train" else 5) or pos == mk.sum():
            raise ValueError("%s split has %d fraud rows out of %d (%s). Need at least %d fraud rows in train and 5 in each other split. "
                             "Use more data, or a file with more labelled fraud." % (nm, pos, int(mk.sum()), what, MIN_POS))


def _report(g, lr, X, y, tr, va, te, amt, chan, pers, frc, names, split, notes, extra=None):
    cfg = policy.Cfg()
    pg, pl = g.predict(X[te]), lr.predict(X[te])
    k = policy.kvec(chan[te], amt[te], pers[te])
    typ = np.array(["all"] * int(te.sum()))
    rep, dec = train.evaluate(y[te], pg, amt[te], typ, frc[te], cfg, k)
    repl, _ = train.evaluate(y[te], pl, amt[te], typ, frc[te], cfg, k)
    rep["lr"] = {q: repl[q] for q in ("auc", "ap", "rec1", "rec01", "ll", "ece")}
    Btr = g.bins(X[tr])
    rep["importance"] = sorted([dict(f=n, v=float(np.abs(g.sh[j][Btr[:, j]]).mean())) for j, n in enumerate(names)], key=lambda a: -a["v"])
    base = float(y[te].mean())
    rep["base_rate"] = base
    rep["rules_only"] = dict(recall=float(((frc[te] > 0) & (y[te] == 1)).sum() / max(y[te].sum(), 1)),
                             fpr=float(((frc[te] > 0) & (y[te] == 0)).sum() / max((y[te] == 0).sum(), 1)))
    n0 = max(int((y[te] == 0).sum()), 1)
    rep["policy"] = dict(approve=float((dec == 0).mean()), step=float((dec == 1).mean()), decline=float((dec == 2).mean()),
                         caught=float(((dec > 0) & (y[te] == 1)).sum() / max(y[te].sum(), 1)),
                         touched=float(((dec > 0) & (y[te] == 0)).sum() / n0))
    rep["split"] = dict(kind=split, train=int(tr.sum()), val=int(va.sum()), test=int(te.sum()), test_fraud=int(y[te].sum()))
    rep["notes"] = notes
    if rep["auc"] > 0.995:
        notes.append("AUC %.4f is too good to be real-world fraud: the data is almost certainly synthetic or still leaks the label. "
                     "Do not quote this number as evidence the model works." % rep["auc"])
    rep.update(extra or {})
    return rep


def _show(rep):
    s, p = rep["split"], rep["policy"]
    print("\nsplit: %s  (train %d / val %d / test %d, %d fraud in test, base rate %.2f%%)" % (
        s["kind"], s["train"], s["val"], s["test"], s["test_fraud"], 100 * rep["base_rate"]))
    print("GAM  AUC %.4f  AP %.4f  recall@1%%FPR %.3f  recall@0.1%%FPR %.3f  ECE %.4f" % (rep["auc"], rep["ap"], rep["rec1"], rep["rec01"], rep["ece"]))
    l = rep["lr"]
    print("LR   AUC %.4f  AP %.4f  recall@1%%FPR %.3f   <- baseline; if it ties the GAM, say so" % (l["auc"], l["ap"], l["rec1"]))
    print("policy on test: approve %.1f%% / step-up %.1f%% / decline %.1f%%  |  fraud touched %.1f%%, good customers touched %.2f%%" % (
        100 * p["approve"], 100 * p["step"], 100 * p["decline"], 100 * p["caught"], 100 * p["touched"]))
    print("top drivers:", ", ".join("%s (%.2f)" % (d["f"], d["v"]) for d in rep["importance"][:6]))
    for n in rep["notes"]:
        print("note:", n)


# ---------------------------------------------------------------- events path

def fit_events(rows, out, notes):
    rows = sorted([r for r in rows if r["lab"] is not None], key=lambda r: r["ts"])
    if len(rows) < 500:
        raise ValueError("only %d labelled rows; need at least 500 for the events path" % len(rows))
    st, pend = feat.Store(), []
    X, Y, F, T, A, C, P = [], [], [], [], [], [], []
    for k, r in enumerate(rows):
        while pend and pend[0][0] <= r["ts"]:
            due, _, rx = heapq.heappop(pend)
            st.report(rx, due)
        x = dict(r, id="f%d" % k, typ="csv")
        v, raw = st.feats(x)
        X.append(v)
        Y.append(1.0 if r["lab"] else 0.0)
        F.append(rules.level(rules.check(x, raw, st)))
        T.append(r["ts"]); A.append(r["amt"]); C.append(r["chan"]); P.append(bool(r["pers"]))
        st.commit(x, upd=not r["lab"])
        if r["lab"] == 1 and random.Random(k).random() < 0.8:      # bank learns of the fraud later, as in production
            heapq.heappush(pend, (r["ts"] + 6 * 3600, k, x))
        if k % 20000 == 0:
            st.prune(r["ts"])
    X, y, F, ts, amt, chan, pers = np.array(X), np.array(Y), np.array(F), np.array(T), np.array(A), np.array(C), np.array(P)
    span = (ts[-1] - ts[0]) / 86400
    burn, tr, va, te = _split_time(ts, y)
    _check_split(y, tr, va, te, "time-ordered split over %.0f days" % span)
    if span < 28:
        notes.append("the file spans %.0f days; behavioural history (new payee, usual amount) is thin, so every number here is pessimistic" % span)
    print("events: %d rows over %.0f days, %d fraud (%.2f%%); fitting on %d, validating on %d, testing on %d" % (
        len(y), span, y.sum(), 100 * y.mean(), tr.sum(), va.sum(), te.sum()))
    g = mdl.GAM(feat.NAMES).fit(X[tr], y[tr], X[va], y[va], log=lambda *a: None)
    lr = mdl.LR().fit(X[tr], y[tr])
    rep = _report(g, lr, X, y, tr, va, te, amt, chan, pers, F, feat.NAMES, "time-ordered (burn-in excluded)", notes,
                  dict(path="events", span_days=round(span, 1)))
    Bva = g.bins(X[va])
    rep["ref"] = {n: (np.bincount(Bva[:, j], minlength=g.nb[j]) / len(Bva)).tolist() for j, n in enumerate(feat.NAMES)}
    rep["ref_n"] = int(len(Bva))
    d = g.dump()
    d["path"] = "events"
    os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, "model.json"), "w"))
    return g, rep


# ---------------------------------------------------------------- tabular path

def _num(v):
    try:
        return float(v.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def _plan(cols, data, y, skip):
    """Decide, per column, how to turn it into numbers. Returns a JSON-able plan."""
    plan, n = [], len(y)
    for c in cols:
        if c in skip:
            continue
        vals = [r.get(c, "") for r in data]
        ne = [v for v in vals if v not in ("", None)]
        if len(ne) < 0.05 * n:
            continue
        nums = [_num(v) for v in ne[:3000]]
        if sum(x is not None for x in nums) >= 0.9 * len(nums):
            plan.append(dict(c=c, k="num", med=float(np.median([x for x in nums if x is not None] or [0.0]))))
        elif sum(1 for v in ne[:3000] if v.startswith("[")) >= 0.9 * len(ne[:3000]):
            plan.append(dict(c=c, k="list"))
        else:
            cnt = {}
            for v in ne:
                cnt[v] = cnt.get(v, 0) + 1
            if len(cnt) > 0.5 * len(ne) or len(cnt) > 400:
                continue                                   # an identifier, not a feature
            keep = [v for v, q in sorted(cnt.items(), key=lambda t: -t[1])[:12] if q >= 0.01 * n]
            if keep:
                plan.append(dict(c=c, k="cat", lv=keep))
    return plan


def _apply(plan, data):
    names, cols = [], []
    for p in plan:
        v = [r.get(p["c"], "") for r in data]
        if p["k"] == "num":
            cols.append([(_num(x) if _num(x) is not None else p["med"]) for x in v]); names.append(p["c"])
        elif p["k"] == "list":
            cols.append([float(len(re.findall(r"[,\w]+", x.strip("[] ")))) if x.strip("[] ") else 0.0 for x in v]); names.append(p["c"] + "#n")
        else:
            for lv in p["lv"]:
                cols.append([1.0 if x == lv else 0.0 for x in v]); names.append("%s=%s" % (p["c"], lv))
    return np.array(cols, float).T, names


def fit_tabular(text, mp, out, notes):
    rd = csv.DictReader(io.StringIO(text))
    cols = [c for c in rd.fieldnames if c]
    data = list(rd)[: bt.MAX_ROWS]
    m = ingest.detect(cols, mp)
    if "label" not in m:
        raise ValueError("no label column found. Pass --map label=<your column>. Columns: %s" % ", ".join(cols[:40]))
    yl = [ingest._label(r.get(m["label"], "")) for r in data]
    keep = [i for i, v in enumerate(yl) if v is not None]
    data, y = [data[i] for i in keep], np.array([1.0 if yl[i] in ("1", "2") else 0.0 for i in keep])
    if y.sum() < MIN_POS or y.sum() == len(y):
        raise ValueError("only %d fraud rows out of %d. Need at least %d fraud rows in train and 5 in each other split." % (y.sum(), len(y), MIN_POS))
    ts = None
    if "ts" in m:
        t = [ingest._ts(r.get(m["ts"])) for r in data]
        if sum(v is not None for v in t) >= 0.9 * len(t):
            ts = np.array([v if v is not None else np.nan for v in t])
            ts = np.where(np.isnan(ts), np.nanmedian(ts), ts)
            for r, v in zip(data, ts):
                d = ingest.dt.datetime.fromtimestamp(v, ingest.IST)
                r["_hour"], r["_dow"] = str(d.hour), str(d.weekday())
        else:
            notes.append("timestamp column %r is not readable (%d%% parsed), so it is ignored and the split is random" % (m["ts"], 100 * sum(v is not None for v in t) // len(t)))
    skip = {m["label"]} | ({m["ts"]} if "ts" in m else set())
    leak_by_name = [c for c in cols if c not in skip and ingest.LEAK.search(c)]
    skip |= set(leak_by_name)
    plan = _plan(cols + (["_hour", "_dow"] if ts is not None else []), data, y, skip)
    X, names = _apply(plan, data)
    # leakage by value: one column that alone predicts the label is almost certainly derived from it
    auc = [max(mdl.roc_auc(y, X[:, j]), 1 - mdl.roc_auc(y, X[:, j])) if X[:, j].std() > 0 else 0.5 for j in range(X.shape[1])]
    sus = [names[j] for j in range(len(names)) if auc[j] > 0.985]
    if sus:
        ok = [j for j in range(len(names)) if auc[j] <= 0.985]
        X, names = X[:, ok], [names[j] for j in ok]
        plan = [p for p in plan if not any(s == p["c"] or s.startswith(p["c"] + "=") or s == p["c"] + "#n" for s in sus)]
    if leak_by_name or sus:
        notes.append("excluded as label leakage (they give the answer away): %s" % ", ".join(leak_by_name + sus))
    if X.shape[1] == 0:
        raise ValueError("no usable feature columns left")
    n = len(y)
    if ts is not None:
        o = np.argsort(ts, kind="stable")
        rk = np.empty(n, int); rk[o] = np.arange(n)
        tr, va, te = rk < 0.65 * n, (rk >= 0.65 * n) & (rk < 0.8 * n), rk >= 0.8 * n
        kind = "time-ordered"
    else:
        rng = np.random.RandomState(7)
        u = rng.rand(n)
        tr, va, te = u < 0.65, (u >= 0.65) & (u < 0.8), u >= 0.8
        kind = "RANDOM (no usable time column; scores are optimistic if the same customers appear on both sides)"
        notes.append("random split: no time ordering available")
    _check_split(y, tr, va, te, kind)
    amt = np.array([max(_num(r.get(m["amt"], "")) or 0.0, 0.0) for r in data]) if "amt" in m else np.full(n, 1000.0)
    if "amt" not in m:
        notes.append("no amount column: the approve/step-up/decline cost policy assumes a flat Rs 1,000 per payment")
    chan = np.array([ingest._chan(r.get(m.get("chan", ""), ""), "upi") for r in data])
    print("tabular: %d rows, %d features, %d fraud (%.2f%%); split %s" % (n, X.shape[1], y.sum(), 100 * y.mean(), kind.split(" (")[0]))
    g = mdl.GAM(names).fit(X[tr], y[tr], X[va], y[va], log=lambda *a: None)
    lr = mdl.LR().fit(X[tr], y[tr])
    rep = _report(g, lr, X, y, tr, va, te, amt, chan, np.zeros(n, bool), np.zeros(n, int), names, kind, notes, dict(path="tabular"))
    d = g.dump()
    d.update(path="tabular", plan=plan, label=m["label"], has_time=ts is not None)
    os.makedirs(out, exist_ok=True)
    json.dump(d, open(os.path.join(out, "model.json"), "w"))
    return g, rep


# ---------------------------------------------------------------- predict (tabular models)

def predict(art, csv_path, out_path):
    d = json.load(open(os.path.join(art, "model.json")))
    g = mdl.GAM.load(d)
    if d.get("path") != "tabular":
        raise ValueError("this model was fitted on event history; score new files with:  FH_ART=%s python -m fh.backtest <file>" % art)
    rd = csv.DictReader(open(csv_path, encoding="utf-8-sig", errors="replace"))
    data = list(rd)
    if d.get("has_time"):
        mt = ingest.detect(rd.fieldnames or []).get("ts")
        for r in data:
            t = ingest._ts(r.get(mt, "")) if mt else None
            if t:
                dd = ingest.dt.datetime.fromtimestamp(t, ingest.IST)
                r["_hour"], r["_dow"] = str(dd.hour), str(dd.weekday())
    X, names = _apply(d["plan"], data)
    if names != d["names"]:
        raise ValueError("this file's columns do not match the ones the model was trained on")
    p = g.predict(X)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["row", "fraud_probability", "top_reasons"])
        for i in range(len(p)):
            _, c = g.contrib(X[i].tolist())
            top = sorted(range(len(c)), key=lambda j: -c[j])[:3]
            w.writerow([i + 2, "%.5f" % p[i], "; ".join("%s %+.2f" % (names[j], c[j]) for j in top if c[j] > 0)])
    print("%d rows scored -> %s" % (len(p), out_path))


# ---------------------------------------------------------------- cli

def run(text, out, mp=None, mode="auto", chan=None, city=None):
    notes = []
    path = mode
    canon = None
    if mode in ("auto", "events"):
        try:
            canon, irep = ingest.convert(text, mp, chan, city)
            notes += irep["notes"]
            if "label" not in irep["mapped"]:
                raise ValueError("no label column found. Pass --map label=<your column>.")
            if irep["mapped"].get("uid") and "mid" in irep["mapped"] or mode == "events":
                path = "events"
            else:
                path = "tabular"
                notes.append("no payee column, so the events path would have no payee graph; used the tabular path")
        except ValueError as e:
            if mode == "events" or "label" in str(e):
                raise
            path = "tabular"
            notes.append("events path unavailable (%s); using the tabular path" % e)
    if path == "events":
        rows, bad = bt.parse(canon)
        notes += [b for b in bad if "unknown or missing category" not in b][:5]
        g, rep = fit_events(rows, out, notes)
    else:
        g, rep = fit_tabular(text, mp or {}, out, notes)
    rep["notes"] = notes
    json.dump(rep, open(os.path.join(out, "report.json"), "w"), indent=1, default=float)
    return g, rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fit the fraud model to your CSV.")
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--out", default="artifacts_csv")
    ap.add_argument("--map", default="")
    ap.add_argument("--mode", choices=["auto", "events", "tabular"], default="auto")
    ap.add_argument("--chan"); ap.add_argument("--city")
    ap.add_argument("--predict", metavar="MODEL_DIR", help="score a CSV with a tabular model saved earlier (needs the csv argument)")
    a = ap.parse_args(argv)
    if a.predict:
        return predict(a.predict, a.csv, a.out if a.out != "artifacts_csv" else "scored.csv")
    if not a.csv:
        ap.error("give a csv")
    t = time.time()
    ov = dict(p.split("=", 1) for p in a.map.split(",") if "=" in p)
    try:
        g, rep = run(open(a.csv, encoding="utf-8-sig", errors="replace").read(), a.out, ov, a.mode, a.chan, a.city)
    except ValueError as e:
        sys.exit("fit: %s" % e)
    _show(rep)
    print("\nsaved %s/model.json + report.json in %.0fs" % (a.out, time.time() - t))


if __name__ == "__main__":
    main()
