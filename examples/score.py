"""Score three payments against a running server and print what the engine says.

    python examples/score.py [http://localhost:8000]
"""
import json
import os
import sys
import urllib.request

URL = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FH_URL", "http://localhost:8000")).rstrip("/")


def call(path, body=None):
    req = urllib.request.Request(URL + path, None if body is None else json.dumps(body).encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


user = call("/api/users")[0]
cases = {
    "A usual grocery payment": dict(uid=user["uid"], mid=user["merchant"], cat="grocery", amt=180, chan="upi", city=user["city"], dev=user["dev"], ip=user["ip"]),
    "A first payment to a person while a screen-sharing app runs": dict(uid=user["uid"], mid="newperson8841@ybl", cat="p2p", amt=18500, chan="upi", pers=True, rat=True, city=user["city"], dev=user["dev"], ip=user["ip"]),
    "A big transfer from a brand-new phone, hours after a SIM change": dict(uid=user["uid"], mid="acct-7781", cat="bank_transfer", amt=49500, chan="imps", pers=True, sim=3, city=user["city"], dev="brand-new-phone", ip="49.1.1.1"),
}
for name, body in cases.items():
    r = call("/api/score", dict(body, commit=False))        # commit=False: a dry run, nothing is remembered
    print("\n%s\n  -> %s (risk %d%%)" % (name, r["dname"], r["score"]))
    print("  rules:", ", ".join(h["code"] for h in r["hits"]) or "none")
    print("  why:  ", r["why"])
