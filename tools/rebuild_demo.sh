#!/usr/bin/env bash
# Rebuild the backend-free demo END TO END. Skipping the capture step silently breaks the Playground scenarios, so do all of it.
set -euo pipefail
cd "$(dirname "$0")/.."
python tools/build_demo.py
fuser -k 8000/tcp >/dev/null 2>&1 || true
FH_STATE=0 setsid nohup uvicorn fh.api:app --port 8000 --workers 1 >/tmp/fh-demo-srv.log 2>&1 < /dev/null &
for i in $(seq 1 40); do curl -sf localhost:8000/api/health >/dev/null && break; sleep 1; done
FH_URL=http://localhost:8000 python tools/capture_scenarios.py
fuser -k 8000/tcp >/dev/null 2>&1 || true
python tools/build_site.py --demo
python - <<'P'
import json
d = json.load(open("dist/demo-data.json"))
assert d.get("scenarios") and d.get("users"), "scenarios missing: the Playground would be broken"
print("demo ok:", len(d["scenarios"]), "scenario calls")
P
