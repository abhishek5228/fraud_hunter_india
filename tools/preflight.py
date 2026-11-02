"""Run this on your own computer 10 minutes before a demo. It wakes the server, then walks the same path a judge would.

    python tools/preflight.py                         # checks that need no key
    FH_API_KEY=... python tools/preflight.py          # also downloads the real data and runs both benchmarks

Reads FH_URL (default https://fraud-hunter-api.onrender.com). Uses only the standard library. Exit code 0 means every check passed."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("FH_URL", "https://fraud-hunter-api.onrender.com").rstrip("/")
KEY = os.environ.get("FH_API_KEY", "")
RES = []


def call(path, body=None, post=False, timeout=90):
    h = {"content-type": "application/json"}
    if KEY:
        h["x-api-key"] = KEY
    req = urllib.request.Request(URL + path, data=(json.dumps(body).encode() if body is not None else (b"" if post else None)), headers=h, method="POST" if post or body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, None


def check(name, ok, detail=""):
    RES.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (("  " + str(detail)) if detail else ""))
    return ok


def job(jid, limit=900):
    t = time.time()
    while time.time() - t < limit:
        code, j = call("/api/realdata/job/" + jid)
        if code == 200 and j["state"] in ("done", "error"):
            return j
        time.sleep(3)
    return dict(state="error", error="timed out after %d s" % limit)


def main():
    print("server:", URL)
    t = time.time()
    up = False
    while time.time() - t < 150:
        try:
            code, h = call("/api/health", timeout=30)
            if code == 200:
                up = True
                break
        except Exception:
            pass
        print("  waking the server... %d s" % (time.time() - t))
        time.sleep(5)
    if not check("server is up", up, "after %d s" % (time.time() - t)):
        return 1
    code, ig = call("/api/integrations")
    check("integrations answer", code == 200, "auth required" if ig and ig.get("auth") else "open (set FH_API_KEY before going public)")
    code, rd = call("/api/realdata")
    check("real data list answers", code == 200 and bool(rd), "uploads on" if rd and rd.get("uploads") else "uploads off")
    code, sh = call("/api/shield", dict(text="Your electricity connection will be disconnected tonight. Call 98xxxxxxxx now and install the support app."))
    check("Scam Shield flags a known scam text", code == 200 and sh and sh["level"] in ("caution", "danger"), sh and sh.get("level"))
    code, sh = call("/api/shield", dict(text="Hi, see you at lunch tomorrow?"))
    check("Scam Shield leaves a normal text alone", code == 200 and sh and sh["level"] == "none", sh and sh.get("level"))
    for p in ("/api/graph", "/api/fairness"):
        code, _ = call(p)
        check("GET " + p, code == 200, code)
    if not KEY:
        print("\nNo FH_API_KEY set: skipping the real-data downloads and benchmarks. Set it to test them.")
    else:
        code, r = call("/api/realdata/run/shield", post=True)
        if code == 409:
            time.sleep(20)
            code, r = call("/api/realdata/run/shield", post=True)
        if check("Scam Shield benchmark job starts", code == 200 and r, code):
            j = job(r["job"], 300)
            res = j.get("result") or {}
            check("Scam Shield benchmark finishes", j["state"] == "done", j.get("error") or "recall %.1f%%, false alarms %.3f%%" % (100 * res.get("recall", 0), 100 * res.get("false_alarm", 0)))
        code, r = call("/api/realdata/run/ulb", post=True)
        if code == 409:
            time.sleep(20)
            code, r = call("/api/realdata/run/ulb", post=True)
        if check("card-fraud benchmark job starts", code == 200 and r, code):
            j = job(r["job"], 900)
            ok = j["state"] == "done"
            res = j.get("result") or {}
            check("card-fraud benchmark finishes (no out-of-memory crash)", ok, j.get("error") or "AUC %.3f" % res["models"][0]["auc"])
            if ok:
                code, rp = call("/api/realdata/replay?offset=0&n=10")
                check("real-card replay answers", code == 200 and rp and len(rp["rows"]) == 10, code)
        code, _ = call("/api/health")
        check("server still up after the benchmarks", code == 200, code)
    bad = RES.count(False)
    print("\n%d checks, %d failed" % (len(RES), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
