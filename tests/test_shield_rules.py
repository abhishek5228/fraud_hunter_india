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


def test_rule_pin_to_receive_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "pin_to_receive" in ids('To receive the refund, enter your UPI PIN on the screen')
    assert "pin_to_receive" not in ids('Enter the pin on the keypad to open the locker door')


def test_rule_collect_approve_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "collect_approve" in ids('Approve the collect request to get your refund')
    assert "collect_approve" not in ids('Approve the leave request for next week')


def test_rule_remote_app_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "remote_app" in ids('Download AnyDesk so I can help you')
    assert "remote_app" not in ids('Download the receipt from your email')


def test_rule_apk_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "apk" in ids('Install the app from https://x.example/update.apk')
    assert "apk" not in ids('Open the PDF attachment')


def test_rule_digital_arrest_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "digital_arrest" in ids('This is CBI. You are under digital arrest')
    assert "digital_arrest" not in ids('The museum has a digital art exhibition')


def test_rule_threat_urgent_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "threat_urgent" in ids('Your account will be blocked today unless you act')
    assert "threat_urgent" not in ids('Your table is booked for today at eight')
