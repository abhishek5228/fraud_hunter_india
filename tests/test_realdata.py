"""The Real data tab's backend, on small synthetic stand-ins for the real files (the real ones are large and not in the repository)."""
import io
import json
import os
import random
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import realdata as rd


REAL_FETCH = rd.fetch


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from fh import api
    monkeypatch.setenv("FH_DATA_DIR", str(tmp_path))
    rd.STATE.clear(); rd.JOBS.clear()
    monkeypatch.setattr(rd, "fetch", lambda i, prog=None: (_ for _ in ()).throw(OSError("offline in tests")))      # tests never touch the network
    with TestClient(api.app) as c:
        yield c, tmp_path


def fake_ulb(path, n=3000, fraud=60, seed=1):
    r = random.Random(seed)
    cols = ["Time"] + ["V%d" % i for i in range(1, 29)] + ["Amount", "Class"]
    with open(path, "w") as f:
        f.write(",".join('"%s"' % c for c in cols) + "\n")
        for i in range(n):
            fr = i % (n // fraud) == 5
            v = [r.gauss(2.0 if (fr and k < 4) else 0, 1) for k in range(28)]
            f.write(",".join(map(str, [i * 40] + v + [round(r.uniform(1, 300), 2), int(fr)])) + "\n")


def wait(c, jid):
    for _ in range(300):
        j = c.get("/api/realdata/job/" + jid).json()
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_status_says_missing_then_present_and_never_calls_a_small_file_verified(client):
    c, d = client
    ls = {x["id"]: x for x in c.get("/api/realdata").json()["datasets"]}
    assert set(ls) == {"ulb", "smishtank", "uci_sms", "nus_sms"} and not any(x["present"] for x in ls.values())
    fake_ulb(d / "creditcard.csv")
    x = {y["id"]: y for y in c.get("/api/realdata?verify=true").json()["datasets"]}["ulb"]
    assert x["present"] and x["counts"] == {"rows": 3000, "pos": 60} and x["verified"] is False       # not the published 284,807 / 492


def test_benchmark_on_a_small_card_file_then_replay_with_the_truth(client):
    c, d = client
    fake_ulb(d / "creditcard.csv")
    r = wait(c, c.post("/api/realdata/run/ulb").json()["job"])
    assert r["state"] == "done", r
    res = r["result"]
    assert res["test_fraud"] >= 5 and {m["name"] for m in res["models"]} >= {"Additive model (this project)"} and all(0 <= m["ap"] <= 1 for m in res["models"])
    rp = c.get("/api/realdata/replay?offset=0&n=50").json()
    assert len(rp["rows"]) == 50 and rp["total"] == res["test"] and {"p", "fraud", "flag", "amt"} <= set(rp["rows"][0])
    jump = c.get("/api/realdata/replay?offset=10&n=20&to_fraud=true").json()
    assert any(x["fraud"] for x in jump["rows"]) and jump["rows"][0]["i"] >= 10
    end = c.get("/api/realdata/replay?offset=%d&n=200" % res["test"]).json()
    assert end["rows"] == [] and end["kpi"]["fraud"] == res["test_fraud"]            # at the end, every real fraud has been counted
    k = end["kpi"]
    assert k["caught"] + k["missed"] == k["fraud"]


def test_replay_and_benchmark_refuse_politely_without_data(client):
    c, _ = client
    assert c.get("/api/realdata/replay").status_code == 409
    j = wait(c, c.post("/api/realdata/run/ulb").json()["job"])
    assert j["state"] == "error" and "could not download" in j["error"]
    assert wait(c, c.post("/api/realdata/run/shield").json()["job"])["state"] == "error"
    assert c.post("/api/realdata/run/nope").status_code == 404 and c.get("/api/realdata/job/zzz").status_code == 404


def test_shield_benchmark_and_real_samples_use_the_files_on_disk(client):
    c, d = client
    (d / "smishtank.csv").write_text("text,label\n" + "\n".join('"Your USPS package is on hold, confirm your address at http://x%d.xyz/a",smish' % i for i in range(60)) + "\n")
    (d / "sms_spam_collection.tsv").write_text("\n".join("ham\tsee you at lunch number %d" % i for i in range(80)) + "\n" + "\n".join("spam\tfree prize you have won a lottery %d" % i for i in range(20)) + "\n")
    r = wait(c, c.post("/api/realdata/run/shield").json()["job"])
    assert r["state"] == "done", r
    res = r["result"]
    assert res["recall"] > 0.5 and res["false_alarm"] == 0 and res["rules"] >= 26 and res["n_smish"] == 30
    s = c.get("/api/realdata/sample?kind=smish").json()
    assert s["truth"] == "smishing" and s["verdict"]["level"] in ("caution", "danger")
    assert c.get("/api/realdata/sample?kind=ham").json()["truth"] == "ordinary"
    assert c.get("/api/realdata/sample?kind=india").status_code == 409 and c.get("/api/realdata/sample?kind=bad").status_code == 422


def test_nus_corpus_is_parsed_message_by_message(client, tmp_path):
    msgs = [{"@id": i, "text": {"$": "hello %d" % i}, "source": {"userProfile": {"country": {"$": "India" if i % 3 == 0 else "SG"}}}} for i in range(120)]
    msgs.append({"@id": 999, "text": {"$": 12345}, "source": {}})                       # a numeric text, as occurs in the real file
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"smsCorpus": {"@date": "x", "message": msgs}}))
    d = rd.load_texts("nus_sms", str(p))
    assert len(d["nus"]) == 121 and len(d["nus_in"]) == 40 and "12345" in d["nus"]


def test_uploads_are_off_without_a_key_and_checked_when_on(client, monkeypatch):
    c, d = client
    monkeypatch.delenv("FH_API_KEY", raising=False); monkeypatch.delenv("FH_ALLOW_UPLOADS", raising=False)
    assert c.post("/api/realdata/smishtank/upload", content=b"x").status_code == 403 and c.get("/api/realdata").json()["uploads"] is False
    monkeypatch.setenv("FH_ALLOW_UPLOADS", "1")
    assert c.post("/api/realdata/smishtank/upload", content=b"").status_code == 422
    assert c.post("/api/realdata/smishtank/upload", content=b"not,a\nreal,file\n").status_code == 422        # too few usable rows
    assert not (d / "smishtank.csv").exists()                                                                  # a bad upload never replaces anything
    ok = c.post("/api/realdata/smishtank/upload", content=("text,label\n" + "\n".join("msg number %d,smish" % i for i in range(80))).encode())
    assert ok.status_code == 200 and ok.json()["status"]["present"] and ok.json()["status"]["counts"]["rows"] == 80
    assert c.post("/api/realdata/nope/upload", content=b"x").status_code == 404
    monkeypatch.setitem(rd.DATASETS["smishtank"], "max_mb", 0.0001)
    assert c.post("/api/realdata/smishtank/upload", content=b"x" * 5000).status_code == 422


def test_upload_needs_the_api_key_when_one_is_set(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("FH_API_KEY", "k")
    assert c.post("/api/realdata/smishtank/upload", content=b"x").status_code == 401
    assert c.post("/api/realdata/run/ulb").status_code == 401
    assert c.post("/api/realdata/smishtank/upload", content=b"", headers={"x-api-key": "k"}).status_code == 422


def test_fetch_downloads_only_from_the_fixed_source_and_enforces_the_limit(client, monkeypatch):
    c, d = client
    monkeypatch.setattr(rd, "fetch", REAL_FETCH)                       # this test exercises the real downloader against a fake network
    seen = []
    class R(io.BytesIO):
        def __enter__(s): return s
        def __exit__(s, *a): pass
    def fake(req, timeout=0):
        seen.append(req.full_url)
        return R(b"text,label\n" + b"\n".join(b"message %d,smish" % i for i in range(70)))
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    r = wait(c, c.post("/api/realdata/smishtank/fetch").json()["job"])
    assert r["state"] == "done" and seen == [rd.DATASETS["smishtank"]["url"]] and (d / "smishtank.csv").exists()
    assert c.post("/api/realdata/evil/fetch").status_code == 404
    monkeypatch.setitem(rd.DATASETS["smishtank"], "max_mb", 0.00001)
    r = wait(c, c.post("/api/realdata/smishtank/fetch").json()["job"])
    assert r["state"] == "error" and "larger than" in r["error"]


def test_only_one_job_runs_at_a_time(client):
    c, _ = client
    assert rd._LOCK.acquire(blocking=False)
    try:
        assert c.post("/api/realdata/run/shield").status_code == 409
    finally:
        rd._LOCK.release()


def test_heavy_endpoints_are_rate_limited_per_ip(client):
    c, _ = client
    from fh import api
    api.RATE.clear()
    codes = [c.post("/api/realdata/evil/fetch").status_code for _ in range(7)]
    assert codes[:4] == [404] * 4 and 429 in codes[4:]
    assert c.get("/api/realdata/replay?n=100000").status_code in (200, 409)   # n is capped, never an error from a huge value


@pytest.fixture(autouse=True)
def _fresh_limits():
    from fh import api
    api.RATE.clear()
    yield
    api.RATE.clear()


def test_benchmarks_fetch_what_a_restarted_server_has_forgotten(client, monkeypatch):
    c, d = client
    got = []
    monkeypatch.setattr(rd, "fetch", lambda i, prog=None: got.append(i) or 1)
    rd.ensure(["ulb", "smishtank"], lambda *a: None)
    assert got == ["ulb", "smishtank"]
    open(rd.path("ulb"), "w").write("x")
    got.clear()
    rd.ensure(["ulb"], lambda *a: None)
    assert got == []                                                   # a file already there is never downloaded again
