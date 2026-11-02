# Changelog

All dates are 2026. Format follows [Keep a Changelog](https://keepachangelog.com).

## [Unreleased]
### Security
- Per-IP limits on the Real data download, upload, benchmark, replay and sample endpoints, so a server without `FH_API_KEY` cannot be used to start repeated large jobs; replay size is capped.

### Fixed
- The Real data benchmarks now download any missing collection from their fixed source before running. A free server forgets its files on every restart, which left the Run buttons stuck on 'download first'.
- The real card-fraud benchmark was killed by the 512 MB limit on the free Render plan (it held the whole file as Python floats, then three copies). The loader now fills numpy arrays in blocks and the table is freed before the models are fitted: peak memory fell from about 280 MB to about 220 MB in a local test.
- Mule-graph hub ids were 4 characters, so two payees could share one and a ruling could hit the wrong payee. Ids are now 8 characters, with a regression test.

### Added
- Live ops can show real data: a switch above the feed replays the real card transactions in time order, scored one by one, with the true outcome beside each. The simulator stays the default.
- A 30-second summary at the top of the README.
- **Real data tab** in the console: download real public datasets from their sources (or upload your own), run the card-fraud and Scam Shield benchmarks, replay real card transactions with their true labels, and try real text messages in Scam Shield. A provenance strip on every tab says what is simulated, real or yours.
- **Real-data benchmarks** (`docs/BENCHMARKS.md`): the additive model on 284,807 real card transactions (`tools/benchmark_ulb.py`) and Scam Shield on about 55,000 real text messages (`tools/eval_shield.py`).
- 11 generic smishing rules for Scam Shield (parcel fees, locked accounts, refunds, subscription failures, bait, crypto groups and more); 26 rules in total.
- `python -m fh.fit --max-rows` to use more than 150,000 rows.
- A test that the browser and server rule implementations agree.

### Fixed
- Buttons given a boolean `disabled: false` were rendered disabled (the helper wrote the string "false"); this had left the cross-bank export and import buttons permanently disabled.
- Scam Shield false alarms found on real ordinary texts: `you won't`, a friend talking about an `.apk` file, a KBC joke, `.lol` slang read as a web address, `expired` about a person.
- Scam Shield caught only 7.8% of real smishing before the generic rules; now 46.4% on a held-out half.

### Also
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
