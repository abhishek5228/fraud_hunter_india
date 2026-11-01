# Changelog

All dates are 2026. Format follows [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]
- Small documentation, examples, tests and tooling improvements.

## 2026-11-01
### Added
- Live links in the README (console, demo, API docs, health check).

## 2026-10-31
### Added
- **Engine:** streaming feature store (44 features), additive model written from scratch in numpy, logistic baseline, escalate-only guardrail rules, expected-cost policy with rail-aware margins, two-phase step-up, windowed reputation, bilingual customer messages, PSI drift monitor.
- **India:** UPI, IMPS, card and ATM rails in rupees; payee graph (mule fan-in), SIM-swap and screen-share signals; UPI-MDR-aware margins.
- **Console:** Live ops, Review queue, Backtest, Red team, Policy lab, Playground, Model card.
- **Backtest, audit log, state snapshots, API key, review queue.**
- **Red team:** an evolutionary attacker and a hardening loop.
- **CSV tools:** `fh.ingest` (read almost any CSV) and `fh.fit` (fit the model to your CSV, with a leakage guard).
- **Live wire:** signed Razorpay webhook, IP and network intelligence, Telegram and Slack alerts, load test.
- **Scam Shield, mule graph, analyst copilot with STR draft, fairness report, SDKs, OpenAPI and Postman collection.**
- **Cross-bank sharing:** keyed hashes and private set intersection.
- **AI wording** for analyst briefs (Gemini or Claude), facts only, payee masked.
- README rewritten with every feature explained, real examples and diagrams.

### Fixed
- A UPI payment of Rs 25 lakh from a brand-new customer was approved; added `EXCEEDS_UPI_LIMIT` and `NEW_CUSTOMER_HIGH_VALUE`.
- Older state snapshots crashed after an upgrade; new fields now get safe defaults.
- Rebuilding the demo halfway broke its Playground; `make demo` now does the full sequence and checks it.
- The header clipped the "Launch attack" menu and hid control labels; it now wraps, and shows the real India clock.
