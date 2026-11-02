import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import shield  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from fh import api
    with TestClient(api.app) as c:
        yield c


def test_shadow_mode_tells_the_caller_approve_but_remembers_what_it_would_have_done(client, monkeypatch):
    u = client.get("/api/users?n=1").json()[0]
    risky = dict(uid=u["uid"], amt=42000, cat="crypto", chan="ecom", city="Dubai", dev="never-seen", ip="203.1.2.3", commit=False)
    live = client.post("/api/score", json=risky).json()
    assert live["dec"] > 0 and "shadow" not in live                    # off by default
    monkeypatch.setenv("FH_SHADOW", "1")
    before = client.get("/api/shadow").json()
    sh = client.post("/api/score", json=risky).json()
    assert sh["dec"] == 0 and sh["shadow"] is True and sh["enforced"] is False
    assert sh["would_have"]["dec"] == live["dec"] and sh["would_have"]["codes"]
    after = client.get("/api/shadow").json()
    assert after["on"] and after["scored"] == before["scored"] + 1
    assert after["would_step_up"] + after["would_decline"] == before["would_step_up"] + before["would_decline"] + 1
    assert after["amount_that_would_have_been_stopped"] >= before["amount_that_would_have_been_stopped"] + 42000
    assert client.get("/api/integrations").json()["shadow"] is True


def test_tokens_fold_links_and_digits_and_stay_ascii():
    assert shield.tokens("Pay Rs 4999 at https://x.in/a?b=1 now") == ["pay", "rs", "0", "at", "urltok", "now", "pay_rs", "rs_0", "0_at", "at_urltok", "urltok_now"]
    assert shield.tokens("नमस्ते hello") == ["hello"]


def test_learned_part_flags_smishing_wording_and_leaves_ordinary_text_alone(monkeypatch):
    smish = "USPS: your package is on hold. Confirm your delivery address at http://usps-track.xyz/a to avoid return."
    ok = "Hi, see you at lunch tomorrow? Bring the notes."
    assert any(r["id"] == "text_model" for r in shield.check(smish)["reasons"])
    assert not any(r["id"] == "text_model" for r in shield.check(ok)["reasons"])
    monkeypatch.setattr(shield, "_R", {k: v for k, v in shield._R.items() if k != "model"})
    assert shield.model_p(smish) is None and not any(r["id"] == "text_model" for r in shield.check(smish)["reasons"])
