"""Cost-sensitive decision policy.

Instead of one global score threshold, every transaction gets the action with the lowest
*expected cost*, so the bar rises with the amount at stake and falls with customer friction.
Works on python floats and numpy arrays alike.
"""
from dataclasses import dataclass, asdict, fields

NAMES = ["APPROVE", "STEP_UP", "DECLINE"]


@dataclass
class Cfg:
    fee: float = 15.0     # fixed cost per fraud: chargeback fee + ops
    loss: float = 1.0     # share of the amount lost when fraud is approved
    marg: float = 0.06    # margin lost on a lost sale
    churn: float = 20.0   # churn/support cost of wrongly declining a good customer
    step: float = 2.5     # cost of issuing a challenge (SMS + friction)
    lpass: float = 0.94   # good customers who pass a challenge
    fpass: float = 0.08   # fraudsters who pass a challenge
    risk: float = 1.0     # risk-aversion multiplier on fraud cost

    def dict(self):
        return asdict(self)

    def update(self, d):
        ok = {f.name for f in fields(self)}
        for k, v in d.items():
            if k in ok:
                setattr(self, k, float(v))
        return self


def costs(p, a, c):
    fr = c.risk * (c.loss * a + c.fee)
    app = p * fr
    stp = c.step + (1 - p) * (1 - c.lpass) * (c.marg * a + 0.5 * c.churn) + p * c.fpass * fr
    dec = (1 - p) * (c.marg * a + c.churn)
    return app, stp, dec


def pick(app, stp, dec):
    if app <= stp and app <= dec:
        return 0
    return 1 if stp <= dec else 2
