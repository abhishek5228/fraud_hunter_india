"""Cross-bank mule sharing without sharing customers.

Each member turns a flagged payee into a keyed hash (HMAC-SHA256 with a key all members hold) and exports only the hashes,
with a count and a signature. A member who imports the feed can recognise a payee it has never seen, and learns nothing else:
no names, no amounts, no accounts, no senders.

Honest limits. Phone numbers and VPAs have low entropy, so anyone holding the key can test guesses against the hashes; the key
is therefore a membership secret and the feed must travel over an authenticated channel. A production design would use private
set intersection or a hosted registry with legal agreements (this is the idea behind I4C's suspect registry, not a replacement).
"""
import hashlib
import hmac
import json
import os
import time

MAX_AGE = 7 * 86400


def key():
    k = os.environ.get("FH_CONSORTIUM_KEY", "")
    return k.encode() if k else None


def tag(mid, k=None):
    k = k or key()
    return hmac.new(k, ("payee:" + str(mid).strip().lower()).encode(), hashlib.sha256).hexdigest()[:20] if k else None


def _sig(body, k):
    return hmac.new(k, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()


def export(st, now, bank, min_complaints=2, min_fan=6, k=None, ts=None):
    """Hashes of payees this bank has strong evidence against. Only evidence counts, never mere novelty."""
    k = k or key()
    if not k:
        raise ValueError("FH_CONSORTIUM_KEY is not set")
    items = {}
    for kk, q in st.bad.items():
        if kk.startswith("m:"):
            n = st.nbad(kk, now)
            if n >= min_complaints:
                items[tag(kk[2:], k)] = dict(h=tag(kk[2:], k), n=n)
    for pay, snd in st.pu.items():
        fan = sum(1 for t in snd.values() if 0 <= now - t <= 7 * 86400)
        if fan >= min_fan and st.nbad("m:" + pay, now) >= 1:
            h = tag(pay, k)
            items[h] = dict(h=h, n=max(items.get(h, {}).get("n", 0), st.nbad("m:" + pay, now)))
    body = dict(bank=bank, ts=int(ts or time.time()),   # wall-clock time for freshness; `now` only windows the evidence
                 items=sorted(items.values(), key=lambda i: i["h"]))
    return dict(body, sig=_sig(body, k))


def ingest(st, feed, now=None, k=None):
    """Verify and load a peer's feed into this bank's store. Returns how many hashes were new."""
    k = k or key()
    if not k:
        raise ValueError("FH_CONSORTIUM_KEY is not set")
    now = now or time.time()
    try:
        body = {x: feed[x] for x in ("bank", "ts", "items")}
        sig = feed["sig"]
    except (KeyError, TypeError):
        raise ValueError("not a consortium feed (needs bank, ts, items, sig)")
    if not hmac.compare_digest(_sig(body, k), str(sig)):
        raise ValueError("signature does not verify: wrong key, or the feed was altered")
    if not (-300 <= now - body["ts"] <= MAX_AGE):
        raise ValueError("feed is stale or from the future (older than 7 days)")
    cons = st.__dict__.setdefault("cons", {})
    new = 0
    for it in body["items"]:
        h = it["h"]
        if h not in cons:
            new += 1
        cons[h] = dict(bank=str(body["bank"])[:40], n=int(it.get("n", 1)), ts=body["ts"])
    return new
