"""Write the sample transactions CSV used by the backtest tool: 45 days, 400 customers, simulated after training.

    python tools/make_sample_csv.py            -> samples/sample_transactions.csv
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fh.sample import sample_csv                # noqa: E402

os.makedirs(os.path.join(ROOT, "samples"), exist_ok=True)
path = os.path.join(ROOT, "samples", "sample_transactions.csv")
txt = sample_csv()
open(path, "w").write(txt)
n = txt.count("\n") - 1
print("%s: %d rows, %.1f MB" % (path, n, len(txt) / 1e6))
