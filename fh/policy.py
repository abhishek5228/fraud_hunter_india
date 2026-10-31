"""Cost-sensitive decision policy (amounts in rupees).

Instead of one global score threshold, every transaction gets the action with the lowest
*expected cost*, so the bar rises with the amount at stake and falls with customer friction.
Works on python floats and numpy arrays alike.

India specifics. Margin forgone on a lost sale depends on the rail: cards earn a merchant discount
rate (about 1.8% here); UPI person-to-person, IMPS and ATM earn none; UPI merchant payments were
zero-MDR from January 2020 until NPCI's framework effective 15 Oct 2026, which charges 0.4% on specified
merchant payments above Rs 2,000. RBI's customer-protection framework gives customers zero liability
for unauthorised transactions reported within three working days, so the bank usually carries the fraud
loss (`loss` = 1.0).
"""
from dataclasses import dataclass, asdict, fields

import numpy as np

NAMES = ["APPROVE", "STEP_UP", "DECLINE"]
CARD_MDR, UPI_MDR, UPI_MDR_ABOVE = 0.018, 0.004, 2000.0


def rail_k(chan, a, pers):
    """Share of the card margin this payment earns (scalar)."""
    if chan in ("pos", "ecom"):
        return 1.0
    if chan == "upi" and not pers and a > UPI_MDR_ABOVE:
        return UPI_MDR / CARD_MDR
    return 0.0


@dataclass
class Cfg:
    fee: float = 600.0    # fixed cost per fraud: complaint handling, reversal ops, disputes
    loss: float = 1.0     # share of the amount the bank loses when fraud is approved
    marg: float = 0.018   # margin on a card payment (UPI to people, IMPS and ATM earn none)
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


def kvec(chans, amts, pers):
    """Vectorised rail_k."""
    chans, amts, pers = np.asarray(chans), np.asarray(amts, float), np.asarray(pers, bool)
    card = np.isin(chans, ("pos", "ecom"))
    upim = (chans == "upi") & ~pers & (amts > UPI_MDR_ABOVE)
    return np.where(card, 1.0, np.where(upim, UPI_MDR / CARD_MDR, 0.0))


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
