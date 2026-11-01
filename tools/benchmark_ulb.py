"""Benchmark the additive model on a REAL public fraud dataset: the ULB / Worldline credit-card data (284,807 European card transactions, 492 fraud).

    python tools/benchmark_ulb.py /path/to/creditcard.csv [--boot 300]

Same pipeline as `python -m fh.fit` (tabular path), two splits, and three outside baselines from scikit-learn (pip install scikit-learn):
  time-ordered  train on the earliest 65%, validate on the next 15%, test on the latest 20% (the honest one for fraud)
  random        stratified 65 / 15 / 20 (what most published numbers use; optimistic)
The features are the 28 anonymised PCA components and the amount, because that is all the file contains: no customer, device or payee ids,
so this tests the MODEL, not the behavioural feature store that is the project's real strength.
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import model as mdl


def load(path):
    rd = csv.DictReader(open(path, encoding="utf-8"))
    rows = list(rd)
    cols = [c for c in rd.fieldnames if c not in ("Time", "Class")]
    X = np.array([[float(r[c]) for c in cols] for r in rows])
    return X, np.array([float(r["Class"]) for r in rows]), np.array([float(r["Time"]) for r in rows]), cols


def masks_time(ts):
    n = len(ts); o = np.argsort(ts, kind="stable"); rk = np.empty(n, int); rk[o] = np.arange(n)
    return rk < .65 * n, (rk >= .65 * n) & (rk < .8 * n), rk >= .8 * n


def masks_random(y, seed=7):
    rng = np.random.RandomState(seed); tr = np.zeros(len(y), bool); va = tr.copy(); te = tr.copy()
    for c in (0, 1):
        ix = np.where(y == c)[0]; rng.shuffle(ix); a, b = int(.65 * len(ix)), int(.8 * len(ix))
        tr[ix[:a]] = True; va[ix[a:b]] = True; te[ix[b:]] = True
    return tr, va, te


def metrics(y, p):
    return dict(auc=mdl.roc_auc(y, p), ap=mdl.avg_prec(y, p), r1=mdl.recall_at_fpr(y, p, 0.01), r01=mdl.recall_at_fpr(y, p, 0.001))


def boot(y, p, k, seed=1):
    rng = np.random.RandomState(seed); a = []
    for _ in range(k):
        i = rng.randint(0, len(y), len(y))
        if y[i].sum() > 0:
            a.append(mdl.avg_prec(y[i], p[i]))
    return np.percentile(a, [2.5, 97.5])


def run(X, y, names, tr, va, te, label, k):
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    print("\n== %s split: train %d / val %d / test %d, fraud in test %d (%.3f%%)" % (label, tr.sum(), va.sum(), te.sum(), y[te].sum(), 100 * y[te].mean()))
    out = {}
    t = time.time(); g = mdl.GAM(names).fit(X[tr], y[tr], X[va], y[va], log=lambda *a: None); out["GAM (this project)"] = (g.predict(X[te]), time.time() - t)
    t = time.time(); lr = mdl.LR().fit(X[tr], y[tr]); out["Logistic regression (this project)"] = (lr.predict(X[te]), time.time() - t)
    sc = StandardScaler().fit(X[tr]); t = time.time()
    m = LogisticRegression(max_iter=2000).fit(sc.transform(X[tr]), y[tr]); out["Logistic regression (scikit-learn)"] = (m.predict_proba(sc.transform(X[te]))[:, 1], time.time() - t)
    t = time.time(); m = HistGradientBoostingClassifier(random_state=0).fit(X[tr], y[tr]); out["Gradient boosting (scikit-learn)"] = (m.predict_proba(X[te])[:, 1], time.time() - t)
    t = time.time(); m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, n_jobs=-1, random_state=0).fit(X[tr], y[tr]); out["Random forest (scikit-learn)"] = (m.predict_proba(X[te])[:, 1], time.time() - t)
    print("%-38s %7s %7s %17s %9s %9s %7s" % ("model", "AUC", "AP", "AP 95% interval", "rec@1%FPR", "rec@.1%", "fit s"))
    for nm, (p, sec) in out.items():
        mt = metrics(y[te], p); lo, hi = boot(y[te], p, k)
        print("%-38s %7.4f %7.3f %8.3f to %5.3f %8.1f%% %8.1f%% %7.1f" % (nm, mt["auc"], mt["ap"], lo, hi, 100 * mt["r1"], 100 * mt["r01"], sec))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("csv"); ap.add_argument("--boot", type=int, default=300)
    a = ap.parse_args()
    X, y, ts, names = load(a.csv)
    print("%d transactions, %d fraud (%.3f%%), %d features" % (len(y), y.sum(), 100 * y.mean(), X.shape[1]))
    run(X, y, names, *masks_time(ts), "time-ordered", a.boot)
    run(X, y, names, *masks_random(y), "random stratified", a.boot)
