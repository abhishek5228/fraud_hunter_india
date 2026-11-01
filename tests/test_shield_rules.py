"""One test per Scam Shield rule: a message that should trigger it, and one that should not."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import shield


def ids(text):
    return {r["id"] for r in shield.check(text)["reasons"]}
