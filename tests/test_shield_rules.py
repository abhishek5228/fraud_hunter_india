"""One test per Scam Shield rule: a message that should trigger it, and one that should not."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import shield


def ids(text):
    return {r["id"] for r in shield.check(text)["reasons"]}


def test_rule_ask_secret_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "ask_secret" in ids('Please share your OTP with me')
    assert "ask_secret" not in ids('Please share the meeting notes with me')
