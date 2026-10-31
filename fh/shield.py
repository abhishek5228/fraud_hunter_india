"""Scam Shield: paste a message, a UPI handle or a QR/link and get a plain-language verdict before paying.

Rules live in shield_rules.json, shared word-for-word with the browser (web/shield.js), so the static demo and the server
agree. It checks wording and structure. It cannot tell who owns a handle, so it never says 'safe'. It says
'no known scam pattern found' and why that is not a guarantee.

Optionally combines the text verdict with what this engine knows about the payee (fan-in of first-time senders, fraud complaints).
"""
import json
import os
import re
import urllib.parse

_R = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shield_rules.json"), encoding="utf-8"))
RULES = [dict(r, rx=re.compile(r["re"], re.I)) for r in _R["rules"]]
VPA = re.compile(r"\b[a-z0-9._\-]{2,}@[a-z]{2,}\b", re.I)
EMAIL_DOMAINS = {"gmail", "yahoo", "outlook", "hotmail", "rediffmail", "icloud", "proton", "protonmail"}


def expand(text):
    """upi://pay?pa=x@y&pn=Name&am=500 -> readable text the rules can see (payee handle, name, amount)."""
    out = [text]
    for m in re.finditer(r"upi://[^\s]+", text, re.I):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(m.group(0)).query)
        out.append(" ".join("%s %s" % (k, v[0]) for k, v in q.items() if k in ("pa", "pn", "tn") and v))
    return " ".join(out)


def handles(text):
    return [h for h in VPA.findall(text) if h.split("@")[1].lower() not in EMAIL_DOMAINS]


def check(text, net=None):
    """net: optional dict(fan_in=int, complaints=int) from the live engine. Returns a verdict dict."""
    t = expand(text or "")
    hit = []
    for r in RULES:
        m = r["rx"].search(t)
        if m:
            hit.append(dict(id=r["id"], w=r["w"], en=r["en"], hi=r["hi"], seen=m.group(0)[:70]))
    if net:
        n = _R["network"]
        if net.get("complaints", 0) >= n["complaints"]["min"]:
            hit.append(dict(id="complaints", w=n["complaints"]["w"], en=n["complaints"]["en"] % net["complaints"], hi=n["complaints"]["hi"] % net["complaints"], seen=""))
        if net.get("fan_in", 0) >= n["fan_in"]["min"]:
            hit.append(dict(id="fan_in", w=n["fan_in"]["w"], en=n["fan_in"]["en"] % net["fan_in"], hi=n["fan_in"]["hi"] % net["fan_in"], seen=""))
    keep = 1.0
    for h in hit:
        keep *= 1 - h["w"] / 100.0                      # noisy-OR: independent warning signs add up but never exceed 100
    score = round(100 * (1 - keep))
    lv = "danger" if score >= _R["levels"]["danger"] else "caution" if score >= _R["levels"]["caution"] else "none"
    hit.sort(key=lambda h: -h["w"])
    return dict(score=score, level=lv, reasons=hit, handles=handles(t), actions=_R["actions"][lv], version=_R["version"])
