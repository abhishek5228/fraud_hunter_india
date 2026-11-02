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


def test_rule_electricity_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "electricity" in ids('Your electricity connection will be disconnected, update now')
    assert "electricity" not in ids('The electricity board published its tariff')


def test_rule_kyc_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "kyc" in ids('Your KYC has expired, update it')
    assert "kyc" not in ids('Welcome to the school open day')


def test_rule_call_number_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "call_number" in ids('Please call 9876543210 now')
    assert "call_number" not in ids('Our office number is listed on the website')


def test_rule_prize_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "prize" in ids('You have won a lottery of 25 lakh')
    assert "prize" not in ids('The quiz team won the district trophy')


def test_rule_task_job_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "task_job" in ids('Work from home, earn 5000 per day just by completing tasks')
    assert "task_job" not in ids('The project task list is on the board')


def test_rule_short_link_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "short_link" in ids('Claim here https://bit.ly/abc123')
    assert "short_link" not in ids('Read more at https://example.org/guide')


def test_rule_bank_word_bad_tld_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "bank_word_bad_tld" in ids('Update now: https://sbi-kyc-update.xyz/login')
    assert "bank_word_bad_tld" not in ids('Visit https://www.sbi.co.in for branch timings')


def test_rule_official_handle_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "official_handle" in ids('Pay to sbi.refund.support@ybl')
    assert "official_handle" not in ids('Pay to ramesh@okaxis for the milk')


def test_rule_parcel_fee_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "parcel_fee" in ids('Your parcel could not be delivered. Confirm your address to redeliver')
    assert "parcel_fee" not in ids('My parcel arrived yesterday and the delivery guy was nice')


def test_rule_account_locked_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "account_locked" in ids('Your debit card has been temporarily locked due to unusual activity')
    assert "account_locked" not in ids('I locked my bike and left the card at home')


def test_rule_odd_tld_link_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "odd_tld_link" in ids('Claim now at https://refund-center.xyz/claim')
    assert "odd_tld_link" not in ids('See you at the cafe, lol. ok.lol see u later')


def test_rule_tax_refund_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "tax_refund" in ids('The IRS has a tax refund of $573 waiting for you')
    assert "tax_refund" not in ids('I filed my taxes and the refund of my deposit came')


def test_rule_survey_reward_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "survey_reward" in ids('You were randomly selected for a survey, get a reward now')
    assert "survey_reward" not in ids('The survey for the college project is due on friday')


def test_rule_earn_per_day_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "earn_per_day" in ids('Easy work from phone, earn Rs 5000 per day, no experience')
    assert "earn_per_day" not in ids('I earn my salary at the end of the month')


def test_rule_adult_bait_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "adult_bait" in ids('Lisa sent you x-photos. See now: http://mphrbt.com/J24sIRz')
    assert "adult_bait" not in ids('I felt lonely at the hostel last night')


def test_rule_crypto_group_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "crypto_group" in ids('Join our BTC group and earn daily profit of $500')
    assert "crypto_group" not in ids('I read an article about bitcoin history yesterday')


def test_rule_subscription_failed_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "subscription_failed" in ids('Netflix: your payment failed and your account is on hold, update billing')
    assert "subscription_failed" not in ids('I watched Netflix after dinner and paid the bill at home')


def test_rule_reply_then_click_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "reply_then_click" in ids('Reply Y to this message and then open the link to activate')
    assert "reply_then_click" not in ids('Please reply with the time that suits you for the meeting')


def test_rule_brand_with_link_fires_on_a_scam_and_stays_quiet_on_an_innocent_message():
    assert "brand_with_link" in ids('HDFC: your reward points expire soon https://pts.example/claim')
    assert "brand_with_link" not in ids('I ordered from Amazon and it came on time')


def test_ordinary_messages_that_used_to_raise_false_alarms_on_real_sms_stay_quiet():
    """Each of these is the shape of a real ordinary text that an earlier version flagged (found by tools/eval_shield.py)."""
    for text in ["You wont get them til march", "I know you won't be awake before 6",          # 'you won' inside "won't"
                 "put the .apk into some android folder", "In KBC, Amitabh asked the last question for 1 crore",
                 "Eh ok thx.lol.I tot of getting 1", "I'm so lonely today",                       # '.lol' slang is not a web address
                 "Shirin's mother expired. Come home immediately."]:                              # 'expired' about a person
        assert shield.check(text)["level"] == "none", text


def test_real_indian_chat_about_power_cuts_and_locked_accounts_is_not_flagged():
    for t in ("There is power cut in our area since 12 am", "Power went down .. wifi disconnected. Will join once power restored.",
              "It says account is blocked", "I have tried to reset using the tool but my account is locked", "Earlier it said account it blocked for pulse"):
        assert not ids(t) and shield.check(t)["level"] == "none", t
    assert "electricity" in ids("Your electricity bill is overdue, connection will be cut tonight, pay now")
    assert "electricity" in ids("Dear consumer, power connection will be disconnected, update now")
    assert "account_locked" in ids("Dear customer, your account has been locked, verify now")
    assert "kyc" in ids("Your SBI account will be blocked, update PAN today")
