import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fh import integrations as itg


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fh import api
    with TestClient(api.app) as c:
        yield c


def ev(amt=250000, **notes):
    return {"event": "payment.captured", "payload": {"payment": {"entity": dict(
        id="pay_T1", amount=amt, currency="INR", method="upi", status="captured", contact="+919800000001", order_id="order_9",
        created_at=int(time.time()), notes=notes)}}}


def test_signature_roundtrip_and_tamper():
    b = b'{"a":1}'
    s = itg.sign_razorpay(b, "sec")
    assert itg.verify_razorpay(b, s, "sec") and not itg.verify_razorpay(b + b" ", s, "sec")
    assert not itg.verify_razorpay(b, s, "") and not itg.verify_razorpay(b, "", "sec")


def test_mapping_paise_pseudonym_and_skips():
    tx, why = itg.razorpay_to_tx(ev(250000, ip="49.36.1.1", city="Pune"))
    assert tx["amt"] == 2500.0 and tx["chan"] == "upi" and tx["uid"].startswith("rz_") and "9800" not in tx["uid"] and tx["city"] == "Pune"
    assert itg.razorpay_to_tx({"event": "refund.created"})[0] is None
    e = ev(); e["payload"]["payment"]["entity"]["currency"] = "USD"
    assert "non-INR" in itg.razorpay_to_tx(e)[1]


def test_webhook_needs_secret_and_valid_signature(client, monkeypatch):
    body = json.dumps(ev()).encode()
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    assert client.post("/api/webhook/razorpay", content=body).status_code == 503
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "whsec")
    assert client.post("/api/webhook/razorpay", content=body, headers={"x-razorpay-signature": "bad"}).status_code == 401
    ok = client.post("/api/webhook/razorpay", content=body, headers={"x-razorpay-signature": itg.sign_razorpay(body, "whsec")})
    assert ok.status_code == 200 and ok.json()["decision"] in ("APPROVE", "STEP_UP", "DECLINE") and "action" in ok.json()
    w = client.get("/api/wire").json()["events"]
    assert w and w[0]["ref"] == "pay_T1"
    ig = client.get("/api/integrations").json()
    assert ig["razorpay"]["on"] and ig["razorpay"]["bad_sig"] >= 1 and "whsec" not in json.dumps(ig)


def test_replay_ignores_unhandled_event(client):
    r = client.post("/api/webhook/razorpay/replay", json={"event": "order.paid"})
    assert r.status_code == 200 and "ignored" in r.json()


def test_ipintel_parse_cache_failure_and_private():
    calls = []
    f = lambda ip: calls.append(ip) or {"city": "Bangalore", "loc": "12.97,77.59", "country": "IN", "org": "AS16509 Amazon.com"}
    i = itg.IpIntel(token="t", fetch=f)
    a = i.lookup("49.36.1.1")
    assert a["city"] == "Bengaluru" and a["anon"] is True and a["lat"] == 12.97
    i.lookup("49.36.1.1"); assert len(calls) == 1 and i.hits == 1
    assert i.lookup("10.0.0.1") is None and i.lookup("not-an-ip") is None
    def boom(ip): raise OSError("down")
    assert itg.IpIntel(token="t", fetch=boom).lookup("8.8.8.8") is None
    assert itg.IpIntel(token="", fetch=f).lookup("8.8.8.8") is None
    assert itg.IpIntel.parse({"bogon": True}) is None


def test_anon_network_escalates_large_payment_only(client, monkeypatch):
    from fh import api
    monkeypatch.setattr(api.S["ip"], "token", "t")
    monkeypatch.setattr(api.S["ip"], "fetch", lambda ip: {"city": "Mumbai", "loc": "19.08,72.88", "country": "IN", "privacy": {"vpn": True}})
    u = next(iter(api.S["eng"].st.u))
    base = dict(uid=u, mid="x@upi", amt=15000, chan="upi", ip="49.36.2.2", commit=False)
    big = client.post("/api/score", json=base).json()
    small = client.post("/api/score", json=dict(base, amt=500)).json()
    assert big["anon"] and big["dec"] >= 1 and any(h["code"] == "ANON_NETWORK" for h in big["hits"])
    assert not any(h["code"] == "ANON_NETWORK" for h in small["hits"])


def test_notifier_rate_limit_secrets_and_failures(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "9"); monkeypatch.setenv("FH_ALERT_PER_MIN", "2")
    sent = []
    n = itg.Notifier(post=lambda url, body, ct: sent.append(url))
    r = dict(dec=2, amt=9000, chan="upi", score=91, uid="u1", hits=[dict(msg="Payee linked to fraud")], top=[])
    assert n.alert(r) and n.alert(r) and not n.alert(r) and n.dropped == 1
    assert not n.alert(dict(r, dec=0))
    def fail(url, body, ct): raise OSError(url)
    n2 = itg.Notifier(post=fail)
    out = n2.test()
    assert out == {"telegram": "failed: OSError"} and "SECRET" not in json.dumps(out) and "SECRET" not in str(n2.status())


def test_loadtest_endpoint(client):
    r = client.post("/api/loadtest?n=300").json()
    assert r["n"] > 100 and r["p50_us"] > 0 and r["p99_us"] >= r["p50_us"] and r["per_sec"] > 0


def test_lite_plan_response_gives_network_not_city(client, monkeypatch):
    from fh import api
    lite = {"ip": "13.233.1.1", "asn": "AS16509", "as_name": "Amazon.com, Inc.", "country_code": "IN", "country": "India"}
    g = itg.IpIntel.parse(lite)
    assert g["anon"] and g["lat"] is None and g["cty"] == "IN"
    monkeypatch.setattr(api.S["ip"], "token", "t"); monkeypatch.setattr(api.S["ip"], "fetch", lambda ip: lite)
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "k")
    e = ev(40000, ip="13.233.1.1")           # an IP but no city: must not 422
    r = client.post("/api/webhook/razorpay/replay", json=e)
    assert r.status_code == 200 and r.json()["ok"]


def test_huge_payment_from_stranger_is_never_waved_through(client):
    r = client.post("/api/webhook/razorpay/replay", json=ev(2_500_000_00)).json()      # Rs 25 lakh on UPI, customer with no history
    assert r["decision"] == "DECLINE" and "EXCEEDS_UPI_LIMIT" in r["reasons"] and "NEW_CUSTOMER_HIGH_VALUE" in r["reasons"]
    r = client.post("/api/webhook/razorpay/replay", json=ev(250_000_00)).json()       # Rs 2.5 lakh from a stranger
    assert r["decision"] in ("STEP_UP", "DECLINE") and "NEW_CUSTOMER_HIGH_VALUE" in r["reasons"]
