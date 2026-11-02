"""Real public datasets, usable from the web console: check what is on the server, download it from its source, upload your own copy,
run the benchmarks, and replay real transactions through the model.

Nothing here is bundled in the repository. Files live in FH_DATA_DIR (default ./data, git-ignored). Downloads come only from the fixed
source URLs below (override with FH_URL_<ID>), so the server cannot be pointed at arbitrary addresses.

Datasets
  ulb        284,807 real European card transactions (Worldline / ULB), 492 fraud. 28 anonymised components, amount, time. No customer ids.
  smishtank  about 1,000 real smishing texts reported by the public
  uci_sms    the UCI SMS Spam Collection, 5,574 real SMS (ham / spam)
  nus_sms    the NUS SMS Corpus, tens of thousands of real ordinary SMS (used for false alarms)
"""
import gc
import csv
import json
import os
import random
import tempfile
import threading
import time
import urllib.request

import numpy as np

from . import model as mdl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH = "https://raw.githubusercontent.com/"
DATASETS = {
    "ulb": dict(title="ULB / Worldline credit-card fraud", file="creditcard.csv", max_mb=220, kind="transactions",
                url=os.environ.get("FH_URL_ULB", "https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv"),
                expect=dict(rows=284807, pos=492), source="Dal Pozzolo et al., Worldline and ULB Machine Learning Group; Kaggle mlg-ulb/creditcardfraud",
                note="Real European card payments from two days in September 2013. Features are anonymised with PCA, so there are no customer, device or payee ids."),
    "smishtank": dict(title="Smishtank real smishing texts", file="smishtank.csv", max_mb=8, kind="texts",
                      url=os.environ.get("FH_URL_SMISHTANK", GH + "Joshoneill6649/smishing-nlp-josh-oneill/main/data/raw/smishtank.csv"),
                      expect=dict(rows=1000), source="Timko and Rahman, smishtank.com (arXiv 2402.18430)",
                      note="Smishing texts reported by the public. Mostly US and English."),
    "uci_sms": dict(title="UCI SMS Spam Collection", file="sms_spam_collection.tsv", max_mb=8, kind="texts",
                    url=os.environ.get("FH_URL_UCI_SMS", GH + "justmarkham/pycon-2016-tutorial/master/data/sms.tsv"),
                    expect=dict(rows=5000), source="Almeida and Hidalgo, UCI Machine Learning Repository dataset 228",
                    note="Real SMS labelled ham or spam. Mostly UK and Singapore English."),
    "nus_sms": dict(title="NUS SMS Corpus", file="NUS_SMS_Corpus.json", max_mb=120, kind="texts",
                    url=os.environ.get("FH_URL_NUS_SMS", GH + "Joshoneill6649/smishing-nlp-josh-oneill/main/data/raw/NUS_SMS_Corpus.json"),
                    expect=dict(rows=40000), source="National University of Singapore SMS Corpus",
                    note="Tens of thousands of real, ordinary text messages, thousands of them sent from India. Used only to measure false alarms."),
}
RECORDED = dict(  # measured on 2026-11-01 with scikit-learn baselines; shown next to live runs for context. See docs/BENCHMARKS.md.
    ulb_time=[("Additive model (this project)", .980, .760, .667, .840, 86.7), ("Logistic regression (this project)", .971, .704, .600, .792, 86.7),
              ("Logistic regression (scikit-learn)", .973, .706, .609, .792, 86.7), ("Random forest (scikit-learn)", .941, .792, .705, .870, 86.7),
              ("Gradient boosting (scikit-learn, untuned)", .769, .475, .360, .592, 70.7)],
    shield=dict(before=dict(smish=7.8, ham_uci=.22, ham_nus=.08), after=dict(smish=46.6, ham_uci=.13, ham_nus=.03, india=.09)))


def data_dir():
    d = os.environ.get("FH_DATA_DIR") or os.path.join(ROOT, "data")
    os.makedirs(d, exist_ok=True)
    return d


def path(i):
    return os.path.join(data_dir(), DATASETS[i]["file"])


# ---------------------------------------------------------------- loading (light on memory)

def load_ulb(p):
    """Fill numpy arrays in blocks of 10,000 rows. Holding every row as Python floats first, or concatenating blocks,
    needs several times the memory, and a 512 MB server is killed by it."""
    with open(p, "rb") as f:
        n = sum(1 for _ in f) - 1
    with open(p, encoding="utf-8", newline="") as f:
        rd = csv.reader(f)
        h = next(rd)
        ix = {c: i for i, c in enumerate(h)}
        feat = [i for c, i in ix.items() if c not in ("Time", "Class")]
        names = [h[i] for i in feat]
        ic, it = ix["Class"], ix["Time"]
        X, y, ts = np.empty((n, len(feat))), np.empty(n), np.empty(n)
        blk, k = [], 0

        def flush():
            nonlocal k
            if blk:
                a = np.array(blk, dtype=np.float64)
                X[k:k + len(a)], y[k:k + len(a)], ts[k:k + len(a)] = a[:, feat], a[:, ic], a[:, it]
                k += len(a)
                blk.clear()
        for r in rd:
            if len(r) > it:
                blk.append(r)
            if len(blk) >= 10000:
                flush()
        flush()
    return X[:k], y[:k], ts[:k], names


def load_texts(i, p):
    """-> dict of lists. smishtank: {smish}; uci_sms: {ham, spam}; nus_sms: {nus, nus_in}."""
    if i == "smishtank":
        return dict(smish=sorted({r["text"].strip() for r in csv.DictReader(open(p, encoding="utf-8", errors="replace")) if (r.get("text") or "").strip()}))
    if i == "uci_sms":
        ham, spam = set(), set()
        for l in open(p, encoding="utf-8", errors="replace"):
            if "\t" in l:
                lab, t = l.rstrip("\n").split("\t", 1)
                (ham if lab == "ham" else spam if lab == "spam" else set()).add(t.strip())
        return dict(ham=sorted(ham), spam=sorted(spam))
    s = open(p, encoding="utf-8", errors="replace").read()           # NUS: parse message by message so memory stays near the file size
    k = s.index('"message"')
    k = s.index("[", k) + 1
    dec, nus, nus_in = json.JSONDecoder(), set(), set()
    n = len(s)
    while k < n:
        while k < n and s[k] in " \n\r\t,":
            k += 1
        if k >= n or s[k] == "]":
            break
        m, k = dec.raw_decode(s, k)
        t = (m.get("text") or {}).get("$")
        if t is None or not str(t).strip():
            continue
        c = (((m.get("source") or {}).get("userProfile") or {}).get("country") or {}).get("$")
        nus.add(str(t).strip())
        if c in ("IN", "India"):
            nus_in.add(str(t).strip())
    return dict(nus=sorted(nus), nus_in=sorted(nus_in))


def count(i, p):
    """Verify what is on disk: rows and, for card data, the number of fraud. Cheap enough to run on demand; cached by file size + mtime."""
    st = os.stat(p)
    key = (i, st.st_size, int(st.st_mtime))
    if key in _COUNT:
        return _COUNT[key]
    if i == "ulb":
        n = pos = 0
        with open(p, encoding="utf-8", newline="") as f:
            rd = csv.reader(f)
            h = next(rd)
            c = h.index("Class")
            for r in rd:
                n += 1
                pos += int(float(r[c]))
        out = dict(rows=n, pos=pos)
    else:
        d = load_texts(i, p)
        out = dict(rows=len(d.get("nus", [])) if i == "nus_sms" else sum(len(v) for v in d.values()), parts={k: len(v) for k, v in d.items()})
    _COUNT[key] = out
    return out


_COUNT = {}


def status(i, verify=False):
    d = DATASETS[i]
    p = path(i)
    out = dict(id=i, title=d["title"], kind=d["kind"], file=d["file"], source=d["source"], note=d["note"], url=d["url"], max_mb=d["max_mb"], present=os.path.exists(p))
    if out["present"]:
        out["size_mb"] = round(os.path.getsize(p) / 1e6, 1)
        if verify:
            try:
                c = count(i, p)
                out["counts"] = c
                e = d["expect"]
                out["verified"] = c["rows"] >= e["rows"] and (c.get("pos") == e.get("pos", c.get("pos")))
            except Exception as ex:                                    # a wrong or damaged file must be reported, not crash the page
                out["verified"], out["error"] = False, "cannot read this file: %s" % type(ex).__name__
    return out


# ---------------------------------------------------------------- download and upload

def fetch(i, progress=None):
    d = DATASETS[i]
    if not d["url"].startswith("https://"):
        raise ValueError("source must be an https address")
    req = urllib.request.Request(d["url"], headers={"User-Agent": "fraud-hunter-realdata/1.0"})
    fd, tmp = tempfile.mkstemp(dir=data_dir(), suffix=".part")
    got, cap = 0, d["max_mb"] * 1_000_000
    try:
        with urllib.request.urlopen(req, timeout=60) as r, os.fdopen(fd, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                got += len(b)
                if got > cap:
                    raise ValueError("file is larger than the %d MB limit" % d["max_mb"])
                f.write(b)
                if progress:
                    progress(got)
        os.replace(tmp, path(i))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return got


async def receive(i, request):
    """Stream an uploaded body to disk under the size limit. Replaces the file only when it parses."""
    cap = DATASETS[i]["max_mb"] * 1_000_000
    fd, tmp = tempfile.mkstemp(dir=data_dir(), suffix=".part")
    got = 0
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in request.stream():
                got += len(chunk)
                if got > cap:
                    raise ValueError("file is larger than the %d MB limit" % DATASETS[i]["max_mb"])
                f.write(chunk)
        if got == 0:
            raise ValueError("empty upload")
        c = count(i, tmp)                                              # parse before accepting
        if c["rows"] < 50:
            raise ValueError("only %d usable rows found; is this the right kind of file?" % c["rows"])
        os.replace(tmp, path(i))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return got


# ---------------------------------------------------------------- benchmarks

def _split_time(ts):
    n = len(ts)
    o = np.argsort(ts, kind="stable")
    rk = np.empty(n, int)
    rk[o] = np.arange(n)
    return rk < .65 * n, (rk >= .65 * n) & (rk < .8 * n), rk >= .8 * n


def _boot(y, p, k=200, seed=1):
    rng, a = np.random.RandomState(seed), []
    for _ in range(k):
        i = rng.randint(0, len(y), len(y))
        if y[i].sum() > 0:
            a.append(mdl.avg_prec(y[i], p[i]))
    return [float(v) for v in np.percentile(a, [2.5, 97.5])]


STATE = {}      # the last ULB run's test rows and scores, for replay


def bench_ulb(progress=lambda *a: None):
    p = path("ulb")
    if not os.path.exists(p):
        raise ValueError("the card-fraud file is not on the server yet")
    t0 = time.time()
    progress(0.05, "reading the file")
    X, y, ts, names = load_ulb(p)
    tr, va, te = _split_time(ts)
    if y[te].sum() < 5 or y[tr].sum() < 30:
        raise ValueError("this file has too little fraud to benchmark (%d fraud in the test part)" % y[te].sum())
    ai = names.index("Amount") if "Amount" in names else None
    Xtr, Xva, Xte = X[tr], X[va], X[te]
    amt = Xte[:, ai].copy() if ai is not None else np.zeros(len(Xte))
    ytr, yva, yte, tte, ntr, nrows, nfr = y[tr], y[va], y[te], ts[te], int(tr.sum()), len(y), int(y.sum())
    del X, ts, y                                                       # a 512 MB server is killed if the full table is kept next to the three slices
    gc.collect()
    progress(0.15, "fitting the additive model on %d payments" % ntr)
    g = mdl.GAM(names).fit(Xtr, ytr, Xva, yva, log=lambda *a: None)
    gc.collect()
    progress(0.75, "fitting logistic regression")
    lr = mdl.LR().fit(Xtr, ytr)
    pg, pl = g.predict(Xte), lr.predict(Xte)
    pv = g.predict(Xva)
    del Xtr, Xte
    gc.collect()
    progress(0.9, "bootstrap intervals")
    res = []
    for name, pr in (("Additive model (this project)", pg), ("Logistic regression (this project)", pl)):
        lo, hi = _boot(yte, pr)
        res.append(dict(name=name, auc=mdl.roc_auc(yte, pr), ap=mdl.avg_prec(yte, pr), ap_lo=lo, ap_hi=hi,
                        rec1=mdl.recall_at_fpr(yte, pr, .01), rec01=mdl.recall_at_fpr(yte, pr, .001)))
    # the operating point for replay: the score that flags 1% of the honest payments in the validation period
    thr = float(np.quantile(pv[yva == 0], 0.99))
    STATE["ulb"] = dict(idx=np.where(te)[0], p=pg, y=yte, amt=amt, ts=tte, thr=thr)
    return dict(dataset="ulb", rows=nrows, fraud=nfr, train=ntr, test=int(te.sum()), test_fraud=int(yte.sum()), threshold=thr,
                models=res, seconds=round(time.time() - t0, 1), split="time-ordered: train on the earliest 65%, test on the latest 20%")


def replay(offset, n, to_fraud=False):
    s = STATE.get("ulb")
    if not s:
        raise ValueError("run the card-fraud benchmark first; it trains the model that scores the replay")
    N = len(s["p"])
    if to_fraud:                                                       # jump to the next real fraud, starting a few payments earlier for context
        nxt = np.where(s["y"][offset:] == 1)[0]
        if len(nxt):
            offset = max(offset, offset + int(nxt[0]) - 6)
    offset = max(0, min(offset, N))
    j = slice(offset, min(N, offset + max(1, min(n, 200))))
    rows = [dict(i=int(offset + k), t=float(s["ts"][j][k]), amt=float(s["amt"][j][k]), p=float(s["p"][j][k]), flag=bool(s["p"][j][k] >= s["thr"]), fraud=bool(s["y"][j][k])) for k in range(len(s["p"][j]))]
    done = slice(0, offset + len(rows))
    flag, fr, amt, p = s["p"][done] >= s["thr"], s["y"][done] == 1, s["amt"][done], s["p"][done]
    kp = dict(seen=int(len(p)), fraud=int(fr.sum()), caught=int((flag & fr).sum()), missed=int((~flag & fr).sum()), false_alarms=int((flag & ~fr).sum()),
              amount_caught=float(amt[flag & fr].sum()), amount_missed=float(amt[~flag & fr].sum()), amount_total=float(amt.sum()))
    return dict(rows=rows, kpi=kp, total=N, threshold=s["thr"])


def _split_texts(d, seed):
    rng = random.Random(seed)
    dev, test = {}, {}
    for k, v in d.items():
        v = list(v)
        rng.shuffle(v)
        h = len(v) // 2
        dev[k], test[k] = v[:h], v[h:]
    return dev, test


def load_all_texts():
    out = {}
    for i in ("smishtank", "uci_sms", "nus_sms"):
        if os.path.exists(path(i)):
            out.update(load_texts(i, path(i)))
    return out


def bench_shield(progress=lambda *a: None, seed=7):
    from . import shield
    progress(0.05, "reading the message collections")
    d = load_all_texts()
    if not d.get("smish"):
        raise ValueError("the smishing collection is not on the server yet")
    progress(0.2, "splitting into development and test halves")
    test = _split_texts(d, seed)[1]
    groups = [("smish", "Real smishing (Smishtank)"), ("spam", "Real SMS spam (UCI)"), ("ham", "Real ordinary SMS (UCI)"), ("nus", "Real ordinary SMS (NUS corpus)"), ("nus_in", "  of which sent from India")]
    rows, flagged = [], {}
    for n, (k, label) in enumerate(groups):
        v = test.get(k)
        if not v:
            continue
        progress(0.25 + 0.7 * n / len(groups), "checking %s" % label.strip())
        lv = [shield.check(t)["level"] for t in v]
        flagged[k] = lv
        rows.append(dict(group=label, key=k, n=len(v), caution=sum(1 for x in lv if x != "none") / len(v), danger=sum(1 for x in lv if x == "danger") / len(v)))
    pos = flagged.get("smish", [])
    neg = (flagged.get("ham", []) + flagged.get("nus", []))
    tp, fp = sum(1 for x in pos if x != "none"), sum(1 for x in neg if x != "none")
    return dict(dataset="shield", rows=rows, rules=len(shield.RULES), seed=seed, n_smish=len(pos), n_ordinary=len(neg),
                recall=tp / len(pos) if pos else None, false_alarm=fp / len(neg) if neg else None, precision=tp / (tp + fp) if tp + fp else None,
                split="a fixed 50/50 split of the real messages, reporting the TEST half")


def sample_text(kind, rng=random):
    """A random real message, with its true label, for trying in Scam Shield."""
    key = dict(smish=("smish", "smishing"), spam=("spam", "spam"), ham=("ham", "ordinary"), india=("nus_in", "ordinary, sent from India"))[kind]
    d = load_all_texts()
    v = d.get(key[0])
    if not v:
        raise ValueError("that collection is not on the server yet")
    return dict(text=rng.choice(v), truth=key[1], source=key[0])


# ---------------------------------------------------------------- one job at a time (memory is small on a free host)

JOBS, _LOCK = {}, threading.Lock()


def start(kind, fn):
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("another job is running; wait for it to finish")
    jid = "j%d" % int(time.time() * 1000)
    JOBS[jid] = dict(id=jid, kind=kind, state="running", progress=0.0, msg="starting", result=None, error=None, t0=time.time())
    for old in list(JOBS)[:-6]:
        JOBS.pop(old, None)

    def prog(f, m=""):
        JOBS[jid].update(progress=float(f), msg=m)

    def run():
        try:
            JOBS[jid].update(result=fn(prog), state="done", progress=1.0, msg="done")
        except Exception as e:                                          # report any failure to the page instead of dying silently
            JOBS[jid].update(state="error", error="%s" % (e if isinstance(e, ValueError) else "%s: %s" % (type(e).__name__, e)))
        finally:
            _LOCK.release()
    threading.Thread(target=run, daemon=True).start()
    return jid
