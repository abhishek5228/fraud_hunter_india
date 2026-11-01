"""Edge cases for the guardrail rules: where a rule should and should not fire."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import feat, rules

RAW = dict(pers=False, nmer=False, chan="upi", kmh=0, km=0, sm5=0, devu=0, mbad=0, dbad=0, ibad=0, ratf=False, sim=1e4, ndev=False, fan=0, lim=False, coll=False)


def codes(amt=500, chan="upi", **raw):
    x = dict(uid="u", mid="m@upi", amt=amt, chan=chan, dev=None, ip=None)
    return {h[1] for h in rules.check(x, dict(RAW, chan=chan, **raw), feat.Store())}


def test_upi_limit_rule_fires_only_above_ten_lakh():
    assert "EXCEEDS_UPI_LIMIT" not in codes(amt=1_000_000)
    assert "EXCEEDS_UPI_LIMIT" in codes(amt=1_000_001)
    assert "EXCEEDS_UPI_LIMIT" not in codes(amt=2_000_000, chan="imps")


def test_new_customer_high_value_needs_both_a_stranger_and_a_big_amount():
    assert "NEW_CUSTOMER_HIGH_VALUE" in codes(amt=100_000)
    assert "NEW_CUSTOMER_HIGH_VALUE" not in codes(amt=99_999)


def test_card_testing_needs_online_card_tiny_amount_and_a_burst():
    assert "CARD_TESTING" in codes(amt=2, chan="ecom", sm5=3)
    assert "CARD_TESTING" not in codes(amt=2, chan="ecom", sm5=2)
    assert "CARD_TESTING" not in codes(amt=50, chan="ecom", sm5=5)
    assert "CARD_TESTING" not in codes(amt=2, chan="upi", sm5=5)


def test_screen_share_is_ignored_on_small_payments_to_shops_but_not_to_strangers():
    assert "SCREEN_SHARE_ACTIVE" not in codes(amt=40, ratf=True)
    assert "SCREEN_SHARE_ACTIVE" in codes(amt=6000, ratf=True)
    assert "SCREEN_SHARE_NEW_PAYEE" in codes(amt=40, ratf=True, pers=True, nmer=True)
