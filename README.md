# Fraud Hunter

A real-time transaction risk engine. It scores every payment as it arrives, decides **approve / step-up / decline**, and explains the decision in terms an analyst can act on. The core question it answers is not "is this fraud?" but **"what is the cheapest action, given what fraud costs and what blocking a good customer costs?"**

Everything runs on synthetic data, so the numbers below demonstrate the engineering, not real-world performance.

```
pip install -r requirements.txt
python -m fh.train          # ~30 s: simulates 42 days, trains, evaluates, saves artifacts/
python -m uvicorn fh.api:app --port 8000
# open http://localhost:8000
python -m pytest -q tests   # 14 tests
```
Or `docker build -t fraudhunter . && docker run -p 8000:8000 fraudhunter`.

## What you can do in the UI

| Tab | What it shows |
|---|---|
| **Live ops** | A stream of simulated payments, KPIs against simulation ground truth, a map, and per-attack-type detection. Click any transaction for the full explanation. **Launch attack** injects card-testing, account takeover, session hijack, cloned-card or mule-ring attacks into the live stream. |
| **Policy lab** | Move the business costs (fraud fee, cost of declining a good customer, challenge friction, risk aversion) and the held-out period is re-decided instantly. Shows total cost against baselines, the fraud-vs-friction frontier, and how the bar moves with the amount at stake. **Apply** pushes the setting to the live engine. |
| **Playground** | Compose your own transaction or run a scenario (teleporting card, card-testing burst, new device plus gift cards) and see the decision. |
| **Model card** | AUC, average precision, recall at fixed false-alarm rates, calibration, feature importance, the learned shape of every feature, who gets flagged, and an honest limitations list. |

## Architecture

```
 transaction ──► feature store ──► GAM model ──► rules ──► cost policy ──► decision + explanation
                 (state BEFORE     (exact per-    (can only  (argmin of
                  this txn)         feature        escalate)  expected cost)
                     ▲              contributions)
                     │ commit after decision;  fraud reports arrive hours later
```

| Module | Role |
|---|---|
| `fh/gen.py` | Synthetic world: 1,200 customers, 500 merchants, 14 cities. Seven fraud typologies plus legitimate lookalikes. |
| `fh/feat.py` | Streaming feature store: velocity windows, per-customer spend profile (Welford), travel speed from the last *card-present* location, device and network graph, 7-day windowed fraud-report counts. |
| `fh/model.py` | Cyclic Newton-boosted **generalized additive model**, written from scratch in numpy, plus a logistic baseline and tie-safe metrics. |
| `fh/rules.py` | Guardrails with reason codes (impossible travel, card testing, device ring, bad reputation, blocklist). |
| `fh/policy.py` | Expected-cost decision rule. |
| `fh/engine.py` | Ties it together; records latency; keeps recent cases for inspection. |
| `fh/sim.py`, `fh/api.py`, `web/` | Live simulator, FastAPI service with SSE, the dashboard (no build step). |

### Design decisions worth defending

1. **No leakage by construction.** Features for a transaction are computed from state *before* it is committed (tested). Train, validation and test are split by *time*, and the model is evaluated on the most recent 12 days.
2. **Labels arrive late.** Fraud reports reach the reputation counters 1-12 hours after the event, for 80% of fraud, mirroring disputes and chargebacks.
3. **Windowed reputation, not lifetime counts.** My first version used cumulative report counts. They kept growing, so on the held-out period they extrapolated beyond the training range and a linear model beat the GAM. Switching to 7-day windows fixed it and the GAM now leads.
4. **Exact explanations.** An additive model's per-feature contribution *is* the model's arithmetic. No SHAP approximation, no surrogate. The inspector's bars plus the baseline sum exactly to the logit (tested).
5. **Cost-aware, amount-aware decisions.** `approve = p·(loss·amt + fee)`, `decline = (1-p)·(margin·amt + churn)`, `step-up = challenge cost + residual risk and abandonment`. The cheapest wins per transaction. A $5 purchase is challenged only above ~16% risk; a $500 one above ~1%. A single global threshold cannot do this.
6. **Rules only escalate.** `final = max(model policy, strongest rule)`. They are graduated: an impossible-travel hit blocks card-present use, but only challenges an online purchase on a *known device* (probably a VPN).
7. **Profile hygiene.** Declined and failed-challenge attempts do not enter the customer's behavioural profile, but they do enter the device graph.

### Bugs I found and fixed while building (and what they taught)

- AUC was 1.000. The world was too easy, so I added camouflage: session hijacks on the victim's own device, spoofed fingerprints, low-and-slow card testing, and legitimate VPN users, shared library devices, cleared cookies and day-trip travellers.
- Hard rules were blocking 0.8% of good customers while the model alone blocked 0.08%. Causes: a VPN purchase overwrote the "last location" (fixed by anchoring travel speed on card-present events only), and a simulator artifact that tainted victims' own networks.
- Cost-optimal decisions are only optimal for **calibrated** scores. A test with uncalibrated toy scores showed the policy losing to a naive threshold, which is why calibration error is a headline metric.

## Results (held-out last 12 days, 44.6k transactions, 882 fraud)

| | GAM | Logistic baseline |
|---|---|---|
| ROC AUC | 0.9948 | 0.9941 |
| Average precision | 0.919 | 0.907 |
| Recall @ 1% false alarms | 91.7% | 91.3% |
| Recall @ 0.1% false alarms | 75.5% | 73.9% |
| Calibration error (ECE) | 0.0019 | |

At default costs: 95.4% approved, 2.6% challenged, 2.0% declined; 93.4% of fraud caught; 2.8% of good customers touched (0.45% declined). **Total cost $23.5k versus $49.4k for one global 0.5 threshold, $141k for rules only and $253k for approving everything.**

Where it is weak, and shown rather than hidden: session hijacks (about 43% flagged), shared public devices (93% flagged, they resemble mule rings), and VPN users (68% flagged).

**Latency:** the engine alone scores about 18,000 transactions per second on one Python thread (p50 45 µs, p99 92 µs; features, model, rules and explanation included). Inside the live server, with the event loop, SSE and the dashboard running, the UI shows roughly 190 µs median.

## API

`POST /api/score` with `{uid, amt, cat, chan, city, dev?, ip?, ts?, commit?}` returns the decision, probability, reason codes, exact contributions, expected cost of each action and the explanation text. Also: `GET /api/stream` (SSE), `GET /api/case/{id}`, `POST /api/feedback`, `GET|POST /api/policy`, `POST /api/policy/lab`, `POST /api/attack`, `GET /api/model`.

## What I would do next with real data

Replace the delayed-report simulator with real chargeback feeds; add monotonic constraints and pairwise interaction terms to the GAM; move state to Redis or a stream processor for horizontal scaling; add drift monitoring (population stability on each feature) and a champion-challenger harness; and learn the step-up pass rates from live outcomes rather than assuming them.
