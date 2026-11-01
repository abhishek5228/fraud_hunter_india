"""Edge cases for the guardrail rules: where a rule should and should not fire."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import feat, rules

RAW = dict(pers=False, nmer=False, chan="upi", kmh=0, km=0, sm5=0, devu=0, mbad=0, dbad=0, ibad=0, ratf=False, sim=1e4, ndev=False, fan=0, lim=False, coll=False)


def codes(amt=500, chan="upi", **raw):
    x = dict(uid="u", mid="m@upi", amt=amt, chan=chan, dev=None, ip=None)
    return {h[1] for h in rules.check(x, dict(RAW, chan=chan, **raw), feat.Store())}
