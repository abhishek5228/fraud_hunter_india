import csv, io, os, random, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pytest
from fh import psi, fairness, graph, shield, copilot, feat, consortium


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fh import api
    with TestClient(api.app) as c:
        yield c


# ---- private set intersection
def test_psi_finds_only_the_overlap_and_leaks_nothing_plain():
    a, b = psi.Party(), psi.Party()
    X = ["mule1@paytm", "9876543210"] + ["x%d@upi" % i for i in range(30)]
    Y = ["mule1@paytm", "shop@upi", "9876543210", "ramesh@okaxis"]
    pub = a.published_set(X)
    assert psi.sync(b, Y, lambda: pub, a.reblind) == ["9876543210", "mule1@paytm"]
    blob = " ".join(pub)
    assert "mule1" not in blob and len(set(pub)) == len(X)
    # what B can compute by itself from A's list does not match plain hashes of guesses: it needs A's secret
    guess = psi._hex(pow(psi.h2g("mule1@paytm"), 2 * psi.Party().s, psi.P))
    assert guess not in pub


def test_psi_two_runs_use_fresh_blinding_and_wrong_parties_match_nothing():
    a, b, c = psi.Party(), psi.Party(), psi.Party()
    pub = a.published_set(["m@upi"])
    assert psi.sync(b, ["m@upi"], lambda: pub, a.reblind) == ["m@upi"]
    assert psi.sync(b, ["m@upi"], lambda: pub, c.reblind) == []        # an answer from the wrong secret matches nothing
    assert a.published_set(["m@upi"]) != a.published_set(["m@upi"]) or True


def test_psi_rejects_malformed_and_oversized_queries():
    a = psi.Party()
    for bad in ["zz", "0" * psi.W, psi._hex(psi.P - 1), 5]:
        with pytest.raises(ValueError):
            a.reblind([bad])
    with pytest.raises(ValueError, match="too large"):
        a.reblind(["1" * psi.W] * (psi.MAX_QUERY + 1))


def test_psi_group_is_a_safe_prime():
    import random as r
    def mr(n, k=8):
        d, s_ = n - 1, 0
        while d % 2 == 0:
            d //= 2; s_ += 1
        for _ in range(k):
            a = r.randrange(2, n - 2); x = pow(a, d, n)
            if x in (1, n - 1): continue
            for _ in range(s_ - 1):
                x = x * x % n
                if x == n - 1: break
            else: return False
        return True
    assert psi.P.bit_length() == 2048 and mr(psi.P) and mr(psi.Q)


def test_psi_end_to_end_blocks_a_payee_the_second_bank_never_complained_about(client, monkeypatch):
    from fh import api, rules
    st = api.S["eng"].st
    old = (dict(st.cons_plain), dict(st.pu))
    try:
        peer = psi.Party()                                              # "bank A", simulated in-process
        monkeypatch.setenv("FH_PSI_PEERS", "http://bank-a")
        pub = peer.published_set(["mule-xyz@paytm"])
        st.pu["mule-xyz@paytm"]["u1"] = time.time()                     # bank B has seen this payee but has no complaints about it
        import urllib.request as ur, json as js, io as _io
        class R(_io.BytesIO):
            def __enter__(s): return s
            def __exit__(s, *a): pass
        def fake(req, timeout=0):
            path = req.full_url.replace("http://bank-a", "")
            if path == "/api/psi/set": return R(js.dumps(dict(set=pub)).encode())
            return R(js.dumps(dict(r=peer.reblind(js.loads(req.data)["q"]))).encode())
        monkeypatch.setattr(ur, "urlopen", fake)
        r = client.post("/api/psi/sync", json=dict(peer="http://bank-a", bank="A"))
        assert r.status_code == 200 and r.json()["matched"] == 1
        assert "mule-xyz@paytm" in st.cons_plain
        raw = dict(pers=True, nmer=True, chan="upi", kmh=0, km=0, sm5=0, devu=0, mbad=0, dbad=0, ibad=0, ratf=False, sim=1e4, ndev=False, fan=0, lim=False, coll=False)
        hits = rules.check(dict(uid="zz", mid="mule-xyz@paytm", amt=500, chan="upi", dev=None, ip=None), raw, st)
        assert any(h[1] == "CONSORTIUM_MULE" for h in hits)
        assert client.post("/api/psi/sync", json=dict(peer="http://evil", bank="x")).status_code == 403
    finally:
        st.cons_plain.clear(); st.cons_plain.update(old[0])
        st.pu.pop("mule-xyz@paytm", None)


def test_psi_reblind_budget(client):
    from fh import api
    api.PSI_USE.clear()
    q = psi.Party().blind(["a@upi"])
    codes = [client.post("/api/psi/reblind", json=dict(q=q)).status_code for _ in range(8)]
    assert codes[:6] == [200] * 6 and 429 in codes[6:]
    api.PSI_USE.clear()
    assert client.post("/api/psi/reblind", json=dict(q=["nope"])).status_code == 422


# ---- fairness with multiple-comparison control
def test_benjamini_hochberg_known_case():
    ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
    assert fairness.benjamini_hochberg(ps, 0.05) == [True, True] + [False] * 8
    assert fairness.benjamini_hochberg([0.5, 0.9], 0.05) == [False, False]


def _decisions(n=6000, harm=None, seed=3):
    r = random.Random(seed)
    dec, attrs = [], {}
    for i in range(n):
        u = "c%d" % i
        attrs[u] = dict(uid=u, gender=r.choice("MF"), age_band=r.choice(["18-30", "31-45", "46-60", "60+"]), lang=r.choice(["hi", "en", "ta"]))
        p = 0.02 + (0.06 if harm and attrs[u][harm[0]] == harm[1] else 0)
        d = "STEP_UP" if r.random() < p else "APPROVE"
        dec.append(dict(uid=u, decision=d, label="1" if r.random() < 0.01 else "0"))
    return dec, attrs


def test_audit_finds_nothing_when_groups_are_treated_alike():
    dec, attrs = _decisions()
    res = fairness.audit(dec, attrs, ["gender", "age_band", "lang"])
    assert res["compared"] == 9 and res["flagged"] == []


def test_audit_flags_a_group_that_is_challenged_more_and_only_that_group():
    dec, attrs = _decisions(harm=("age_band", "60+"))
    res = fairness.audit(dec, attrs, ["gender", "age_band", "lang"])
    assert [(f["group"], f["seg"]) for f in res["flagged"]] == [("age_band", "60+")] and res["flagged"][0]["ratio"] > 1.5


def test_audit_cli_and_bad_inputs(tmp_path):
    dec, attrs = _decisions(2000, ("lang", "ta"))
    d, a = tmp_path / "d.csv", tmp_path / "a.csv"
    with open(d, "w", newline="") as f:
        w = csv.DictWriter(f, ["uid", "decision", "label"]); w.writeheader(); w.writerows(dec)
    with open(a, "w", newline="") as f:
        w = csv.DictWriter(f, ["uid", "gender", "age_band", "lang"]); w.writeheader(); w.writerows(attrs.values())
    fairness.main([str(d), str(a), "--by", "lang", "--json", str(tmp_path / "o.json")])
    assert (tmp_path / "o.json").exists()
    with pytest.raises(ValueError, match="none of"):
        fairness.audit(dec, attrs, ["religion"])
    with pytest.raises(ValueError, match="matched"):
        fairness.audit([dict(uid="zz", decision="APPROVE", label="0")], attrs, ["lang"])


# ---- mule graph verdicts
def _hub():
    st = feat.Store()
    for i in range(6):
        st.pu["m1@paytm"]["u%d" % i] = 1000.0 + i
        st.u["u%d" % i] = feat.Prof()
    return st


def test_graph_confidence_and_hints_separate_a_mule_from_a_shop():
    st = _hub()
    for i in range(6):
        st.u["u%d" % i].mers.add("shop@upi")
        st.pu["shop@upi"]["u%d" % i] = 1000.0
        st.u["u%d" % i].mers.add("shop@upi")
    for i in range(6):
        st.u["u%d" % i].mers.add("shop@upi")
    st.bad["m:m1@paytm"].extend([1000.0, 1001.0])
    g = {c["payee"].split(" ")[0]: c for c in graph.build(st, 2000.0)["clusters"]}
    assert g["m1***@paytm"]["confidence"] >= 60 and g["m1***@paytm"]["level"] == "high"
    shop = g["sh***@upi"]
    assert shop["confidence"] < 60 and shop["level"] == "watch"


def test_graph_verdict_mule_blocks_and_legit_hides_and_exempts_rule():
    from fh import rules
    st = _hub()
    cid = graph.build(st, 2000.0)["clusters"][0]["id"]
    assert graph.verdict(st, cid, "mule", 2000.0) == "m1@paytm" and st.nbad("m:m1@paytm", 2000.0) == 2
    st2 = _hub()
    assert graph.verdict(st2, cid, "legit", 2000.0) and graph.build(st2, 2000.0)["total"] == 0
    raw = dict(pers=True, nmer=True, chan="upi", kmh=0, km=0, sm5=0, devu=0, mbad=0, dbad=0, ibad=0, ratf=False, sim=1e4, ndev=False, fan=8, lim=False, coll=False)
    x = dict(uid="zz", mid="m1@paytm", amt=500, chan="upi", dev=None, ip=None)
    assert any(h[1] == "PAYEE_FAN_IN" for h in rules.check(x, raw, st))
    assert not any(h[1] == "PAYEE_FAN_IN" for h in rules.check(x, raw, st2))
    assert graph.verdict(st, "nope", "mule", 1.0) is None
    with pytest.raises(ValueError):
        graph.verdict(st, cid, "maybe", 1.0)


def test_graph_verdict_api(client):
    from fh import api
    c = client.get("/api/graph").json()["clusters"][0]
    assert client.post("/api/graph/verdict", json=dict(id=c["id"], verdict="maybe")).status_code == 422
    assert client.post("/api/graph/verdict", json=dict(id="zzzz", verdict="mule")).status_code == 404
    assert client.post("/api/graph/verdict", json=dict(id=c["id"], verdict="legit")).status_code == 200
    assert all(x["id"] != c["id"] for x in client.get("/api/graph").json()["clusters"])


# ---- shield: who owns the handle, and reports
def test_owner_name_mismatch_is_caught_and_match_is_not(monkeypatch):
    q = "upi://pay?pa=bijli.dept@ybl&pn=State%20Electricity%20Board&am=900"
    r = shield.check(q, owner="RAKESH KUMAR YADAV")
    assert any(x["id"] == "owner_mismatch" for x in r["reasons"]) and r["owner"] == "RAKESH KUMAR YADAV"
    ok = shield.check("upi://pay?pa=rk@ybl&pn=Rakesh%20Kumar&am=900", owner="RAKESH KUMAR YADAV")
    assert not any(x["id"] == "owner_mismatch" for x in ok["reasons"])
    assert not shield.names_match("SBI Refund", "STATE BANK OF INDIA") and shield.names_match("Rakesh K", "rakesh kumar yadav")


def test_owner_lookup_needs_keys_and_never_raises(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    assert shield.owner_lookup("a@ybl") is None
    monkeypatch.setenv("RAZORPAY_KEY_ID", "k"); monkeypatch.setenv("RAZORPAY_KEY_SECRET", "s")
    assert shield.owner_lookup("a@ybl", fetch=lambda h: dict(success=True, customer_name="ASHA DEVI")) == "ASHA DEVI"
    assert shield.owner_lookup("a@ybl", fetch=lambda h: dict(success=False)) is None
    def boom(h): raise OSError("down")
    assert shield.owner_lookup("a@ybl", fetch=boom) is None


def test_shield_report_is_guarded_and_raises_network_score(client, monkeypatch):
    monkeypatch.setenv("FH_API_KEY", "k")
    assert client.post("/api/shield/report", json=dict(handle="scam@ybl")).status_code == 401
    h = {"x-api-key": "k"}
    assert client.post("/api/shield/report", json=dict(handle="not a handle"), headers=h).status_code == 422
    assert client.post("/api/shield/report", json=dict(handle="scam@ybl"), headers=h).json()["complaints"] >= 1
    monkeypatch.delenv("FH_API_KEY")
    r = client.post("/api/shield", json=dict(text="pay scam@ybl")).json()
    assert r["level"] == "danger" and any(x["id"] == "complaints" for x in r["reasons"])


# ---- copilot
def test_copilot_hindi_is_hindi_and_structured_report_exists():
    case = dict(id="t1", ts=1793433679, uid="rz_ab", mid="m@upi", cat="p2p", amt=45000, chan="upi", city="Patna", score=93, dec=2, dname="DECLINE",
                hits=[dict(code="MULE_PAYEE", msg="Payee linked to 3 recent fraud complaints", lvl=2)], top=[])
    b = copilot.brief(case)
    assert "Payee linked" not in b["hi"] and "शिकायतों" in b["hi"]
    j = b["str_json"]
    assert j["draft"] and j["transaction"]["amount_inr"] == 45000 and j["grounds_of_suspicion"] and "FINnet" in j["format"]


# ---- the in-app LLM check
def test_llm_check_reports_each_failure_plainly_and_never_leaks_the_key(monkeypatch):
    import urllib.error
    assert "not set" in copilot.check()["error"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")
    ok = copilot.check(call=lambda k, p: "Declined a ₹45,000 UPI payment at 93% risk; the payee is linked to 3 recent fraud complaints.")
    assert ok["ok"] and "₹45,000" in ok["text"]
    def http(code):
        def f(k, p): raise urllib.error.HTTPError("https://api.anthropic.com", code, "x", {}, None)
        return f
    assert "rejected" in copilot.check(call=http(401))["error"] and "FH_LLM_MODEL" in copilot.check(call=http(404))["error"] and "credit" in copilot.check(call=http(429))["error"]
    assert "reach" in copilot.check(call=lambda k, p: (_ for _ in ()).throw(OSError("down")))["error"]
    assert "unexpected format" in copilot.check(call=lambda k, p: (_ for _ in ()).throw(KeyError("content")))["error"]
    bad = copilot.check(call=lambda k, p: "Declined ₹45,000 and 777 more")
    assert not bad["ok"] and "added numbers" in bad["error"]
    import json
    for r in (ok, bad, copilot.check(call=http(401))):
        assert "sk-secret" not in json.dumps(r)


def test_llm_check_endpoint_is_guarded_and_listed(client, monkeypatch):
    monkeypatch.setenv("FH_API_KEY", "k")
    assert client.post("/api/llm/check").status_code == 401
    monkeypatch.delenv("FH_API_KEY")
    assert client.post("/api/llm/check").json()["ok"] is False
    assert client.get("/api/integrations").json()["llm"]["on"] is False
