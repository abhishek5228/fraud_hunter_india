# Resume bullets for Fraud Hunter India

Pick two or three. Each uses only numbers that are measured and reproducible from the repo (`python -m fh.train`, `python -m pytest`, `python -m fh.backtest`). All of them say "simulated" because the data is.

## Project line
**Fraud Hunter India** | Python, FastAPI, NumPy, JavaScript, SQLite, Docker | github.com/abhishek5228/fraud_hunter_india

## Bullets (choose 2 to 4)
- Built a real-time risk engine for UPI, IMPS and card payments that picks approve, step-up or decline by expected cost in rupees; on a simulated 12-day holdout it caught 98.6% of fraud while touching 2.7% of good customers, at about 12,700 decisions per second on one Python thread.
- Designed streaming features without label leakage: velocity windows, per-customer profiles, device, network and payee graphs (mule fan-in), SIM-change and screen-share signals, and 7-day complaint counts that arrive hours late.
- Wrote a boosted additive model from scratch in NumPy so every decision decomposes exactly into per-factor contributions; landed within 0.011 average precision of a logistic baseline (0.960 vs 0.971) and documented that result rather than hiding it.
- Found and fixed my own evaluation errors: an AUC of 1.0 from an over-easy simulator, rules that blocked 10x more good customers than the model, and a bug where a step-up challenge made the engine trust a fraudster's device. Added tests so each stays fixed (36 tests).
- Built an automated red team (evolutionary search over 12 attack levers, scored by the production engine on sandboxed copies of customer history) that found a limit-structuring blind spot worth about Rs 2.6 lakh per simulated customer; training on its findings cut the median haul 86% for 0.4 points more friction, and I reported that later rounds did not reliably improve and the best of three searches still found Rs 1.2 lakh.
- Shipped a backtest tool that replays a customer's CSV of past payments through an isolated copy of the engine and reports fraud stopped, good customers touched and rupees saved, with warm-up handling and warnings when the history is too short.
- Built a live operations dashboard (vanilla JS, no build step) with streaming decisions, an analyst review queue, a policy lab, drift monitoring (PSI) and English and Hindi customer messages; deployable as a single container, a static site, or a 3 MB offline demo.

## One-line version
Built and tested a real-time UPI fraud-decision engine on simulated data: exact explanations, cost-aware decisions, a backtest tool and a live dashboard.

## Added: real-time integrations
- Connected the engine to Razorpay test-mode webhooks (HMAC-verified, payer identity hashed), with IP/network intelligence and Telegram alerts; decisions return in about 0.2 ms engine time.
- Found by hand that a Rs 25 lakh UPI payment from a new customer was approved (model extrapolation); fixed with escalate-only guardrails and a regression test. Say this one out loud: it shows testing, not just building.

## Do not claim
- That it detects real fraud or has been used on real payments. It was trained and tested on simulated data only.
- The headline numbers without "simulated". Judges and interviewers will ask.
- That the Razorpay link means it works on live money. It ran on test-mode payments only.
- Production readiness. It has an API key, an audit log and a review queue, but no rate limiting, role-based access or horizontal scaling.

## What to say when asked about the red team
It is a search over a fixed menu of attack levers against a simulator, so a good result means those holes closed, not that none remain. Say the number as a range: median Rs 2.6 lakh before, Rs 35 thousand after one round, best-of-three Rs 1.2 lakh. Say that rounds two and three did not help reliably.

## What to say when asked about the weak spots
The README lists them: scams with no technical tell are only partly caught, IMPS transfers touch about one good customer in five, the payee fan-in rule produces false alarms on a short history, and the engine needs about a month of customer history before its friction is fair. Naming these yourself is worth more than any extra percentage point.
