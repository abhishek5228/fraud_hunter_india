"""Models and metrics, numpy only.

GAM: a cyclic Newton-boosted generalized additive model (an Explainable-Boosting-style
model fitted from scratch). logit(x) = b0 + sum_j f_j(x_j). Because it is additive,
each feature's contribution to a score is *exact*, not an approximation like SHAP on a
black box. LR is the baseline.
"""
import math
import bisect

import numpy as np


def sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def logloss(y, p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def curves(y, p):
    """ROC and PR points at distinct thresholds (tie-safe)."""
    o = np.argsort(-p, kind="mergesort")
    ys, ps = y[o], p[o]
    tp, fp = np.cumsum(ys), np.cumsum(1 - ys)
    k = np.r_[np.where(np.diff(ps) != 0)[0], len(ps) - 1]
    tp, fp, th = tp[k], fp[k], ps[k]
    P, N = max(tp[-1], 1), max(fp[-1], 1)
    tpr, fpr, prec = tp / P, fp / N, tp / np.maximum(tp + fp, 1)
    return fpr, tpr, prec, th


def roc_auc(y, p):
    fpr, tpr, _, _ = curves(y, p)
    return float(np.trapezoid(np.r_[0, tpr], np.r_[0, fpr]))


def avg_prec(y, p):
    _, tpr, prec, _ = curves(y, p)
    return float(np.sum(np.diff(np.r_[0, tpr]) * prec))


def recall_at_fpr(y, p, f=0.01):
    fpr, tpr, _, _ = curves(y, p)
    i = np.searchsorted(fpr, f, side="right") - 1
    return float(tpr[max(i, 0)])


def calib(y, p, edges=(0, .005, .01, .02, .05, .1, .2, .4, .7, 1.0001)):
    rows, ece = [], 0.0
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b)
        if m.sum():
            rows.append(dict(lo=a, hi=min(b, 1), n=int(m.sum()), pred=float(p[m].mean()), obs=float(y[m].mean())))
            ece += m.sum() / len(p) * abs(p[m].mean() - y[m].mean())
    return rows, float(ece)


class GAM:
    def __init__(s, names):
        s.names = list(names)

    def bins(s, X):
        return np.stack([np.searchsorted(s.edges[j], X[:, j], side="right") for j in range(X.shape[1])], 1)

    def fit(s, X, y, Xv, yv, rounds=900, lr=0.06, lam=20.0, nb=24, log=print):
        n, d = X.shape
        s.edges = []
        for j in range(d):
            u = np.unique(X[:, j])
            if len(u) <= 2:
                e = (u[:-1] + u[1:]) / 2
            else:
                e = np.unique(np.quantile(X[:, j], np.linspace(0, 1, nb + 1)[1:-1]))
            s.edges.append(e)
        B, Bv = s.bins(X), s.bins(Xv)
        s.nb = [len(e) + 1 for e in s.edges]
        s.sh = [np.zeros(k) for k in s.nb]
        pr = float(y.mean())
        s.b0 = math.log(pr / (1 - pr))
        F, Fv = np.full(n, s.b0), np.full(len(yv), s.b0)
        best = (1e9, None, 0)
        for rd in range(rounds):
            for j in range(d):
                p = sig(F)
                g, h = p - y, p * (1 - p) + 1e-9
                bj = B[:, j]
                G, H = np.bincount(bj, g, s.nb[j]), np.bincount(bj, h, s.nb[j])
                dl = -lr * G / (H + lam)
                s.sh[j] += dl
                F += dl[bj]
                Fv += dl[Bv[:, j]]
            ll = logloss(yv, sig(Fv))
            if ll < best[0] - 1e-6:
                best = (ll, [a.copy() for a in s.sh], rd)
            elif rd - best[2] > 12:
                break
            if rd % 10 == 0:
                log("  gam round %3d  val logloss %.5f" % (rd, ll))
        s.sh = best[1]
        log("  gam best round %d  val logloss %.5f" % (best[2], best[0]))
        s.center(B)
        s.lists()
        return s

    def center(s, B):
        """Center each shape function on the training distribution; push the offset into b0."""
        for j in range(len(s.sh)):
            cnt = np.bincount(B[:, j], minlength=s.nb[j])
            m = float((s.sh[j] * cnt).sum() / cnt.sum())
            s.sh[j] = s.sh[j] - m
            s.b0 += m

    def lists(s):
        s.el = [e.tolist() for e in s.edges]
        s.sl = [a.tolist() for a in s.sh]

    def logit(s, X):
        B = s.bins(X)
        return s.b0 + sum(s.sh[j][B[:, j]] for j in range(B.shape[1]))

    def predict(s, X):
        return sig(s.logit(X))

    # single-row python path: this is the hot loop of the live engine
    def contrib(s, v):
        c = [s.sl[j][bisect.bisect_right(s.el[j], v[j])] for j in range(len(v))]
        return s.b0 + sum(c), c

    def dump(s):
        return dict(names=s.names, b0=s.b0, edges=s.el, shapes=s.sl)

    @staticmethod
    def load(d):
        g = GAM(d["names"])
        g.b0 = d["b0"]
        g.edges = [np.array(e) for e in d["edges"]]
        g.sh = [np.array(a) for a in d["shapes"]]
        g.nb = [len(a) for a in g.sh]
        g.lists()
        return g


class LR:
    def fit(s, X, y, l2=1.0, it=12):
        s.mu, s.sd = X.mean(0), X.std(0) + 1e-9
        Z = np.c_[(X - s.mu) / s.sd, np.ones(len(X))]
        reg = np.r_[np.ones(Z.shape[1] - 1), 0.0] * l2
        w = np.zeros(Z.shape[1])
        for _ in range(it):
            p = sig(Z @ w)
            g = Z.T @ (p - y) + reg * w
            H = (Z.T * (p * (1 - p) + 1e-6)) @ Z + np.diag(reg)
            w -= np.linalg.solve(H, g)
        s.w = w
        return s

    def predict(s, X):
        return sig(np.c_[(X - s.mu) / s.sd, np.ones(len(X))] @ s.w)
