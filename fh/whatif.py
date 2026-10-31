"""Offline policy lab: replay the held-out period under any cost configuration, vectorised."""
import numpy as np

from . import policy


def decide(p, a, f, c):
    return np.maximum(np.argmin(np.stack(policy.costs(p, a, c)), 0), f)


def realised(dec, y, a, c):
    """Expected realised $ outcome of a decision vector under cost config c (risk aversion is a
    steering knob, not a real cost, so it is excluded here)."""
    F, L = y == 1, y == 0
    stop = np.where(dec == 2, 1.0, np.where(dec == 1, 1 - c.fpass, 0.0))
    leak_amt = (a * F * (1 - stop)).sum()
    leak_n = (F * (1 - stop)).sum()
    lose = np.where(dec == 2, 1.0, np.where(dec == 1, 1 - c.lpass, 0.0))
    fric = np.where(dec == 1, c.step, 0.0).sum()
    lost = (L * lose * (c.marg * a + np.where(dec == 2, c.churn, 0.5 * c.churn))).sum()
    cost = c.loss * leak_amt + c.fee * leak_n + lost + fric
    return dict(
        cost=float(cost), leak=float(leak_amt), leak_pct=float(leak_amt / max((a * F).sum(), 1)),
        bps=float(1e4 * leak_amt / a.sum()), lost=float(lost), fric=float(fric),
        approve=float((dec == 0).mean()), step=float((dec == 1).mean()), decline=float((dec == 2).mean()),
        touched=float(((dec > 0) & L).sum() / max(L.sum(), 1)), declined_legit=float(((dec == 2) & L).sum() / max(L.sum(), 1)),
        caught=float(((dec > 0) & F).sum() / max(F.sum(), 1)),
    )


def lab(h, cfg):
    p, a, y, f = h["p"], h["amt"], h["y"], h["frc"]
    c = policy.Cfg(**{k: v for k, v in cfg.dict().items()})
    cur = realised(decide(p, a, f, c), y, a, c)
    naive = realised(np.where(p > 0.5, 2, 0), y, a, c)         # one global threshold, no step-up
    nomod = realised(np.maximum(0, f), y, a, c)                 # rules only
    allow = realised(np.zeros_like(f), y, a, c)                 # approve everything
    front = []
    for r in np.exp(np.linspace(np.log(0.1), np.log(10), 21)):
        c2 = policy.Cfg(**{**c.dict(), "risk": float(r)})
        m = realised(decide(p, a, f, c2), y, a, c)
        front.append(dict(risk=float(r), cost=m["cost"], bps=m["bps"], touched=m["touched"], caught=m["caught"]))
    grid = np.exp(np.linspace(np.log(1e-4), 0, 1500))
    thr = []
    for amt in (5, 25, 100, 500, 2000, 8000):
        d = np.argmin(np.stack(policy.costs(grid, np.full_like(grid, amt), c)), 0)
        s = grid[np.argmax(d >= 1)] if (d >= 1).any() else 1.0
        k = grid[np.argmax(d >= 2)] if (d >= 2).any() else 1.0
        thr.append(dict(amt=amt, step=float(s), decline=float(k)))
    typ = {}
    d = decide(p, a, f, c)
    for t in sorted(set(h["typ"])):
        m = h["typ"] == t
        typ[str(t)] = dict(n=int(m.sum()), fraud=bool(y[m].max()), flagged=float((d[m] > 0).mean()), declined=float((d[m] == 2).mean()))
    return dict(cfg=c.dict(), cur=cur, naive=naive, rules=nomod, allow=allow, front=front, thr=thr, typ=typ, n=int(len(y)))
