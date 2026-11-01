"""Measure Scam Shield on real public SMS collections.

    python tools/eval_shield.py --smishtank smishtank.csv --uci sms_spam_collection.csv --nus NUS_SMS_Corpus.json [--seed 7] [--show-fp N] [--show-miss N]

Data (not redistributed here; see docs/BENCHMARKS.md for where to get it):
  smishtank   1,000+ real smishing texts reported by the public (label: smish)
  uci         the UCI SMS Spam Collection (5,574 real SMS, ham/spam)
  nus         the NUS SMS Corpus (tens of thousands of real, ordinary SMS; used for false positives)

The data is split 50/50 by a fixed seed into DEV and TEST. Rules may be tuned by reading DEV only; TEST is what gets reported.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import realdata as rd, shield


def load(a):
    d = dict(rd.load_texts("smishtank", a.smishtank))
    d.update(rd.load_texts("uci_sms", a.uci))
    d.update(rd.load_texts("nus_sms", a.nus) if a.nus else dict(nus=[], nus_in=[]))
    d["uci_ham"] = d.pop("ham")
    return d


def split(d, seed):
    return rd._split_texts(d, seed)


def rate(texts, level):
    if not texts:
        return float("nan"), 0, 0
    lv = [shield.check(t)["level"] for t in texts]
    k = sum(1 for x in lv if (x != "none" if level == "caution" else x == "danger"))
    return k / len(texts), k, len(texts)


def report(name, d):
    print("\n== %s ==" % name)
    print("%-34s %8s %10s %10s" % ("group", "n", ">=caution", "danger"))
    for k, label in (("smish", "real smishing (smishtank)"), ("spam", "real SMS spam (UCI)"), ("uci_ham", "real ordinary SMS (UCI ham)"), ("nus", "real ordinary SMS (NUS corpus)"), ("nus_in", "  of which sent in India")):
        c, kc, n = rate(d[k], "caution")
        r, kd, _ = rate(d[k], "danger")
        print("%-34s %8d %9.2f%% %9.2f%%" % (label, n, 100 * c, 100 * r))
    pos = d["smish"]
    neg = d["uci_ham"] + d["nus"]
    tp = sum(1 for t in pos if shield.check(t)["level"] != "none")
    fp = sum(1 for t in neg if shield.check(t)["level"] != "none")
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / len(pos)
    print("smishing vs ordinary SMS at >=caution: recall %.1f%%, precision %.1f%%, false-alarm rate %.2f%% (precision depends on the mix: %d smishing vs %d ordinary)" % (
        100 * rec, 100 * prec, 100 * fp / len(neg), len(pos), len(neg)))
    return fp, neg


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smishtank", required=True); ap.add_argument("--uci", required=True); ap.add_argument("--nus")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", choices=["dev", "test", "all"], default="test")
    ap.add_argument("--show-fp", type=int, default=0); ap.add_argument("--show-miss", type=int, default=0)
    a = ap.parse_args()
    d = load(a)
    dev, test = split(d, a.seed)
    sets = dict(dev=dev, test=test, all=d)
    s = sets[a.only]
    report(a.only.upper(), s)
    if a.show_fp:
        print("\nfalse alarms on ordinary SMS:")
        for t in (s["uci_ham"] + s["nus"]):
            r = shield.check(t)
            if r["level"] != "none":
                print("  [%s %d] %s  <- %s" % (r["level"], r["score"], t[:140].replace("\n", " "), ",".join(x["id"] for x in r["reasons"])))
                a.show_fp -= 1
                if a.show_fp <= 0:
                    break
    if a.show_miss:
        print("\nsmishing missed:")
        n = 0
        for t in s["smish"]:
            if shield.check(t)["level"] == "none":
                print("  ", t[:160].replace("\n", " ")); n += 1
                if n >= a.show_miss:
                    break
