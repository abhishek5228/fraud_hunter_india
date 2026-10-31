"""Smoke-test the optional LLM wording of analyst briefs against the REAL API, with your key.

    GEMINI_API_KEY=... python tools/check_llm.py       or   ANTHROPIC_API_KEY=... python tools/check_llm.py
    (FH_LLM_MODEL=... to try another model; FH_LLM_PROVIDER=gemini|anthropic if both keys are set)

Sends one fixture case (no real customer data), prints what came back, and exits 1 if it fell back to the template, which means the
key, the model name or the network is wrong. The key is never printed.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import copilot

r = copilot.check()
print("provider:", r.get("provider"), "model:", r.get("model"))
print("ok:", r["ok"])
print(r.get("text") or r.get("error"))
sys.exit(0 if r["ok"] else 1)
