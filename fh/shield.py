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


def qr_name(text):
    """The payee name a QR or request claims (the pn= field of a upi:// link), or None."""
    for m in re.finditer(r"upi://[^\s]+", text or "", re.I):
        v = urllib.parse.parse_qs(urllib.parse.urlparse(m.group(0)).query).get("pn")
        if v:
            return v[0]
    return None


def names_match(a, b):
    """Loose match of two names: do they share a meaningful word (3+ letters)? 'SBI Refund' vs 'STATE BANK OF INDIA' does not match."""
    tok = lambda s: {w for w in re.findall(r"[a-z]{3,}", (s or "").lower()) if w not in {"the", "and", "pvt", "ltd", "limited", "private", "shri", "smt", "mr", "mrs"}}
    return bool(tok(a) & tok(b))


def owner_lookup(handle, fetch=None):
    """Who is this handle registered to? Uses Razorpay's validate-VPA API when RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are set
    (the feature must be enabled on your Razorpay account). Returns the registered name, or None. Never raises."""
    import base64
    import urllib.error
    import urllib.request
    kid, sec = os.environ.get("RAZORPAY_KEY_ID"), os.environ.get("RAZORPAY_KEY_SECRET")
    if not (kid and sec):
        return None
    try:
        if fetch:
            d = fetch(handle)
        else:
            tok = base64.b64encode(("%s:%s" % (kid, sec)).encode()).decode()
            req = urllib.request.Request("https://api.razorpay.com/v1/payments/validate/vpa", json.dumps({"vpa": handle}).encode(),
                                         {"Authorization": "Basic " + tok, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as r:
                d = json.loads(r.read(20000))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return (d.get("customer_name") or None) if isinstance(d, dict) and d.get("success") else None


def check(text, net=None, owner=None):
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
    claimed = qr_name(text)
    if owner and claimed and not names_match(owner, claimed):
        n = _R["network"]["owner_mismatch"]
        hit.append(dict(id="owner_mismatch", w=n["w"], en=n["en"] % (owner, claimed), hi=n["hi"] % (owner, claimed), seen=""))
    keep = 1.0
    for h in hit:
        keep *= 1 - h["w"] / 100.0                      # noisy-OR: independent warning signs add up but never exceed 100
    score = round(100 * (1 - keep))
    lv = "danger" if score >= _R["levels"]["danger"] else "caution" if score >= _R["levels"]["caution"] else "none"
    hit.sort(key=lambda h: -h["w"])
    return dict(score=score, level=lv, reasons=hit, handles=handles(t), actions=_R["actions"][lv], version=_R["version"], owner=owner)
