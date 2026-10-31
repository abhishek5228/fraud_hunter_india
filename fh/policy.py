"""Cost-sensitive decision policy (amounts in rupees).

Instead of one global score threshold, every transaction gets the action with the lowest
*expected cost*, so the bar rises with the amount at stake and falls with customer friction.
Works on python floats and numpy arrays alike.

India specifics: UPI P2M carries zero merchant discount rate and IMPS/ATM earn no margin, so a
declined UPI payment forfeits no margin, only customer trust (the `churn` term). RBI's customer
protection framework gives customers zero liability for unauthorised transactions reported within
three working days, so the bank usually carries the fraud loss (`loss` = 1.0).
"""
from dataclasses import dataclass, asdict, fields

import numpy as np

NAMES = ["APPROVE", "STEP_UP", "DECLINE"]
RAIL = {"upi": 0.0, "imps": 0.0, "atm": 0.0, "pos": 1.0, "ecom": 1.0}   # share of the card margin each rail earns


@dataclass
class Cfg:
    fee: float = 600.0    # fixed cost per fraud: complaint handling, reversal ops, disputes
    loss: float = 1.0     # share of the amount the bank loses when fraud is approved
    marg: float = 0.018   # margin on a card payment (UPI / IMPS earn none)
    churn: float = 400.0  # churn/support cost of wrongly declining a good customer
    step: float = 15.0    # cost of issuing a challenge (OTP / PIN re-entry + friction)
    lpass: float = 0.95   # good customers who pass a challenge
    fpass: float = 0.08   # fraudsters assumed to pass a challenge
    risk: float = 1.0     # risk-aversion multiplier on fraud cost

    def dict(self):
        return asdict(self)

    def update(self, d):
        ok = {f.name for f in fields(self)}
        for k, v in d.items():
            if k in ok:
                setattr(self, k, float(v))
        return self


def kvec(chans):
    return np.array([RAIL.get(c, 1.0) for c in chans], dtype=float)


def costs(p, a, c, k=1.0):
    fr = c.risk * (c.loss * a + c.fee)
    m = c.marg * k * a
    app = p * fr
    stp = c.step + (1 - p) * (1 - c.lpass) * (m + 0.5 * c.churn) + p * c.fpass * fr
    dec = (1 - p) * (m + c.churn)
    return app, stp, dec


def pick(app, stp, dec):
    if app <= stp and app <= dec:
        return 0
    return 1 if stp <= dec else 2
