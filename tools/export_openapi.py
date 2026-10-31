"""Write docs/openapi.json and a Postman collection from the running app's own schema (so they cannot drift from the code)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = {"/api/score": dict(uid="u0042", mid="shop@upi", amt=2500, chan="upi", cat="digital", city="Mumbai", commit=False),
      "/api/shield": dict(text="Your electricity will be cut tonight, call 9876543210 immediately"),
      "/api/confirm": dict(id="t0000001", passed=True), "/api/feedback": dict(id="t0000001", verdict="fraud", block=False)}
spec = api.app.openapi()
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
json.dump(spec, open(os.path.join(ROOT, "docs", "openapi.json"), "w"), indent=1)
items = []
for path, ops in sorted(spec["paths"].items()):
    for m, op in ops.items():
        r = dict(method=m.upper(), header=[{"key": "x-api-key", "value": "{{api_key}}"}, {"key": "content-type", "value": "application/json"}],
                 url=dict(raw="{{base}}" + path, host=["{{base}}"], path=[p for p in path.split("/") if p]))
        if m == "post" and path in EX:
            r["body"] = dict(mode="raw", raw=json.dumps(EX[path], indent=2))
        items.append(dict(name="%s %s" % (m.upper(), path), request=r))
col = dict(info=dict(name="Fraud Hunter India API", schema="https://schema.getpostman.com/json/collection/v2.1.0/collection.json"), item=items,
           variable=[dict(key="base", value="https://fraud-hunter-api.onrender.com"), dict(key="api_key", value="")])
json.dump(col, open(os.path.join(ROOT, "docs", "FraudHunter.postman_collection.json"), "w"), indent=1)
print("%d operations -> docs/openapi.json, docs/FraudHunter.postman_collection.json" % len(items))
