"""Smoke-test the optional LLM wording of analyst briefs against the REAL API, with your key.

    ANTHROPIC_API_KEY=sk-... python tools/check_llm.py        (FH_LLM_MODEL=... to try another model)

Sends one fixture case (no real customer data), prints what came back, and exits 1 if it fell back to the template, which means the
key, the model name or the network is wrong. The key is never printed.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import copilot

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("set ANTHROPIC_API_KEY first")
case = dict(id="fixture", ts=1793433679, uid="rz_fixture", mid="mu***@paytm", cat="p2p", amt=45000, chan="upi", city="Patna", score=93, dec=2, dname="DECLINE",
            hits=[dict(code="MULE_PAYEE", msg="Payee linked to 3 recent fraud complaints", lvl=2)], top=[dict(txt="First payment to this payee", c=1.2)])
b = copilot.brief(case, llm=True)
print("model:", os.environ.get("FH_LLM_MODEL", "claude-sonnet-5-5"))
print("source:", b["source"])
print(b["en"])
sys.exit(0 if b["source"] == "llm" else 1)
