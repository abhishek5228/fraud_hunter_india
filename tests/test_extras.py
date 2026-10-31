import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fh import shield, graph, consortium, copilot, feat


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fh import api
    with TestClient(api.app) as c:
        yield c


# ---- scam shield
@pytest.mark.parametrize("text,level", [
    ("Your electricity connection will be disconnected tonight as bill not updated. Call 9876543210 immediately", "danger"),
    ("Sir KYC expire ho gaya, abhi AnyDesk download karo aur OTP bata do", "danger"),
    ("CBI officer on video call: your parcel has drugs, transfer money to safe account", "danger"),
    ("upi://pay?pa=sbi.refund.support@ybl&pn=SBI&am=5000", "caution"),
    ("Approve the collect request to get your refund", "caution"),
    ("Pay Rs 500 to kirana store ramesh@okaxis for milk", "none"),
    ("Lunch at 2? send the notes to abc@gmail.com", "none"),
])
def test_shield_levels(text, level):
    r = shield.check(text)
    assert r["level"] == level, (r["score"], [x["id"] for x in r["reasons"]])
    assert r["actions"] and all(x["hi"] and x["en"] for x in r["reasons"])


def test_shield_never_claims_safe_and_extracts_handles():
    r = shield.check("pay ramesh@okaxis and mail me at a@gmail.com")
    assert r["handles"] == ["ramesh@okaxis"] and "not a guarantee" in r["actions"]["en"][0]


def test_shield_network_evidence_raises_the_score():
    base = shield.check("pay ramesh@okaxis")
    net = shield.check("pay ramesh@okaxis", dict(fan_in=5, complaints=2))
    assert base["level"] == "none" and net["level"] == "danger" and net["score"] > base["score"]


def test_shield_rules_json_is_shared_with_the_browser():
    import json
    j = json.load(open(os.path.join(os.path.dirname(shield.__file__), "shield_rules.json"), encoding="utf-8"))
    assert len(j["rules"]) == len(shield.RULES) and all(r["en"] and r["hi"] for r in j["rules"])


def test_shield_api_is_public_and_rate_limited(client):
    r = client.post("/api/shield", json=dict(text="share your OTP now"))
    assert r.status_code == 200 and r.json()["level"] in ("caution", "danger")
    assert client.post("/api/shield", json=dict(text="  ")).status_code == 422
    from fh import api
    api.RATE.clear()
    codes = [client.post("/api/shield", json=dict(text="hello")).status_code for _ in range(45)]
    assert 429 in codes and codes[0] == 200
    api.RATE.clear()


# ---- mule graph
def _store():
    st = feat.Store()
    for i in range(6):
        st.pu["mule1@paytm"]["u%d" % i] = 1000.0 + i
    st.pu["shop@upi"]["u9"] = 1000.0
    st.bad["m:mule1@paytm"].extend([1000.0, 1001.0])
    st.u["u0"] = feat.Prof(); st.u["u1"] = feat.Prof()
    st.u["u0"].devs.add("devX"); st.u["u1"].devs.add("devX")
    st.du["devX"] = {"u0": 1000.0, "u1": 1000.0}
    return st


def test_graph_finds_the_hub_and_masks_it():
    g = graph.build(_store(), 2000.0)
    c = g["clusters"][0]
    assert g["total"] == 1 and c["senders"] == 6 and c["complaints"] == 2 and c["level"] == "high" and "mule1" not in c["payee"]
    assert len(c["devices"]) == 1 and set(c["devices"][0]["senders"]) == {"u0", "u1"}


def test_graph_ignores_old_activity():
    assert graph.build(_store(), 1000.0 + 9 * 86400)["total"] == 0


def test_graph_api(client):
    r = client.get("/api/graph").json()
    assert "clusters" in r and r["total"] >= 0


# ---- consortium
KEY = b"k" * 16


def test_consortium_roundtrip_hides_identity_and_blocks_at_peer():
    a = _store()
    feed = consortium.export(a, 2000.0, "bank-a", k=KEY)
    assert feed["items"] and "mule1" not in str(feed) and "u0" not in str(feed)
    b = feat.Store()
    assert consortium.ingest(b, feed, k=KEY) == len(feed["items"])
    os.environ["FH_CONSORTIUM_KEY"] = KEY.decode()
    try:
        from fh import rules
        hits = rules.check(dict(uid="zz", mid="mule1@paytm", amt=500, chan="upi", dev=None, ip=None),
                           dict(pers=True, nmer=True, chan="upi", kmh=0, km=0, sm5=0, devu=0, mbad=0, dbad=0, ibad=0, ratf=False, sim=1e4, ndev=False, fan=0, lim=False, coll=False), b)
        assert any(h[1] == "CONSORTIUM_MULE" for h in hits)
    finally:
        del os.environ["FH_CONSORTIUM_KEY"]


def test_consortium_rejects_tamper_wrong_key_and_stale():
    feed = consortium.export(_store(), 2000.0, "bank-a", k=KEY)
    st = feat.Store()
    bad = dict(feed, items=feed["items"] + [dict(h="f" * 20, n=9)])
    with pytest.raises(ValueError, match="signature"):
        consortium.ingest(st, bad, k=KEY)
    with pytest.raises(ValueError, match="signature"):
        consortium.ingest(st, feed, k=b"x" * 16)
    old = consortium.export(_store(), 2000.0, "bank-a", k=KEY, ts=time.time() - 9 * 86400)
    with pytest.raises(ValueError, match="stale"):
        consortium.ingest(st, old, k=KEY)
    assert not st.cons


def test_consortium_api_needs_key(client, monkeypatch):
    monkeypatch.delenv("FH_CONSORTIUM_KEY", raising=False)
    assert client.get("/api/consortium").json()["on"] is False
    assert client.post("/api/consortium/export").status_code == 503
    monkeypatch.setenv("FH_CONSORTIUM_KEY", "sharedsecret12345")
    f = client.post("/api/consortium/export?bank=A").json()
    assert f["bank"] == "A" and "sig" in f
    assert client.post("/api/consortium/import", json=dict(f, bank="tampered")).status_code == 422


# ---- copilot
CASE = dict(id="t1", ts=1793433679, uid="rz_ab", mid="mu***@paytm", cat="p2p", amt=45000, chan="upi", city="Patna", score=93, dec=2, dname="DECLINE",
            hits=[dict(code="MULE_PAYEE", msg="Payee linked to 3 recent fraud complaints", lvl=2)], top=[dict(txt="First payment to this payee", c=1.2)])


def test_copilot_template_is_complete_and_marks_itself_a_draft():
    b = copilot.brief(CASE)
    assert "₹45,000" in b["en"] and "declined" in b["en"] and b["source"] == "template" and "₹45,000" in b["hi"]
    assert "DRAFT" in b["str"] and "not the FIU-IND" in b["str"] and "1930" in b["str"] and "[BANK NAME" in b["str"]


def test_copilot_llm_cannot_add_numbers_or_leak_follow_ups(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    seen = []
    ok = copilot.brief(CASE, True, call=lambda k, p: seen.append(p) or "Declined a ₹45,000 UPI payment at 93% risk; payee linked to complaints.")
    assert ok["source"] == "llm" and "rz_ab" in seen[0] and "ANTHROPIC" not in seen[0]
    bad = copilot.brief(CASE, True, call=lambda k, p: "Declined ₹45,000 at 93% risk and 777 other cases")
    assert bad["source"].startswith("template") and "777" not in bad["en"]
    def boom(k, p): raise OSError("down")
    assert copilot.brief(CASE, True, call=boom)["source"].startswith("template")


def test_brief_api_needs_existing_case(client):
    assert client.get("/api/case/nope/brief").status_code == 404
    cid = client.post("/api/score", json=dict(uid=next(iter(__import__("fh.api", fromlist=["S"]).S["eng"].st.u)), mid="x@upi", amt=900, chan="upi", city="Mumbai", commit=False)).json()["id"]
    assert "en" in client.get("/api/case/%s/brief" % cid).json()


# ---- fairness
def test_fairness_report_shape_and_flags_are_defined(client):
    r = client.get("/api/fairness").json()
    assert r["legit_n"] > 1000 and 0 < r["base"] < 0.2 and any(s["group"] == "Rail" for s in r["segments"])
    for s in r["segments"]:
        if s["flag"]:
            assert s["n"] >= r["min_n"] and s["ratio"] >= 1.5 and s["lo"] > r["base"]   # 99% bound is stricter than the 95% one shown


# ---- sdk
def test_python_sdk_against_the_real_app(client):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sdk", "python"))
    from fraudhunter import FraudHunter, FraudHunterError
    from fh import api
    def tx(method, path, body, headers, timeout):
        r = client.request(method, path, json=body, headers=headers)
        return r.status_code, r.json()
    fh = FraudHunter("http://x", transport=tx)
    u = next(iter(api.S["eng"].st.u))
    d = fh.score(uid=u, amt=900, mid="x@upi", city="Mumbai", commit=False)
    assert d.decision in ("APPROVE", "STEP_UP", "DECLINE") and 0 <= d.risk <= 100 and d.id
    assert fh.shield("share your OTP")["level"] in ("caution", "danger")
    with pytest.raises(FraudHunterError) as e:
        fh.score(uid=u, amt=-5, city="Mumbai")
    assert e.value.status == 422
    calls = []
    def flaky(method, path, body, headers, timeout):
        calls.append(path)
        raise OSError("down")
    with pytest.raises(FraudHunterError):
        FraudHunter("http://x", transport=flaky, retries=2).score(uid="a", amt=5, city="Mumbai", commit=True)
    assert len(calls) == 1                       # a committed score is never retried
    calls.clear()
    with pytest.raises(FraudHunterError):
        FraudHunter("http://x", transport=flaky, retries=2).score(uid="a", amt=5, city="Mumbai", commit=False)
    assert len(calls) == 3
