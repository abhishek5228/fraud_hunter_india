# Fraud Hunter India

A real-time risk engine for Indian digital payments. It scores every UPI, IMPS, card and ATM payment as it arrives, chooses **approve / step-up / decline**, and explains the decision in terms an analyst, or the customer, can act on. The core question is not "is this fraud?" but **"what is the cheapest action, given what fraud costs and what blocking a good customer costs?"**

All data is synthetic. The numbers below show the engineering, not real-world performance.

![Live operations console](docs/live.png)

```
pip install -r requirements.txt
python -m fh.train                          # ~35 s: simulates 42 days, trains, evaluates, saves artifacts/
python -m uvicorn fh.api:app --port 8000    # then open http://localhost:8000
python -m pytest -q tests                   # 21 tests
```
Or `docker build -t fraud-hunter . && docker run -p 8000:8000 fraud-hunter`.

## Why India needs its own engine

Indian payments fraud is dominated by things a card-centric engine barely sees. Each row below is a real signal in this project.

| What happens in India | Signal the engine uses | Where |
|---|---|---|
| Customers are talked into paying a stranger (vishing, QR and refund scams, collect requests) | First payment to a person, **strangers paying the same payee for the first time** (mule fan-in), payee never seen on the platform, complaints against the payee | `feat.py`, rules `PAYEE_FAN_IN`, `MULE_PAYEE` |
| Scammer has the victim share their screen | Screen-share / remote-access app flag, combined with amount and payee novelty | rule `SCREEN_SHARE_NEW_PAYEE` |
| SIM swap, then UPI re-bound on a new phone and drained in near-limit transfers | SIM-change recency x new device, amounts just under Rs 50k / 1 lakh / 2 lakh | rules `SIM_SWAP_DRAIN`, `LIMIT_STRUCTURING` |
| Rented mule accounts, rotated to stay ahead of complaints | 7-day windowed complaint counts per payee, device and network | `feat.py` |
| Cyber cafes and CSC kiosks put one phone in many hands | Shared-device rules only escalate when paying a stranger or moving real money | rule `DEVICE_RING` |
| UPI is about 70% of volume, IMPS carries the big transfers | Per-rail features and per-rail margins in the cost model | `policy.py` |
| Festival peaks change what "normal" looks like | PSI drift monitor; a Festival-surge switch in the UI to see it fire | `/api/drift` |
| Customers read Hindi or English | Bilingual customer message with the scam-safe advice (never share PIN or OTP, call 1930) | `explain.py` |

## A tour

| | |
|---|---|
| **Live ops.** Simulated traffic with ground-truth KPIs, an India map, per-attack detection, and the drift monitor. Launch any attack from the top bar. Click a payment for the full explanation: a decision ruler whose zones move with the amount and rail, exact factor contributions, expected cost of each action, and what the customer sees in English or Hindi. | ![](docs/drift.png) |

**Policy lab.** Move the business costs (fraud fee, cost of declining a good customer, challenge friction, risk aversion) and the held-out period is re-decided instantly. It compares against the best *tuned* thresholds, not a straw man.

![Policy lab](docs/lab.png)

**Playground.** Compose a payment or run a scenario (SIM-swap drain, vishing with screen-share, a payee four strangers just paid, a teleporting card) and see the decision, the rules that fired and the customer message.

![Playground](docs/play.png)

**Model card.** AUC, average precision, recall at fixed false-alarm rates, calibration, importance, the learned shape of every feature, who gets flagged, and a limitations list.

![Model card](docs/model.png)

## Architecture

```
 payment ──► feature store ──► additive model ──► rules ──► cost policy ──► decision + explanation
             (state BEFORE      (exact per-       (can only  (argmin of          + customer message
              this payment)      feature           escalate)  expected cost)
                  ▲              contributions)
                  │ commit after the decision;  complaints arrive hours later
```

| Module | Role |
|---|---|
| `fh/gen.py` | Synthetic India: 1,200 customers across 15 cities, 500 merchants, 5 rails. Eight fraud typologies and 12 kinds of legitimate lookalike. |
| `fh/feat.py` | Streaming features: velocity windows, per-customer profile, travel speed from the last *card-present* location, device / network / **payee** graphs, SIM and screen-share signals, 7-day windowed complaint counts. 44 features. |
| `fh/model.py` | Cyclic Newton-boosted generalized additive model written from scratch in numpy, a logistic baseline, tie-safe metrics. |
| `fh/rules.py` | Guardrails with reason codes. They only escalate. |
| `fh/policy.py` | Expected-cost decision rule with rail-, recipient- and amount-dependent margin. |
| `fh/engine.py`, `fh/explain.py` | Orchestration, latency tracking, reasons, bilingual messages. |
| `fh/sim.py`, `fh/api.py`, `web/` | Live simulator, FastAPI + SSE service, the dashboard (no build step). |

## Design decisions worth defending

1. **No leakage by construction.** Features come from state *before* the payment is committed (tested). Splits are by time, the first week is burn-in (every payee looks new on day one), and the model is evaluated on the most recent 12 days.
2. **Honest labels.** Complaints reach the reputation counters 1 to 12 hours late for 80% of fraud. A complaint about an *authorised* scam (the customer was talked into paying) taints the **payee**, never the victim's own phone. My first version got this wrong and blocked victims' later genuine payments.
3. **Fan-in counts strangers, not friends.** Friends paying each other all week is normal. A mule is identified by *first-time* senders. Counting every sender gave 900 false challenges in one test; counting first-time senders fixed it.
4. **Windowed reputation.** Lifetime counts drifted out of the range the model was trained on. Seven-day windows fixed it.
5. **Exact explanations.** The model is additive, so each feature's contribution is the model's own arithmetic. The bars plus the baseline sum exactly to the logit (tested). No surrogate.
6. **Cost-aware, amount-aware, rail-aware.** `approve = p x (loss x amount + fee)`; `decline = (1 - p) x (margin x amount + churn)`; `step-up = challenge cost + residual risk and abandonment`. The cheapest wins per payment. Margin is a function of the rail: cards earn about 1.8%; UPI to a person, IMPS and ATM earn none; UPI to a merchant above Rs 2,000 earns 0.4% under NPCI's framework effective 15 Oct 2026.
7. **Rules only escalate, and they are proportionate.** An impossible-travel hit blocks card-present use but only challenges an online payment on a *known device* (probably a VPN). A screen-share is only worth interrupting for a person payee or Rs 5,000 and up. A kiosk phone is only blocked when paying a stranger.
8. **Drift monitoring that does not cry wolf.** PSI against the most recent period the model saw, minus the PSI that pure sampling noise would produce for that sample size, and the diurnal `hrar` feature excluded.

## Results

Held-out last 12 days: 53,789 payments, 908 fraud.

| | GAM (shipped) | Logistic baseline |
|---|---|---|
| ROC AUC | 0.9975 | 0.9973 |
| Average precision | 0.934 | 0.943 |
| Recall at 1% false alarms | 94.8% | 96.2% |
| Recall at 0.1% false alarms | 76.5% | 77.3% |
| Calibration error (ECE) | 0.0015 | 0.0017 |

**The plain logistic model is at least as accurate as the GAM here.** The GAM converged by round 240, so it is not undertrained. It is also additive, with exact contributions, so I ship it for the non-linear shapes in the Model card, not for accuracy. Pairwise interaction terms are the obvious next step.

**What the policy buys** (same 12 days, default costs):

| Approach | Total cost | Fraud caught | Good customers touched |
|---|---|---|---|
| **This policy (amount- and rail-aware)** | **Rs 1.91 L** | 98.3% | 3.4% |
| Best *tuned* step-up + decline thresholds | Rs 2.19 L | 98.8% | 4.8% |
| Best tuned single threshold | Rs 5.58 L | 96.1% | 1.3% |
| Untuned: decline above 50% | Rs 15.1 L | 80.4% | 0.1% |
| Hard rules only | Rs 36.6 L | 55.9% | 1.0% |
| Approve everything | Rs 1.82 Cr | 0% | 0% |

The tuned baselines were fitted on this very period, which flatters them. The amount-aware policy is still 13% cheaper than tuned tiers and 66% cheaper than the best single threshold.

**Speed:** the engine alone scores about 12,800 payments per second on one Python thread (p50 63 microseconds, p99 151 microseconds, features through explanation). Inside the live server the UI shows roughly 200 microseconds.

## Where it is weak (shown, not hidden)

- **Step-up is not a silver bullet.** The policy assumes 8% of fraudsters pass an OTP challenge. In the simulator a SIM-swapper receives the OTP, a vished customer reads it out and a scammed customer approves it, so those pass 45% to 60% of the time. Stopping them takes friction aimed at the scam: first-payee warnings, cooling-off periods, blocking screen-share.
- **Scams without a screen-share** are the hardest case: 64% to 68% declined outright.
- **IMPS transfers** touch 13.6% of good customers, because large transfers to new beneficiaries look like account takeover.
- **Rent day** (a large first payment to a new account) is flagged 66% of the time.
- **Shared kiosk phones** still draw 15% friction.
- The SIM-change signal assumes telecom data that only some banks receive; the simulator reflects that with 60% coverage.

## Facts this project relies on

- RBI's circular on [limiting customer liability in unauthorised electronic banking transactions](https://www.rbi.org.in/scripts/FS_Notification.aspx?Id=11040) (6 July 2017): zero liability when reported within three working days, which is why the cost model assumes the bank carries the loss.
- UPI [per-transaction limits](https://www.businesstoday.in/personal-finance/banking/story/npci-to-increase-upi-transaction-limits-for-high-value-payments-from-sept-15-check-updated-limits-493278-2025-09-09): Rs 1 lakh for standard and P2P payments, up to Rs 5 lakh for some merchant categories. The structuring signal hugs Rs 50k, 1 lakh and 2 lakh.
- NPCI's [0.4% MDR on specified merchant payments above Rs 2,000](https://www.khaleejtimes.com/asia/india-charge-some-merchants-up-to-rs300-upi-transactions-over-rs2000), effective 15 October 2026; P2P and smaller payments stay free.
- The I4C [Suspect Registry](https://www.policyedge.in/p/i4c-and-rbih-partner-to-use-ai-for-detecting-mule-accounts-and-financial-fraud) for mule accounts, and the [1930 helpline and cybercrime.gov.in](https://moneylife.in/article/fraud-alert-illegal-payment-gateways-and-mule-bank-accounts/75513.html) used in the customer messages.
- A report that fraudsters are [shifting to India-based mule accounts](https://www.latestly.com/agency-news/business-news-fraudsters-increasingly-using-india-based-mule-accounts-to-move-stolen-money-report-7532900.html/amp), which is why payee-side signals carry so much weight.

These informed modelling assumptions. This is not legal or compliance advice, and the simulator is not a model of any real bank's customers.

## API

`POST /api/score` with `{uid, amt, cat, chan (upi|ecom|pos|atm|imps), mid, pers?, coll?, rat?, sim?, city, dev?, ip?, ts?, commit?}` returns the decision, probability, reason codes, exact contributions, expected cost of each action, the explanation and the bilingual customer message. Also: `GET /api/stream` (SSE), `GET /api/case/{id}`, `GET /api/drift`, `POST /api/feedback`, `GET|POST /api/policy`, `POST /api/policy/lab`, `POST /api/attack`, `POST /api/sim` (speed, pause, fraud pressure, festival surge), `GET /api/model`.

## With real data, next

Replace the simulator with real complaint feeds and the I4C registry; add interaction terms and monotonic constraints to the GAM; learn step-up pass rates per attack type from live outcomes; add scam-specific friction (first-payee warnings, cooling-off) as a fourth action; move state to Redis or a stream processor; run a champion-challenger harness behind the drift monitor.

MIT licensed.
