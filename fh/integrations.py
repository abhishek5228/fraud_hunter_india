"""Real-world plumbing. Every integration is OFF until its environment variable is set, and none of them can stop scoring.

    RAZORPAY_WEBHOOK_SECRET   verify + accept Razorpay webhooks at POST /api/webhook/razorpay
    IPINFO_TOKEN              resolve a payer IP to city / coordinates / network owner (ipinfo.io)
    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID    push every step-up / decline to a Telegram chat
    SLACK_WEBHOOK_URL         the same, to a Slack incoming webhook
    FH_ALERT_MIN_AMT          only alert at or above this amount in rupees (default 0)
    FH_ALERT_PER_MIN          alert rate limit per minute (default 20; the rest are counted, not sent)

Secrets are read from the environment only. They are never logged, returned by the API, or written to disk.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, deque

HOSTING = ("amazon", "aws", "google cloud", "google llc", "microsoft", "azure", "digitalocean", "ovh", "hetzner", "linode", "vultr",
           "m247", "choopa", "leaseweb", "contabo", "oracle", "alibaba", "tencent", "datacamp", "cloudflare", "nordvpn", "expressvpn",
           "proton", "mullvad", "surfshark", "tor ")
CITY_TO_CANON = {"bangalore": "Bengaluru", "bombay": "Mumbai", "new delhi": "Delhi", "calcutta": "Kolkata", "madras": "Chennai"}


# ------------------------------------------------------------------ Razorpay

def verify_razorpay(body: bytes, signature: str, secret: str) -> bool:
    """Razorpay signs the raw request body with HMAC-SHA256 using the webhook secret (X-Razorpay-Signature, hex)."""
    if not secret or not signature:
        return False
    want = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, signature.strip())


def sign_razorpay(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _pid(s):
    """Stable pseudonymous customer id: raw phone numbers and emails never enter the engine or the audit log."""
    return "rz_" + hashlib.sha256(s.lower().encode()).hexdigest()[:10]


RZ_CHAN = {"upi": "upi", "card": "ecom", "netbanking": "imps", "wallet": "upi", "emi": "ecom", "paylater": "ecom", "bank_transfer": "imps"}
RZ_EVENTS = ("payment.authorized", "payment.captured", "payment.failed")


def razorpay_to_tx(ev: dict):
    """Razorpay webhook JSON -> a transaction for the engine, or (None, reason).

    Razorpay is merchant-side: the payee is always the merchant, so payee-graph signals are weak here and device / network /
    amount / velocity do the work. Merchants can pass richer context through the order or payment `notes`:
    notes.ip, notes.device_id, notes.city, notes.cat. Those are the fields worth adding at checkout.
    """
    name = ev.get("event", "")
    if name not in RZ_EVENTS:
        return None, "event %r is ignored (handled: %s)" % (name, ", ".join(RZ_EVENTS))
    p = (((ev.get("payload") or {}).get("payment") or {}).get("entity")) or {}
    if not p.get("id"):
        return None, "no payment entity in payload"
    if (p.get("currency") or "INR").upper() != "INR":
        return None, "non-INR payment skipped (currency %s)" % p.get("currency")
    amt = (p.get("amount") or 0) / 100.0           # Razorpay amounts are in paise
    if amt <= 0:
        return None, "amount must be positive"
    who = p.get("contact") or p.get("email") or p.get("customer_id") or (p.get("card") or {}).get("id") or p.get("vpa")
    if not who:
        return None, "no contact, email or customer id to identify the payer"
    notes = p.get("notes") if isinstance(p.get("notes"), dict) else {}
    from .gen import CATS
    cat = notes.get("cat") if notes.get("cat") in CATS else "digital"
    ch = RZ_CHAN.get(p.get("method"), "ecom")
    return dict(uid=_pid(str(who)), mid="rzp:" + str(notes.get("merchant") or p.get("order_id") or "merchant")[:40], cat=cat, amt=amt, chan=ch,
                pers=False, ts=float(p.get("created_at") or time.time()), dev=notes.get("device_id") or None, ip=notes.get("ip") or None,
                city=notes.get("city") or None, ref=p["id"], status=p.get("status"), event=name, method=p.get("method")), None


# ------------------------------------------------------------------ IP intelligence

class IpIntel:
    """ipinfo.io lookup with a small cache, a hard timeout, and a guarantee: failure returns None, never an exception."""

    def __init__(self, token=None, fetch=None, ttl=3600, cap=5000):
        self.token, self.ttl, self.cap = token if token is not None else os.environ.get("IPINFO_TOKEN"), ttl, cap
        self.fetch, self.cache, self.hits, self.errs = fetch or self._http, OrderedDict(), 0, 0

    @property
    def on(self):
        return bool(self.token)

    def _http(self, ip):
        u = "https://ipinfo.io/%s/json?token=%s" % (urllib.parse.quote(ip, safe=""), urllib.parse.quote(self.token, safe=""))
        with urllib.request.urlopen(urllib.request.Request(u, headers={"Accept": "application/json"}), timeout=1.2) as r:
            return json.loads(r.read(20000))

    @staticmethod
    def public(ip):
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return a.is_global

    def lookup(self, ip):
        if not (self.on and ip and self.public(ip)):
            return None
        now = time.time()
        c = self.cache.get(ip)
        if c and now - c[0] < self.ttl:
            self.hits += 1
            return c[1]
        try:
            d = self.fetch(ip)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            self.errs += 1
            return None
        out = self.parse(d)
        self.cache[ip] = (now, out)
        while len(self.cache) > self.cap:
            self.cache.popitem(last=False)
        return out

    @staticmethod
    def parse(d):
        if not isinstance(d, dict) or d.get("bogon"):
            return None
        lat = lon = None
        try:
            lat, lon = [float(v) for v in (d.get("loc") or "").split(",")]
        except ValueError:
            pass
        pv = d.get("privacy") if isinstance(d.get("privacy"), dict) else {}
        org = str(d.get("org") or d.get("as_name") or "")
        anon = any(pv.get(k) for k in ("vpn", "proxy", "tor", "relay", "hosting")) or any(w in org.lower() for w in HOSTING)
        city = d.get("city") or ""
        return dict(city=CITY_TO_CANON.get(city.lower(), city), lat=lat, lon=lon, cty=d.get("country") or "", org=org, anon=anon,
                    region=d.get("region") or "")


# ------------------------------------------------------------------ alerts

class Notifier:
    """Telegram / Slack push for risky decisions. Sends from a background thread; a slow or dead chat app cannot slow scoring."""

    def __init__(self, post=None):
        e = os.environ.get
        self.tg = (e("TELEGRAM_BOT_TOKEN"), e("TELEGRAM_CHAT_ID"))
        self.slack = e("SLACK_WEBHOOK_URL")
        self.min_amt = float(e("FH_ALERT_MIN_AMT", "0") or 0)
        self.per_min = int(e("FH_ALERT_PER_MIN", "20") or 20)
        self.post = post or self._post
        self.q, self.sent, self.dropped, self.failed, self.win = queue.Queue(maxsize=200), 0, 0, 0, deque()
        self.last_err = None
        threading.Thread(target=self._loop, daemon=True).start()

    @property
    def channels(self):
        return [n for n, ok in (("telegram", all(self.tg)), ("slack", bool(self.slack))) if ok]

    @staticmethod
    def _post(url, body, ctype):
        req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype})
        urllib.request.urlopen(req, timeout=5).read(2000)

    def text(self, r, src="live"):
        from .fmt import inr
        icon = {1: "\U0001F7E1 STEP-UP", 2: "\U0001F534 DECLINE"}.get(r["dec"], "OK")
        why = "; ".join(h["msg"] for h in r["hits"][:2]) or "; ".join(t["txt"] for t in r["top"][:2]) or "model score"
        return "%s  %s  %s\nrisk %d%%  customer %s  via %s\nwhy: %s" % (icon, inr(r["amt"], 0), r["chan"].upper(), r["score"], r["uid"], src, why[:300])

    def alert(self, r, src="live"):
        """Queue an alert if the decision is risky enough. Returns True if queued."""
        if r["dec"] < 1 or r["amt"] < self.min_amt or not self.channels:
            return False
        now = time.time()
        while self.win and now - self.win[0] > 60:
            self.win.popleft()
        if len(self.win) >= self.per_min:
            self.dropped += 1
            return False
        self.win.append(now)
        try:
            self.q.put_nowait(self.text(r, src))
        except queue.Full:
            self.dropped += 1
            return False
        return True

    def test(self):
        """Send a clearly-labelled test message synchronously and report what happened (used by the UI's test button)."""
        return self._send("TEST — Fraud Hunter alert channel is working.")

    def _send(self, msg):
        res = {}
        for ch in self.channels:
            try:
                if ch == "telegram":
                    self.post("https://api.telegram.org/bot%s/sendMessage" % self.tg[0],
                              urllib.parse.urlencode({"chat_id": self.tg[1], "text": msg}).encode(), "application/x-www-form-urlencoded")
                else:
                    self.post(self.slack, json.dumps({"text": msg}).encode(), "application/json")
                self.sent += 1
                res[ch] = "sent"
            except (urllib.error.URLError, OSError, ValueError) as e:
                self.failed += 1
                self.last_err = type(e).__name__
                res[ch] = "failed: " + type(e).__name__          # never echo the URL: it contains the bot token
        return res

    def _loop(self):
        while True:
            self._send(self.q.get())

    def status(self):
        return dict(channels=self.channels, sent=self.sent, dropped=self.dropped, failed=self.failed, min_amt=self.min_amt, per_min=self.per_min)
