"""The browser and the server read the same shield_rules.json. This proves they also AGREE on what it means (regex dialects differ in places)."""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from fh import shield


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_and_server_match_the_same_rules_on_every_fixture_text():
    texts = json.load(open(os.path.join(HERE, "fixtures", "shield_texts.json"), encoding="utf-8"))
    out = subprocess.run(["node", os.path.join(HERE, "shield_parity.mjs")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    py = [sorted(r["id"] for r in shield.check(t)["reasons"] if r["id"] not in ("complaints", "fan_in", "owner_mismatch")) for t in texts]
    bad = [(t[:60], a, b) for t, a, b in zip(texts, js, py) if a != b]
    assert not bad, bad[:3]
    assert len(texts) >= 50
