"""Offline pipeline: simulate history, stream it through the feature store exactly as production
would, split by *time*, fit GAM (+LR baseline), evaluate, and save artifacts.

    python -m fh.train
"""
import os
import json
import time
import heapq
import pickle
import random
import sys

import numpy as np

from . import feat, model, policy, rules
from .gen import World, T0, DAY, TYPS

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
DAYS, T_TRAIN, T_VAL = 42, 22, 30


def stream(w, r, days=DAYS):
    evs = w.window(r, T0, T0 + days * DAY)
    st, pend = feat.Store(), []
    X, Y, M, F, H = [], [], [], [], []
    for k, x in enumerate(evs):
        while pend and pend[0][0] <= x["ts"]:
            due, _, rx = heapq.heappop(pend)
            st.report(rx, due)
        v, raw = st.feats(x)
        X.append(v)
        Y.append(x["lab"])
        M.append((x["ts"], x["amt"], x["typ"], x["chan"], bool(x["pers"])))
        hh = rules.check(x, raw, st)
        F.append(rules.level(hh))
        H.append("+".join(h[1] for h in hh))
        st.commit(x, upd=not x["lab"])
        if x["lab"] and r.random() < 0.8:
            heapq.heappush(pend, (x["ts"] + r.uniform(3600, 43200), k, x))
        if k % 20000 == 0:
            st.prune(x["ts"])
    return st, np.array(X), np.array(Y, float), M, np.array(F), np.array(H)


def evaluate(y, p, amt, typ, frc, cfg, k):
    fpr, tpr, prec, _ = model.curves(y, p)
    keep = np.unique(np.linspace(0, len(fpr) - 1, 220).astype(int))
    app, stp, dec = policy.costs(p, amt, cfg, k)
    d = np.argmin(np.stack([app, stp, dec]), 0)
    d = np.maximum(d, frc)
    cal, ece = model.calib(y, p)
    rows = {}
    for t in sorted(set(typ)):
        m = typ == t
        rows[t] = dict(n=int(m.sum()), flagged=float((d[m] > 0).mean()), declined=float((d[m] == 2).mean()))
    return dict(
        auc=model.roc_auc(y, p), ap=model.avg_prec(y, p), rec1=model.recall_at_fpr(y, p, 0.01),
        rec01=model.recall_at_fpr(y, p, 0.001), ll=model.logloss(y, p), ece=ece, calib=cal,
        pr=dict(rec=tpr[keep].tolist(), prec=prec[keep].tolist()), slices=rows,
        n=int(len(y)), npos=int(y.sum()),
    ), d


def main(seed=7):
    t = time.time()
    w, r = World(seed), random.Random(seed + 1)
    print("simulating + streaming %d days ..." % DAYS)
    st, X, Y, M, F, H = stream(w, r)
    ts = np.array([m[0] for m in M])
    amt = np.array([m[1] for m in M])
    typ = np.array([m[2] for m in M])
    chan = np.array([m[3] for m in M])
    kk = policy.kvec(chan, amt, np.array([m[4] for m in M]))
    print("  %d txns, %d fraud (%.2f%%)  [%.1fs]" % (len(Y), Y.sum(), 100 * Y.mean(), time.time() - t))
    burn = ts >= T0 + 7 * DAY   # burn-in: the first week is cold start, every payee looks new
    tr, va, te = burn & (ts < T0 + T_TRAIN * DAY), (ts >= T0 + T_TRAIN * DAY) & (ts < T0 + T_VAL * DAY), ts >= T0 + T_VAL * DAY
    print("fitting GAM  train=%d val=%d test=%d" % (tr.sum(), va.sum(), te.sum()))
    g = model.GAM(feat.NAMES).fit(X[tr], Y[tr], X[va], Y[va])
    lr = model.LR().fit(X[tr], Y[tr])
    cfg = policy.Cfg()
    pg, pl = g.predict(X[te]), lr.predict(X[te])
    rep, dec = evaluate(Y[te], pg, amt[te], typ[te], F[te], cfg, kk[te])
    repl, _ = evaluate(Y[te], pl, amt[te], typ[te], F[te], cfg, kk[te])
    rep["lr"] = {k: repl[k] for k in ("auc", "ap", "rec1", "rec01", "ll", "ece")}
    # rules-only baseline: how good are guardrails on their own?
    rep["rules_only"] = dict(recall=float(((F[te] > 0) & (Y[te] == 1)).sum() / max(Y[te].sum(), 1)),
                             fpr=float(((F[te] > 0) & (Y[te] == 0)).sum() / max((Y[te] == 0).sum(), 1)))
    Btr = g.bins(X[tr])
    rep["importance"] = sorted([dict(f=n, v=float(np.abs(g.sh[j][Btr[:, j]]).mean())) for j, n in enumerate(feat.NAMES)], key=lambda a: -a["v"])
    Bva = g.bins(X[va])   # drift reference = the most recent period the model saw, when customer profiles had matured
    rep["ref"] = {n: (np.bincount(Bva[:, j], minlength=g.nb[j]) / len(Bva)).tolist() for j, n in enumerate(feat.NAMES)}
    rep["ref_n"] = int(len(Bva))
    rep["split"] = dict(train=int(tr.sum()), val=int(va.sum()), test=int(te.sum()), days=DAYS)
    os.makedirs(ART, exist_ok=True)
    json.dump(g.dump(), open(os.path.join(ART, "model.json"), "w"))
    json.dump(rep, open(os.path.join(ART, "report.json"), "w"))
    np.savez_compressed(os.path.join(ART, "holdout.npz"), p=pg, amt=amt[te], y=Y[te], typ=typ[te], frc=F[te], k=kk[te], chan=chan[te])
    pickle.dump((w, st), open(os.path.join(ART, "world.pkl"), "wb"))
    print("GAM  AUC %.4f  AP %.4f  recall@1%%FPR %.3f  recall@0.1%%FPR %.3f  ECE %.4f" % (rep["auc"], rep["ap"], rep["rec1"], rep["rec01"], rep["ece"]))
    print("LR   AUC %.4f  AP %.4f  recall@1%%FPR %.3f" % (repl["auc"], repl["ap"], repl["rec1"]))
    print("rules only: recall %.3f  fpr %.4f" % (rep["rules_only"]["recall"], rep["rules_only"]["fpr"]))
    y = Y[te]
    n0 = (y == 0).sum()
    print("policy: approve %.2f%%  step %.2f%%  decline %.2f%%  | fraud caught(any action) %.1f%%  legit touched %.2f%%" % (
        100 * (dec == 0).mean(), 100 * (dec == 1).mean(), 100 * (dec == 2).mean(),
        100 * ((dec > 0) & (y == 1)).sum() / y.sum(), 100 * ((dec > 0) & (y == 0)).sum() / n0))
    for k, v in rep["slices"].items():
        print("   %-11s n=%6d flagged %.3f declined %.3f" % (k, v["n"], v["flagged"], v["declined"]))
    print("done in %.0fs -> %s" % (time.time() - t, ART))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
