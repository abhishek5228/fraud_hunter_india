import random
import numpy as np
import pytest

from fh import feat, model, policy, rules, whatif, explain
from fh.fmt import inr
from fh.gen import World, T0, DAY
from fh.geo import hav


def tx(**k):
    d = dict(ts=T0 + 5 * DAY, uid="u1", mid="mq0001@ybl", cat="grocery", amt=300.0, chan="pos", dev=None, ip=None,
             lat=19.08, lon=72.88, cty="IN", city="Mumbai", pers=False, coll=False, rat=False, sim=1e4, app=False,
             lab=0, typ="legit")
    d.update(k)
    return d


def test_haversine():
    assert abs(hav(19.08, 72.88, 28.61, 77.21) - 1150) < 40
    assert hav(1, 1, 1, 1) == 0


def test_indian_number_grouping():
    assert inr(12345678.5) == "₹1,23,45,678.50"
    assert inr(100000, 0) == "₹1,00,000"
    assert inr(999, 0) == "₹999" and inr(-250000, 0) == "-₹2,50,000"


def test_generator_deterministic_sorted_and_indian():
    a = World(3, nusr=60, nmer=80).window(random.Random(1), T0, T0 + 2 * DAY)
    b = World(3, nusr=60, nmer=80).window(random.Random(1), T0, T0 + 2 * DAY)
    assert a == b and len(a) > 100
    assert all(x["ts"] <= y["ts"] for x, y in zip(a, a[1:]))
    assert {"upi", "pos", "ecom"} <= {e["chan"] for e in a}
    assert sum(e["chan"] == "upi" for e in a) > len(a) * 0.5          # UPI dominates volume
    w = World(3, nusr=60, nmer=80)
    ev = w.window(random.Random(2), T0, T0 + 6 * DAY)
    assert any(e["lab"] for e in ev) and all(e["cty"] == "IN" for e in ev if not e["lab"] and e["typ"] not in ("trip", "vpn"))


def test_festival_surge_raises_volume():
    w = World(3, nusr=80, nmer=80)
    base = len(w.window(random.Random(1), T0, T0 + DAY))
    w.fest = 2.5
    assert len(w.window(random.Random(1), T0, T0 + DAY)) > 1.8 * base


def test_features_do_not_see_the_current_transaction():
    st = feat.Store()
    x = tx()
    v1, _ = st.feats(x)
    v2, _ = st.feats(x)
    assert v1 == v2 and len(v1) == len(feat.NAMES)
    st.commit(x)
    _, raw = st.feats(tx(ts=x["ts"] + 60))
    assert raw["n"] == 1 and raw["c1"] == 1


def test_declined_attempts_stay_out_of_profile_but_in_graph():
    st = feat.Store()
    x = tx(chan="upi", dev="d9", ip="1.2.3.4", pers=True, mid="mu001@ybl")
    st.commit(x, upd=False)
    assert "u1" not in st.u and "u1" in st.du["d9"] and "u1" in st.pu["mu001@ybl"]


def test_fan_in_counts_first_time_strangers_not_friends():
    st = feat.Store()
    for i in range(4):  # four different customers each pay the same personal payee for the first time
        st.commit(tx(uid="v%d" % i, chan="upi", dev="d%d" % i, ip="9.9.%d.1" % i, pers=True, mid="mu001@ybl", ts=T0 + DAY + i))
    st.commit(tx(uid="v0", chan="upi", dev="d0", pers=True, mid="mu001@ybl", ts=T0 + DAY + 100))   # a repeat payment adds nothing
    x = tx(uid="vz", chan="upi", dev="dz", pers=True, mid="mu001@ybl", ts=T0 + DAY + 200)
    _, raw = st.feats(x)
    assert raw["fan"] == 4 and raw["nmer"] == 1
    assert any(h[1] == "PAYEE_FAN_IN" for h in rules.check(x, raw, st))


def test_reports_are_windowed():
    st = feat.Store()
    x = tx(chan="ecom", dev="d9", ip="1.2.3.4")
    st.report(x, T0)
    assert st.nbad("d:d9", T0 + DAY) == 1
    assert st.nbad("d:d9", T0 + 8 * DAY) == 0


def test_authorised_scam_reports_taint_the_payee_not_the_victim_device():
    st = feat.Store()
    x = tx(chan="upi", dev="victim-phone", ip="5.5.5.5", pers=True, mid="mu009@ybl", app=True)
    st.report(x, T0)
    assert st.nbad("m:mu009@ybl", T0 + 1) == 1 and st.nbad("d:victim-phone", T0 + 1) == 0
    st.report(tx(chan="upi", dev="hacked-phone", ip="6.6.6.6", pers=True, mid="mu009@ybl", app=False), T0)
    assert st.nbad("d:hacked-phone", T0 + 1) == 1       # unauthorised fraud does taint the device


def test_impossible_travel_blocks_card_present():
    st = feat.Store()
    st.commit(tx())
    far = tx(ts=T0 + 5 * DAY + 1200, lat=25.20, lon=55.27, cty="AE", city="Dubai")
    _, raw = st.feats(far)
    assert any(h[1] == "IMPOSSIBLE_TRAVEL" and h[0] == rules.BLOCK for h in rules.check(far, raw, st))


def test_vpn_on_known_device_is_only_a_step_up():
    st = feat.Store()
    st.commit(tx())                                                     # in-person at home
    st.commit(tx(ts=T0 + 5 * DAY + 100, chan="upi", dev="mine", ip="10.0.0.1", mid="mq9@ybl"))
    v = tx(ts=T0 + 5 * DAY + 1200, chan="upi", dev="mine", ip="150.1.1.1", lat=51.5, lon=-0.13, cty="GB", mid="mq9@ybl")
    _, raw = st.feats(v)
    hit = [h for h in rules.check(v, raw, st) if h[1] == "IMPOSSIBLE_TRAVEL"]
    assert hit and hit[0][0] == rules.STEP


def test_card_testing_rule():
    st = feat.Store()
    for i in range(4):
        st.commit(tx(ts=T0 + 5 * DAY + 10 * i, amt=1.0, chan="ecom", dev="b", ip="9.9.9.9"))
    x = tx(ts=T0 + 5 * DAY + 50, amt=1.0, chan="ecom", dev="b", ip="9.9.9.9")
    _, raw = st.feats(x)
    assert any(h[1] == "CARD_TESTING" for h in rules.check(x, raw, st))


def test_screen_share_to_a_first_time_person_is_blocked():
    st = feat.Store()
    st.commit(tx(chan="upi", dev="mine", ip="10.0.0.1"))
    x = tx(ts=T0 + 5 * DAY + 600, chan="upi", dev="mine", ip="10.0.0.2", pers=True, rat=True, mid="new@ybl", amt=20000)
    _, raw = st.feats(x)
    assert any(h[1] == "SCREEN_SHARE_NEW_PAYEE" and h[0] == rules.BLOCK for h in rules.check(x, raw, st))


def fit_toy():
    r = np.random.default_rng(0)
    X = r.normal(size=(6000, 4))
    y = (r.random(6000) < 1 / (1 + np.exp(-(2.5 * X[:, 0] + (X[:, 1] > 1) * 2 - 4)))).astype(float)
    g = model.GAM(list("abcd")).fit(X[:4000], y[:4000], X[4000:], y[4000:], rounds=60, log=lambda *a: None)
    return g, X, y


def test_gam_contributions_are_exact():
    g, X, y = fit_toy()
    for row in X[:50]:
        lg, con = g.contrib(row.tolist())
        assert abs(lg - (g.b0 + sum(con))) < 1e-9
        assert abs(lg - float(g.logit(row[None, :])[0])) < 1e-9
    assert model.roc_auc(y[4000:], g.predict(X[4000:])) > 0.8


def test_gam_roundtrip():
    g, X, _ = fit_toy()
    g2 = model.GAM.load(g.dump())
    assert np.allclose(g.logit(X[:100]), g2.logit(X[:100]))


def test_auc_and_ties():
    y = np.array([0, 0, 1, 1.0])
    assert model.roc_auc(y, np.array([.1, .2, .8, .9])) == 1.0
    assert abs(model.roc_auc(y, np.array([.5, .5, .5, .5])) - 0.5) < 1e-9


def test_policy_monotone_in_risk_and_amount_aware():
    c = policy.Cfg()
    ps = np.exp(np.linspace(np.log(1e-5), 0, 400))
    for amt in (50, 800, 9000, 70000):
        d = np.argmin(np.stack(policy.costs(ps, np.full_like(ps, amt), c)), 0)
        assert (np.diff(d) >= 0).all()
    first = lambda a: ps[np.argmax(np.argmin(np.stack(policy.costs(ps, np.full_like(ps, a), c)), 0) >= 1)]
    assert first(50000) < first(500) < first(50)


def test_upi_has_no_margin_to_lose():
    c = policy.Cfg()
    upi, card = policy.costs(0.3, 5000.0, c, policy.RAIL["upi"]), policy.costs(0.3, 5000.0, c, policy.RAIL["pos"])
    assert upi[2] < card[2] and upi[0] == card[0]      # declining a UPI payment forfeits no margin


def test_customer_messages_are_bilingual_and_only_when_needed():
    assert explain.customer_msg(0, 500, "x@ybl", []) is None
    m = explain.customer_msg(2, 12500, "mu03@ybl", ["SCREEN_SHARE_ACTIVE"])
    assert "₹12,500" in m["en"] and "1930" in m["en"] and "screen" in m["en"].lower()
    assert "₹12,500" in m["hi"] and "1930" in m["hi"] and any("ऀ" <= ch <= "ॿ" for ch in m["hi"])


def test_whatif_risk_aversion_trades_fraud_for_friction():
    r = np.random.default_rng(1)
    n = 5000
    p = np.clip(r.beta(0.12, 5, n), 1e-5, 1 - 1e-5)   # calibrated by construction: y ~ Bernoulli(p)
    y = (r.random(n) < p).astype(float)
    a = r.lognormal(6, 1, n)
    h = dict(p=p, amt=a, y=y, frc=np.zeros(n, int), typ=np.where(y == 1, "f", "l"), k=np.ones(n), chan=np.array(["ecom"] * n))
    lo = whatif.lab(h, policy.Cfg(risk=0.2))["cur"]
    hi = whatif.lab(h, policy.Cfg(risk=5.0))["cur"]
    assert hi["caught"] >= lo["caught"] and hi["touched"] >= lo["touched"] and hi["leak"] <= lo["leak"]
    best = whatif.lab(h, policy.Cfg())
    assert best["cur"]["cost"] < best["best1"]["cost"] < best["allow"]["cost"]
    assert best["cur"]["cost"] <= best["best2"]["cost"] * 1.05      # amount-aware is at least as good as tuned tiers


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fh import api
    with TestClient(api.app) as c:
        yield c


def test_api_end_to_end(client):
    assert client.get("/api/health").json()["ok"]
    u = client.get("/api/users?n=1").json()[0]
    ok = client.post("/api/score", json=dict(uid=u["uid"], amt=190.0, cat="grocery", chan="pos", city=u["city"], commit=False)).json()
    assert ok["dname"] in ("APPROVE", "STEP_UP", "DECLINE") and 0 <= ok["p"] <= 1
    bad = client.post("/api/score", json=dict(uid=u["uid"], amt=42000, cat="crypto", chan="ecom", city="Dubai",
                                              dev="never-seen", ip="203.1.2.3", commit=False)).json()
    assert bad["p"] > ok["p"] and bad["dec"] > ok["dec"] and bad["top"] and bad["why"] and len(bad["cost"]) == 3
    assert bad["msg"] and "₹42,000" in bad["msg"]["en"]
    scam = client.post("/api/score", json=dict(uid=u["uid"], amt=38000, cat="p2p", chan="upi", city=u["city"], mid="brand-new@ybl",
                                               dev=u["dev"], ip=u["ip"], rat=True, commit=False)).json()
    assert scam["dec"] == 2 and any(h["code"] == "SCREEN_SHARE_NEW_PAYEE" for h in scam["hits"])
    assert client.post("/api/score", json=dict(uid="x", amt=-5, cat="grocery", city="Mumbai")).status_code == 422
    assert client.post("/api/score", json=dict(uid="x", amt=5, cat="grocery", city="Mumbai", chan="cheque")).status_code == 422
    assert client.get("/api/case/" + bad["id"]).json()["id"] == bad["id"]
    lab = client.post("/api/policy/lab", json={}).json()
    assert lab["cur"]["cost"] < lab["best1"]["cost"] and lab["thr"][0]["upi"]["step"] > 0
    assert client.post("/api/attack", json={"kind": "sim_swap"}).json()["injected"] >= 2
    assert client.post("/api/attack", json={"kind": "nope"}).status_code == 422
    assert client.post("/api/sim", json={"fest": 2.0}).json()["fest"] == 2.0
    client.post("/api/sim", json={"fest": 1.0})
    assert "ready" in client.get("/api/drift").json()
