# Running and shipping Fraud Hunter India

Three ways to run it. They share one frontend; only where the API lives changes.

```
 browser ──► static frontend (web/) ──► API (fh/api.py, one Python process, state in memory)
                    │
                    └── demo mode: the same pages, answered from recorded engine output (no API at all)
```

| | What you get | Needs a server? | Best for |
|---|---|---|---|
| **A. All-in-one** | Live scoring, free-form inputs, everything | Yes (one container) | The real thing, local or hosted |
| **B. Split** | Static frontend on a CDN, API elsewhere | Yes (API only) | Netlify/Vercel/Pages in front of your API |
| **C. Static demo** | Recorded real decisions, nothing to host | No | A portfolio link, a hackathon submission, offline |

## A. All-in-one

```bash
pip install -r requirements.txt
python -m fh.train                          # about 35 s; writes artifacts/ (model + warmed feature store)
uvicorn fh.api:app --port 8000 --workers 1  # open http://localhost:8000
```

Docker: `docker compose up --build` (the image trains once at build time, so the container starts in seconds).

Hosted: **Render** (`render.yaml` is a ready blueprint: New > Blueprint > pick the repo), or Fly.io, Railway, or Cloud Run. Anything that runs a Dockerfile works: the container honours `$PORT`, exposes `/api/health` for health checks, and runs a non-root user.

Two settings that matter on any host:
- **Keep one worker and one instance.** The feature store lives in process memory, so a second worker would score against different state. On Cloud Run set `min-instances=1, max-instances=1`; on Render keep the default single instance.
- **Do not buffer the stream.** `/api/stream` is Server-Sent Events. The API already sends `X-Accel-Buffering: no`; if you put nginx or Cloudflare in front, disable response buffering for that path.

## B. Static frontend on a CDN, API elsewhere

```bash
python tools/build_site.py --api https://fraud-hunter-api.onrender.com
# -> dist/site/   (index.html + static/*), with the API URL baked into static/config.js
```

Drag `dist/site` onto Netlify, or push it to GitHub Pages / Vercel. You can also edit `static/config.js` after the fact: it is one line, `window.FH_API = "https://..."`.

On the backend, restrict who may call it:

```bash
FH_ORIGINS="https://your-site.netlify.app"   # comma-separated; default "*" is for development
```

Tested: a frontend served from one origin driving an API on another, including the live stream and the case inspector.

## C. Static demo (no backend)

The demo replays decisions the real engine recorded offline: a live stream with attacks embedded, an attack library for the "Launch attack" menu, a festival-surge segment with its drift readings, a grid of 45 policy-lab results, the model card, and the Playground scenarios captured by driving the real UI. Nothing is faked: every number came out of the production engine. Free-form scoring and some sliders are disabled, and the page says so.

```bash
python -m fh.train
python tools/build_demo.py                                   # records the engine -> dist/demo-data.json
uvicorn fh.api:app --port 8000 &                             # a fresh backend, only needed for the next step
python tools/capture_scenarios.py                            # records the Playground scenarios through the real UI
python tools/build_site.py --demo
# -> dist/demo-site/                 a static site (drag onto Netlify)
# -> dist/fraud-hunter-demo.html     one self-contained file (about 3 MB): email it, host it, open it from disk
```

(`capture_scenarios.py` needs `pip install playwright && playwright install chromium`.)

## Wiring it into a real payment flow

Scoring is two phases, because a challenged payment is not yet a trusted one:

```bash
# 1. score the payment before it is authorised
curl -X POST $API/api/score -H 'content-type: application/json' -d '{
  "uid":"u0330","amt":38000,"cat":"p2p","chan":"upi","mid":"q7z1@oksbi","pers":true,
  "city":"Bengaluru","dev":"du0330a","ip":"22.4.53.10","rat":true}'
# -> {"dname":"DECLINE","p":0.99,"hits":[...],"top":[...],"msg":{"en":"...","hi":"..."},"id":"t0000123",...}

# 2. if the answer was STEP_UP, run your OTP / PIN challenge, then report the outcome
curl -X POST $API/api/confirm -H 'content-type: application/json' -d '{"id":"t0000123","passed":true}'

# 3. later, when a complaint or analyst decision arrives
curl -X POST $API/api/feedback -H 'content-type: application/json' -d '{"id":"t0000123","verdict":"fraud","block":true}'
```

Only an approved payment, or a challenged one confirmed as passed, updates the customer's profile. Every attempt still counts toward velocity and the device, network and payee graphs. Send `sim` (hours since a SIM change), `rat` (screen-share or remote-access detected) and `coll` (approving a collect request) when your telemetry has them; they default to "unknown".

## Settings

| Variable | Default | What it does |
|---|---|---|
| `FH_API_KEY` | unset (open) | If set, integration endpoints need an `X-API-Key` header. Health stays open. |
| `FH_ORIGINS` | `*` | Comma-separated origins allowed to call the API from a browser. Lock it to your frontend. |
| `FH_AUDIT_DB` | `artifacts/audit.db` | Where the audit log lives. Point it at a persistent disk. |
| `FH_ART` | `artifacts/` | Directory of the trained model. Point at `artifacts_hard` to run the red-team-hardened model. |
| `FH_STATE` | `1` | Set `0` to stop saving and restoring the feature store snapshot. |
| `PORT` | `8000` | The container honours it. |

A browser frontend cannot hold an API key safely: anything in `static/config.js` is visible to every visitor. Use `FH_API_KEY` for server-to-server calls (your payment system to the engine), and keep the public demo open and simulated.

**Files on a free host are usually erased on redeploy.** That includes the audit log and the state snapshot. For anything you need to keep, attach a persistent disk and point `FH_AUDIT_DB` at it.

## Demo day on a free server

A free Render server sleeps after about 15 idle minutes, takes 30 to 50 seconds to wake, and forgets downloaded files on every restart. Three things make that survivable:

1. **Keep it awake.** `.github/workflows/keepalive.yml` pings `/api/health` every 10 minutes. It is free on a public repository; on a private one it spends your Actions minutes, so disable it when the event is over.
2. **Fetch the real text collections at boot.** Set `FH_PREWARM=1` in the Render environment (already in `render.yaml` for new blueprints). Add `FH_PREWARM_ULB=1` to fetch the 144 MB card file too. Without it, the Run buttons on the Real data tab download what is missing themselves.
3. **Rehearse 10 minutes before.** `FH_API_KEY=<your key> python tools/preflight.py` wakes the server and walks the path a judge would: Scam Shield, the real-data downloads, both benchmarks and the card replay. Every line should say PASS. A crash from the 512 MB limit shows up here, not on stage.

## Before real traffic

- **This is trained on synthetic data.** Retrain on your own history (`fh/train.py` is the template), and expect to rebuild the cost settings with your finance team.
- **Authentication is one shared key.** `FH_API_KEY` is enough for a pilot; for production use your gateway, per-client keys and role-based access. There is no rate limiting. Lock `FH_ORIGINS`.
- **State is in memory.** A restart loses the live feature store (the baked-in snapshot is restored). To scale out, partition by customer id so one customer always hits one instance, or move the store to Redis.
- **Personal data.** The engine needs device ids, IPs and payee ids. Treat them under your data-protection obligations; none of this repository contains real data.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Page loads, feed stays empty | The page can't reach the API: check `static/config.js`, the browser console, and `FH_ORIGINS` |
| Feed freezes behind a proxy | Response buffering on `/api/stream`: disable it for that path |
| `no artifacts found, training` on start | Run `python -m fh.train` first (the Docker build does this for you) |
| Different numbers after a restart | The simulator reseeds; the model and metrics do not change |
