#!/usr/bin/env bash
# Backtest the bundled 45-day sample from the command line (no server needed; run `python -m fh.train` first).
#   bash examples/backtest_sample.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python -m fh.backtest samples/sample_transactions.csv --out /tmp/decisions.csv --json /tmp/summary.json
echo "Per-payment decisions: /tmp/decisions.csv    Summary: /tmp/summary.json"
