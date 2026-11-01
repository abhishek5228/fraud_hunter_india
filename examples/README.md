# Examples

Small scripts that talk to a running server (default `http://localhost:8000`; pass another URL as the first argument or set `FH_URL`). Start one with `python -m uvicorn fh.api:app --port 8000`.

| File | What it shows |
|---|---|
| `score.py` | Score three payments and print the decision, rules and reasons |
| `shield_check.py` | Check a scam message with Scam Shield |
| `webhook_curl.sh` | Send a correctly signed Razorpay-style webhook (needs `RAZORPAY_WEBHOOK_SECRET`) |
| `backtest_sample.sh` | Backtest the bundled 45-day sample from the command line |
