"""Small unit tests for helper functions."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import fmt, geo, ingest, shield


def test_inr_uses_indian_digit_grouping():
    assert fmt.inr(18500, 0) == "₹18,500"
    assert fmt.inr(2500000, 0) == "₹25,00,000"
    assert fmt.inr(180.5, 2) == "₹180.50"
    assert fmt.inr(1.04e7, 0) == "₹1,04,00,000"
