"""Fraud Hunter client. Zero dependencies (standard library only).

    from fraudhunter import FraudHunter
    fh = FraudHunter("https://fraud-hunter-api.onrender.com", api_key="...")
    d = fh.score(uid="u0042", mid="shop@upi", amt=2500, chan="upi", city="Mumbai")
    if d.decision != "APPROVE":
        print(d.risk, d.reasons, d.customer_message["en"])

Retries only what is safe to repeat: GETs, and score() with commit=False. A committed score changes the customer's history,
so it is never retried silently.
"""
import json
import time
import urllib.error
import urllib.request

__all__ = ["FraudHunter", "FraudHunterError", "Decision"]
__version__ = "1.0.0"


class FraudHunterError(Exception):
    def __init__(self, status, detail):
        super().__init__("%s: %s" % (status, detail))
        self.status, self.detail = status, detail


class Decision:
    """A scored payment. Raw JSON stays available as .raw."""

    def __init__(self, raw):
        self.raw = raw
        self.id = raw["id"]
        self.decision = raw["dname"]                     # APPROVE | STEP_UP | DECLINE
        self.risk = raw["score"]                         # 0-100
        self.probability = raw["p"]
        self.reasons = [h["code"] for h in raw["hits"]]  # guardrail rule codes
        self.drivers = [t["txt"] for t in raw["top"]]    # model factors, strongest first
        self.why = raw["why"]
        self.customer_message = raw.get("msg")           # {"en": ..., "hi": ...} or None when approved
        self.latency_us = raw.get("lat_us")

    @property
    def approved(self):
        return self.decision == "APPROVE"

    def __repr__(self):
        return "<Decision %s risk=%d reasons=%s>" % (self.decision, self.risk, ",".join(self.reasons) or "-")


class FraudHunter:
    def __init__(self, url, api_key=None, timeout=3.0, retries=2, transport=None):
        self.url, self.key, self.timeout, self.retries = url.rstrip("/"), api_key, timeout, retries
        self._tx = transport or self._http

    def _http(self, method, path, body, headers, timeout):
        req = urllib.request.Request(self.url + path, None if body is None else json.dumps(body).encode(), headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"null")
            except ValueError:
                return e.code, {"detail": e.reason}

    def _call(self, method, path, body=None, safe=False):
        h = {"content-type": "application/json", **({"x-api-key": self.key} if self.key else {})}
        for i in range(self.retries + 1 if safe else 1):
            try:
                st, js = self._tx(method, path, body, h, self.timeout)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                if i < self.retries and safe:
                    time.sleep(0.2 * 2 ** i)
                    continue
                raise FraudHunterError(0, "cannot reach %s (%s)" % (self.url, type(e).__name__))
            if st >= 500 and safe and i < self.retries:
                time.sleep(0.2 * 2 ** i)
                continue
            if st >= 400:
                raise FraudHunterError(st, (js or {}).get("detail", js))
            return js

    def score(self, uid, amt, mid="shop@upi", chan="upi", cat="digital", city=None, ip=None, dev=None, commit=True, **more):
        body = dict(uid=uid, amt=amt, mid=mid, chan=chan, cat=cat, commit=commit, **{k: v for k, v in dict(city=city, ip=ip, dev=dev).items() if v is not None}, **more)
        return Decision(self._call("POST", "/api/score", body, safe=not commit))

    def confirm(self, decision_id, passed):
        """After a STEP_UP: tell the engine whether the customer passed the challenge."""
        return self._call("POST", "/api/confirm", dict(id=decision_id, passed=bool(passed)))

    def feedback(self, decision_id, fraud, block=False):
        return self._call("POST", "/api/feedback", dict(id=decision_id, verdict="fraud" if fraud else "legit", block=block))

    def shield(self, text):
        """Scam Shield verdict for a message, UPI handle or QR link."""
        return self._call("POST", "/api/shield", dict(text=text), safe=True)

    def brief(self, decision_id, llm=False):
        return self._call("GET", "/api/case/%s/brief%s" % (decision_id, "?llm=true" if llm else ""), safe=True)

    def health(self):
        return self._call("GET", "/api/health", safe=True)
