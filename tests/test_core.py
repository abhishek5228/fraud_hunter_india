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
    assert st.u["u1"].n == 0 and "u1" in st.du["d9"] and "u1" in st.pu["mu001@ybl"]   # attempt recorded, nothing trusted


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


def test_velocity_counts_every_attempt_even_untrusted_ones():
    st = feat.Store()
    for i in range(3):
        st.commit(tx(ts=T0 + 5 * DAY + 5 * i, amt=1.0, chan="ecom", dev="b", ip="9.9.9.9"), upd=False)   # all declined
    _, raw = st.feats(tx(ts=T0 + 5 * DAY + 30, amt=1.0, chan="ecom", dev="b", ip="9.9.9.9"))
    assert raw["c1"] == 3 and raw["sm5"] == 3 and raw["n"] == 0


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


def test_margin_depends_on_rail_recipient_and_amount():
    assert policy.rail_k("pos", 500, False) == policy.rail_k("ecom", 9000, False) == 1.0
    assert policy.rail_k("upi", 5000, True) == 0.0                 # paying a person earns nothing
    assert policy.rail_k("upi", 1500, False) == 0.0                # small merchant payments stay free
    assert abs(policy.rail_k("upi", 5000, False) - 0.4 / 1.8) < 1e-9   # NPCI 0.4% MDR above Rs 2,000, from 15 Oct 2026
    assert policy.rail_k("imps", 90000, True) == policy.rail_k("atm", 5000, False) == 0.0
    ks = policy.kvec(["pos", "upi", "upi", "upi", "imps"], [500, 5000, 1500, 5000, 9000], [False, False, False, True, True])
    assert np.allclose(ks, [1.0, 0.4 / 1.8, 0.0, 0.0, 0.0])
    c = policy.Cfg()
    free, paid = policy.costs(0.3, 5000.0, c, 0.0), policy.costs(0.3, 5000.0, c, 1.0)
    assert free[2] < paid[2] and free[0] == paid[0]      # declining a margin-free payment forfeits less


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


class _Fake:
    """Stand-in model with a fixed logit, to test engine plumbing without training."""
    names, b0 = feat.NAMES, -3.0

    def __init__(self, logit):
        self.logit = logit

    def contrib(self, v):
        return self.logit, [0.0] * len(v)


def _eng(logit):
    from fh.engine import Engine
    return Engine(_Fake(logit), feat.Store())


def test_step_up_is_two_phase_and_pending_payments_do_not_teach_the_device():
    e = _eng(-2.0)                                                    # p about 12%: a challenge at this amount
    x = tx(chan="upi", dev="bot-dev", ip="9.9.9.9", mid="mq5@ybl", amt=500.0)
    r = e.score(x)
    assert r["dec"] == 1
    assert e.st.u["u1"].n == 0 and not e.st.u["u1"].devs              # pending: attempt counted, nothing trusted
    assert e.confirm(r["id"], False) and e.st.u["u1"].n == 0          # abandoned: still nothing learned
    assert e.confirm(r["id"], True) and "bot-dev" in e.st.u["u1"].devs  # passed: now it is the customer's device
    assert not e.confirm("nope", True)


def test_approved_payments_are_learned_immediately_and_declined_never():
    ok, bad = _eng(-9.0), _eng(9.0)
    assert ok.score(tx(chan="upi", dev="d1", mid="mq5@ybl"))["dec"] == 0 and ok.st.u["u1"].n == 1
    assert bad.score(tx(chan="upi", dev="d1", mid="mq5@ybl", amt=900.0))["dec"] == 2 and bad.st.u["u1"].n == 0


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
    assert lab["cur"]["cost"] < lab["best1"]["cost"] and lab["thr"][0]["upi_p2p"]["step"] > 0
    assert client.post("/api/attack", json={"kind": "sim_swap"}).json()["injected"] >= 2
    assert client.post("/api/attack", json={"kind": "nope"}).status_code == 422
    assert client.post("/api/sim", json={"fest": 2.0}).json()["fest"] == 2.0
    client.post("/api/sim", json={"fest": 1.0})
    assert "ready" in client.get("/api/drift").json()


# ---------------------------------------------------------------- backtest, audit, persistence, auth
def _csv(rows):
    head = "ts,uid,amt,chan,mid,cat,dev,ip,city,pers,coll,rat,sim,label\n"
    return head + "\n".join(",".join(str(v) for v in r) for r in rows) + "\n"


def test_backtest_parse_reports_bad_rows_and_never_guesses():
    from fh import backtest
    t = 1_790_000_000
    rows, bad = backtest.parse(_csv([
        [t, "a", 100, "upi", "m@ybl", "grocery", "d1", "1.1.1.1", "Mumbai", 0, 0, 0, "", 0],
        [t, "a", -5, "upi", "m@ybl", "grocery", "d1", "1.1.1.1", "Mumbai", 0, 0, 0, "", 0],        # negative amount
        [t, "a", 5, "cheque", "m@ybl", "grocery", "d1", "1.1.1.1", "Mumbai", 0, 0, 0, "", 0],      # unknown rail
        [t, "a", 5, "upi", "m@ybl", "grocery", "d1", "1.1.1.1", "Atlantis", 0, 0, 0, "", 0],       # unknown city
        ["2026-10-01T10:00:00+05:30", "b", 5, "upi", "m@ybl", "nonsense", "", "", "Delhi", 1, 0, 0, "", 2],
    ]))
    assert [r["uid"] for r in rows] == ["a", "b"]
    assert sum("line" in b for b in bad) == 3 and any("category" in b for b in bad)
    assert rows[1]["lab"] == 1 and rows[1]["app"] is True and rows[1]["cat"] == "p2p"      # label 2 = authorised scam
    with pytest.raises(ValueError, match="missing required"):
        backtest.parse("ts,uid\n1,a\n")
    with pytest.raises(ValueError, match="location"):
        backtest.parse("ts,uid,amt,chan,mid\n1,a,5,upi,m\n")


def test_backtest_runs_in_isolation_and_reports_impact():
    import json, os
    from fh import backtest, train
    from fh.model import GAM
    g = GAM.load(json.load(open(os.path.join(train.ART, "model.json"))))
    w = World(5, nusr=120, nmer=120)
    ev = w.window(random.Random(3), T0 + 60 * DAY, T0 + 100 * DAY, boost=0.1)
    rows, bad = backtest.parse(_csv([[int(e["ts"]), e["uid"], e["amt"], e["chan"], e["mid"], e["cat"], e["dev"] or "", e["ip"] or "", e["city"], int(e["pers"]),
                                      int(e["coll"]), int(e["rat"]), "", e["lab"]] for e in ev]))
    live = feat.Store()
    sm, out = backtest.run(rows, g)
    assert sm["scored"] + sm["warm"] == sm["n"] == len(out) and sm["warmup_days"] > 0 and sm["labelled"]
    d = sm["decisions"]
    assert d["approve"] + d["step"] + d["decline"] == sm["scored"]
    assert sm["impact"]["cur"]["cost"] < sm["impact"]["allow"]["cost"] and sm["auc"] > 0.9
    assert not live.u                                               # a backtest never touches live state
    assert backtest.to_csv(out).splitlines()[0].startswith("line,ts,uid")


def test_backtest_warns_on_short_files():
    import json, os
    from fh import backtest, train
    from fh.model import GAM
    g = GAM.load(json.load(open(os.path.join(train.ART, "model.json"))))
    t = 1_790_000_000
    rows, _ = backtest.parse(_csv([[t + i * 600, "u%d" % (i % 7), 200, "upi", "m@ybl", "grocery", "d%d" % (i % 7), "1.1.%d.1" % (i % 7), "Pune", 0, 0, 0, "", ""] for i in range(300)]))
    sm, _ = backtest.run(rows, g)
    assert not sm["labelled"] and any("spans" in w for w in sm["warnings"])


def test_audit_log_roundtrip(tmp_path):
    from fh.audit import Audit
    a = Audit(str(tmp_path / "a.db"))
    a.log("score", "t1", "u1", 500.0, "upi", "DECLINE", 0.9, ["MULE_PAYEE"], "abc12345", dict(src="api"))
    a.log("feedback", "t1", detail=dict(verdict="fraud"))
    rows = a.recent(10)
    assert a.count() == 2 and rows[0]["kind"] == "feedback" and rows[1]["codes"] == "MULE_PAYEE" and rows[1]["model"] == "abc12345"
    assert [r["kind"] for r in a.recent(10, "score")] == ["score"]


def test_state_snapshot_roundtrip_and_staleness(tmp_path):
    from fh import persist
    st = feat.Store()
    st.commit(tx(chan="upi", dev="d1", ip="1.2.3.4", pers=True, mid="mu1@ybl"))
    p = str(tmp_path / "state.pkl")
    persist.save(st, p)
    back = persist.load(p)
    assert back.u["u1"].n == 1 and "u1" in back.du["d1"] and "u1" in back.pu["mu1@ybl"]
    assert persist.load(p, newer_than=1e12) is None and persist.load(str(tmp_path / "nope.pkl")) is None
    open(p, "wb").write(b"garbage")
    assert persist.load(p) is None                                  # a corrupt snapshot falls back to the trained state


def test_api_key_guard_queue_audit_and_backtest(client, monkeypatch):
    u = client.get("/api/users?n=1").json()[0]
    body = dict(uid=u["uid"], amt=900.0, cat="p2p", chan="upi", city=u["city"], mid="newguy@ybl", pers=True, dev="never", ip="9.9.9.9", commit=True)
    monkeypatch.setenv("FH_API_KEY", "s3cret")
    assert client.post("/api/score", json=body).status_code == 401
    assert client.post("/api/score", json=body, headers={"x-api-key": "wrong"}).status_code == 401
    assert client.get("/api/audit").status_code == 401 and client.post("/api/backtest", content="x").status_code == 401
    assert client.get("/api/health").json()["auth"] is True        # health stays open
    r = client.post("/api/score", json=body, headers={"x-api-key": "s3cret"})
    assert r.status_code == 200 and r.json()["model"] and len(r.json()["model"]) == 8
    h = {"x-api-key": "s3cret"}
    cid = r.json()["id"]
    if r.json()["dec"] > 0:
        assert cid in [c["id"] for c in client.get("/api/queue", headers=h).json()["cases"]]
        client.post("/api/feedback", json=dict(id=cid, verdict="legit"), headers=h)
        assert cid not in [c["id"] for c in client.get("/api/queue", headers=h).json()["cases"]]
    kinds = [x["kind"] for x in client.get("/api/audit?limit=20", headers=h).json()["rows"]]
    assert "score" in kinds
    bad = client.post("/api/backtest", content="ts,uid\n1,a\n", headers={**h, "content-type": "text/csv"})
    assert bad.status_code == 422 and "could not find" in bad.json()["detail"]
    monkeypatch.delenv("FH_API_KEY")
    assert client.get("/api/audit").status_code == 200              # no key configured: open (development default)


# ---------------------------------------------------------------- red team
def _rt_world():
    return World(5, nusr=80, nmer=100)


def test_redteam_genomes_are_normalised_and_described():
    from fh import redteam as R
    rng = random.Random(1)
    g = R.norm(dict(R.random_genome(rng), split="limit", mult=8))
    assert g["mult"] == 0
    assert R.norm(dict(R.random_genome(rng), n=1, split="random"))["split"] == "equal"
    txt = R.describe(R.random_genome(rng))
    assert "IST" in txt and ("UPI" in txt or "IMPS" in txt)
    seen = {R.key(R.random_genome(rng)) for _ in range(300)}
    assert len(seen) > 250                                              # the search space is genuinely large


def test_redteam_build_respects_limits_and_targets_one_customer():
    from fh import redteam as R
    w = _rt_world()
    u = w.users[3]
    for _ in range(40):
        g = R.random_genome(random.Random(_))
        evs = R.build(w, u, T0, g, random.Random(_))
        assert len(evs) == g["n"] and all(e["uid"] == u["uid"] and e["lab"] == 1 and e["typ"] == "evasive" for e in evs)
        assert all(e["amt"] <= (100000 if e["chan"] == "upi" else 500000) for e in evs)
        assert all(a["ts"] < b["ts"] for a, b in zip(evs, evs[1:]))
    g = dict(R.random_genome(random.Random(2)), split="limit", n=3, rail="upi")
    assert all(47500 <= e["amt"] < 50000 for e in R.build(w, u, T0, R.norm(g), random.Random(1)))


def test_redteam_attack_money_is_an_expectation_and_never_touches_the_real_store():
    from fh import redteam as R
    w = _rt_world()
    st = feat.Store()
    for i in range(30):
        st.commit(tx(uid=w.users[0]["uid"], ts=T0 + i * 3600, chan="upi", dev="d1", ip="1.1.1.1", mid="m@ybl"))
    before = (st.u[w.users[0]["uid"]].n, len(st.pu), len(st.du), len(st.pf))
    g = R.norm(dict(R.random_genome(random.Random(3)), n=3, social=1, split="equal", payee="fresh", rail="upi"))
    evs = R.build(w, w.users[0], T0 + 40 * DAY, g, random.Random(1))
    cfg = policy.Cfg()
    approve, challenge, decline = _eng(-9.0).m, _eng(-2.0).m, _eng(9.0).m
    got, tried, _ = R.attack(approve, st, cfg, evs)
    assert abs(got - tried) < 1e-6                                       # nothing stops it
    got, tried, stopped = R.attack(decline, st, cfg, evs)
    assert got == 0 and stopped == len(evs)
    got, tried, _ = R.attack(challenge, st, cfg, evs)
    assert abs(got - R.SOCIAL_PASS * tried) < 1e-6                       # a tricked customer completes about half the challenges
    g2 = dict(g, social=0)
    got, tried, _ = R.attack(challenge, st, cfg, R.build(w, w.users[0], T0 + 40 * DAY, g2, random.Random(1)))
    assert abs(got - cfg.fpass * tried) < 1e-6                           # an ordinary fraudster gets through far less often
    assert (st.u[w.users[0]["uid"]].n, len(st.pu), len(st.du), len(st.pf)) == before


def test_redteam_search_finds_something_and_reports_honestly():
    from fh import redteam as R
    from fh import api
    g, w, rep, h, eng = api.load()
    r = R.search(g, eng.st, w, seed=3, pop=10, gens=3, k=6, day_ts=T0 + 42 * DAY)
    assert len(r["curve"]) == 3 and r["top"] and r["best"] >= r["baseline"] and r["evaluated"] == 30
    assert all(0 <= t["share"] <= 1.0001 and 0 <= t["caught"] <= 1 for t in r["top"])
    assert len({tuple(t["genome"][k] for k in ("rail", "split", "payee", "dev", "ip", "rat", "sim", "social")) for t in r["top"]}) == len(r["top"])
    assert r["levers"][0]["spread"] >= r["levers"][-1]["spread"]


def test_redteam_episodes_are_labelled_fraud_and_deterministic():
    from fh import redteam as R
    w = _rt_world()
    gs = [R.random_genome(random.Random(i)) for i in range(3)]
    a, b = R.episodes(w, gs, 20, 1), R.episodes(w, gs, 20, 1)
    assert a == b and a and all(e["lab"] == 1 and e["typ"] == "evasive" for e in a)


def test_redteam_api(client, monkeypatch):
    r = client.post("/api/redteam/run", json=dict(seed=2, gens=2, pop=8, victims=4))
    assert r.status_code == 200 and r.json()["curve"] and r.json()["model"]
    assert client.post("/api/redteam/run", json=dict(seed=3, gens=2, pop=8, victims=4)).status_code == 429     # one run at a time, with a pause
    assert client.get("/api/redteam/rounds").status_code in (200, 404)
    monkeypatch.setenv("FH_API_KEY", "k")
    assert client.post("/api/redteam/run", json={}).status_code == 401
    monkeypatch.delenv("FH_API_KEY")
