"""Check a message with Scam Shield.

    python examples/shield_check.py "your message here" [http://localhost:8000]
"""
import json
import os
import sys
import urllib.request

text = sys.argv[1] if len(sys.argv) > 1 else "Your electricity connection will be disconnected tonight. Call 9876543210 immediately."
url = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get("FH_URL", "http://localhost:8000")).rstrip("/")
req = urllib.request.Request(url + "/api/shield", json.dumps({"text": text}).encode(), {"content-type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=10))
print("%s (warning score %d / 100)" % (r["level"].upper(), r["score"]))
for x in r["reasons"]:
    print("  - %s: %s" % (x["id"], x["en"]))
print("What to do:")
for a in r["actions"]["en"]:
    print("  *", a)
