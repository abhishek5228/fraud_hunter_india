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


def test_haversine_mumbai_to_delhi_is_about_1150_km():
    assert 1130 < geo.hav(19.08, 72.88, 28.61, 77.21) < 1170
    assert geo.hav(19.08, 72.88, 19.08, 72.88) == 0


def test_ingest_maps_channel_words_to_rails():
    assert ingest._chan("CASH_OUT", "upi") == "atm"
    assert ingest._chan("NEFT", "upi") == "imps"
    assert ingest._chan("Debit Card", "upi") == "ecom"
    assert ingest._chan("", "upi") == "upi"


def test_ingest_maps_places_to_known_cities():
    assert ingest._city("Bangalore") == "Bengaluru"
    assert ingest._city("Bihar") == "Patna"
    assert ingest._city("Mars") is None


def test_ingest_reads_fraud_labels():
    assert ingest._label("TRUE") == "1" and ingest._label("legit") == "0"
    assert ingest._label("2") == "2" and ingest._label("maybe") is None
