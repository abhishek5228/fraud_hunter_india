"""Train the small learned part of Scam Shield on real public SMS, and report it honestly.

    FH_DATA_DIR=./data python tools/train_shield_model.py [--seed 7] [--write]

Reads the collections the Real data tab fetches (smishtank, uci_sms, nus_sms, india_sms). The messages are split 50/50 by the same fixed
seed as tools/eval_shield.py. The model is fitted on DEV only: its words, its settings and its threshold (chosen from out-of-fold
predictions on DEV so the false-alarm rate on ordinary texts stays near the target). TEST is only used to report. With --write the model
is stored in fh/shield_rules.json, where the browser reads it too."""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fh import realdata as rd, shield  # noqa: E402

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fh", "shield_rules.json")


def feats(texts, vocab):
    X = np.zeros((len(texts), len(vocab)), np.float32)
    for r, t in enumerate(texts):
        for k in set(shield.tokens(t)):
            j = vocab.get(k)
            if j is not None:
                X[r, j] = 1
    return X


def fit(X, y, lam, it=400, lr=0.5):
    """Logistic regression with L2 and class balancing, plain gradient descent."""
    n, d = X.shape
    w, b = np.zeros(d, np.float32), 0.0
    sw = np.where(y == 1, 0.5 / max(1, y.sum()), 0.5 / max(1, (1 - y).sum())).astype(np.float32) * n
    for _ in range(it):
        z = X @ w + b
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = (p - y) * sw
        w -= lr * (X.T @ g / n + lam * w)
        b -= lr * g.mean()
    return w, float(b)


def score(X, w, b):
    return 1 / (1 + np.exp(-np.clip(X @ w + b, -30, 30)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--target-fa", type=float, default=0.001, help="false-alarm rate on ordinary DEV texts the threshold is set for")
    ap.add_argument("--vocab", type=int, default=3000)
    ap.add_argument("--lam", type=float, default=0.002)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    d = rd.load_all_texts()
    if not d.get("smish"):
        sys.exit("fetch the collections first (Real data tab, or FH_DATA_DIR with the files)")
    dev, test = rd._split_texts(d, a.seed)
    held = set().union(*[set(v) for v in test.values()])                 # nothing that is in any TEST group may reach training
    pos = [t for t in dev["smish"] if t not in held]
    rng = np.random.default_rng(a.seed)
    neg = [t for k in ("ham", "in_ham") for t in dev.get(k, []) if t not in held]
    nus = [t for t in dev.get("nus", []) if t not in held]
    neg += [nus[i] for i in rng.permutation(len(nus))[:6000]]
    print("train: %d smishing, %d ordinary (UCI %d, India %d, NUS sample %d)" % (len(pos), len(neg), len([t for t in dev["ham"] if t not in held]), len([t for t in dev.get("in_ham", []) if t not in held]), min(6000, len(nus))))
    # vocabulary: words common in smishing, plus common words of ordinary texts so the model can tell them apart
    from collections import Counter
    cp, cn = Counter(), Counter()
    for t in pos:
        cp.update(set(shield.tokens(t)))
    for t in neg:
        cn.update(set(shield.tokens(t)))
    keep = [k for k, c in cp.most_common() if c >= 3][: int(a.vocab * 0.75)]
    keep += [k for k, c in cn.most_common() if c >= 8 and k not in set(keep)][: a.vocab - len(keep)]
    vocab = {k: i for i, k in enumerate(keep)}
    texts = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg), np.float32)
    X = feats(texts, vocab)
    # out-of-fold scores on DEV choose the threshold
    folds = rng.integers(0, 5, len(y))
    oof = np.zeros(len(y), np.float32)
    for f in range(5):
        w, b = fit(X[folds != f], y[folds != f], a.lam)
        oof[folds == f] = score(X[folds == f], w, b)
    neg_s = np.sort(oof[y == 0])[::-1]
    k = max(1, int(round(a.target_fa * len(neg_s))))
    thr = float(neg_s[k - 1]) + 1e-6
    print("DEV out-of-fold: threshold %.3f gives %.2f%% ordinary flagged and %.1f%% of smishing" % (thr, 100 * (oof[y == 0] >= thr).mean(), 100 * (oof[y == 1] >= thr).mean()))
    w, b = fit(X, y, a.lam)
    M = dict(bias=round(b, 4), w={k: round(float(w[i]), 3) for k, i in vocab.items() if abs(w[i]) >= 0.05}, t=round(thr, 4), hit_w=35,
             en="The wording resembles real smishing texts. This comes from a small model trained on public messages, not from a named scam rule.",
             hi="इस संदेश की भाषा असली ठगी वाले SMS जैसी है। यह नाम वाले नियम से नहीं, सार्वजनिक संदेशों पर सीखे एक छोटे मॉडल से आया है।",
             trained_on="%d real smishing and %d real ordinary messages (DEV half only), seed %d" % (len(pos), len(neg), a.seed))
    # TEST report: rules alone against rules plus the model
    base = dict(shield._R)
    rows = {}
    for tag, mdl in (("rules only", None), ("rules + model", M)):
        shield._R = dict(base)
        if mdl:
            shield._R["model"] = mdl
        else:
            shield._R.pop("model", None)
        out = {}
        for key in ("smish", "spam", "ham", "nus", "nus_in", "in_ham", "in_spam"):
            v = test.get(key, [])
            if v:
                lv = [shield.check(t)["level"] for t in v]
                out[key] = (len(v), sum(1 for x in lv if x != "none") / len(v), sum(1 for x in lv if x == "danger") / len(v))
        rows[tag] = out
    shield._R = base
    names = dict(smish="real smishing (Smishtank)", spam="real SMS spam (UCI)", ham="ordinary (UCI)", nus="ordinary (NUS)", nus_in="  ordinary, sent from India", in_ham="ordinary Indian (telecom collection)", in_spam="Indian spam, mostly promotions")
    print("\\nTEST half, flagged at caution or higher (danger in brackets):")
    for key in names:
        if key in rows["rules only"]:
            n, c0, d0 = rows["rules only"][key]
            _, c1, d1 = rows["rules + model"][key]
            print("  %-42s n=%-6d rules %5.2f%% (%4.1f%%)   rules+model %5.2f%% (%4.1f%%)" % (names[key], n, 100 * c0, 100 * d0, 100 * c1, 100 * d1))
    print("model: %d words, threshold %.3f" % (len(M["w"]), M["t"]))
    if a.write:
        R = json.load(open(RULES, encoding="utf-8"))
        R["model"] = M
        json.dump(R, open(RULES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("written to", os.path.normpath(RULES))


if __name__ == "__main__":
    main()
