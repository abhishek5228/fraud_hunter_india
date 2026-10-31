import json, os, random, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from fh import fit, ingest


def make(n=4000, seed=3, leak=True, ids=True):
    r = random.Random(seed)
    h = ["Txn_Time", "nameOrig", "nameDest", "Amount", "Type", "State", "isFraud"] + (["fraud_pattern"] if leak else [])
    L = [",".join(h)]
    for i in range(n):
        f = r.random() < 0.05
        amt = r.choice([48000, 95000]) if f else round(r.lognormvariate(6, 1), 2)
        row = ["2026-09-%02d %02d:%02d:00" % (1 + i * 20 // n, r.randrange(24), r.randrange(60)), "C%d" % r.randrange(300),
               ("M%d" % r.randrange(400)) if not f else "M9%d" % r.randrange(3), amt, "PAYMENT" if not f else "CASH_OUT",
               r.choice(["Bihar", "Gujarat", "Kerala"]), int(f)] + (["scam" if f else ""] if leak else [])
        L.append(",".join(map(str, row)))
    return "\n".join(L)


def test_ingest_maps_aliases_and_values():
    txt, rep = ingest.convert(make(200))
    assert rep["mapped"]["uid"] == "nameOrig" and rep["mapped"]["mid"] == "nameDest" and rep["mapped"]["label"] == "isFraud"
    lines = txt.splitlines()
    assert lines[0].startswith("ts,uid,amt,chan") and len(lines) == 201
    assert "atm" in txt            # CASH_OUT -> atm


def test_ingest_refuses_without_required_columns():
    with pytest.raises(ValueError, match="could not find"):
        ingest.convert("a,b\n1,2\n")


def test_ingest_override_and_bad_map():
    with pytest.raises(ValueError, match="no such column"):
        ingest.convert(make(50), {"uid": "nope"})


def test_fit_events_and_leak_never_a_feature():
    with tempfile.TemporaryDirectory() as d:
        g, rep = fit.run(make(), d)
        assert rep["path"] == "events" and rep["auc"] > 0.9
        assert json.load(open(os.path.join(d, "model.json")))["path"] == "events"


def test_fit_tabular_drops_leak_and_predicts():
    with tempfile.TemporaryDirectory() as d:
        g, rep = fit.run(make(), d, mode="tabular")
        assert rep["path"] == "tabular"
        assert any("fraud_pattern" in n for n in rep["notes"])
        assert not any("fraud_pattern" in x["f"] for x in rep["importance"])
        src = os.path.join(d, "in.csv"); open(src, "w").write(make(100, seed=9))
        out = os.path.join(d, "o.csv"); fit.predict(d, src, out)
        assert len(open(out).read().splitlines()) == 101


def test_fit_refuses_when_too_little_fraud():
    with pytest.raises(ValueError, match="fraud rows"):
        with tempfile.TemporaryDirectory() as d:
            fit.run(__import__("re").sub(r",1$", ",0", make(1500, leak=False), flags=__import__("re").M), d, mode="tabular")
