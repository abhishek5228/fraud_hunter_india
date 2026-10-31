"""Ingest: turn almost any transactions CSV into the engine's canonical columns.

    python -m fh.ingest raw.csv --out canon.csv [--map uid=sender_id,mid=receiver_id] [--chan upi] [--city Mumbai]

Column names are matched by alias (sender_id, nameOrig, cc_num -> uid ...). Values are normalised: timestamps in many
formats, channel words (P2P, NEFT, card ...) -> upi/ecom/pos/atm/imps, Indian states -> a city, fraud labels -> 0/1.
What cannot be found is reported, never invented. Missing location means no geo signal, and that is said out loud.
"""
import argparse
import csv
import datetime as dt
import io
import json
import re
import sys

from . import backtest as bt
from .geo import CITY

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

ALIAS = dict(
    ts=["ts", "timestamp", "datetime", "date_time", "trans_date_trans_time", "txn_time", "transaction_time", "transaction_date",
        "txn_date", "date", "time", "unix_time"],
    uid=["uid", "sender_id", "user_id", "customer_id", "customer", "nameorig", "cc_num", "account_id", "payer_id", "payer",
         "sender", "from_account", "client_id", "card_id", "account"],
    mid=["mid", "receiver_id", "merchant_id", "merchant", "payee_id", "payee", "namedest", "beneficiary", "receiver", "to_account",
         "recipient", "recipient_id", "dest"],
    amt=["amt", "amount", "amount_inr", "transaction_amount", "txn_amount", "value", "trans_amount", "amount_rs"],
    chan=["chan", "channel", "transaction_type", "txn_type", "type", "payment_mode", "payment_method", "mode"],
    city=["city", "sender_city", "txn_city", "location_city", "sender_state", "state", "region", "location"],
    lat=["lat", "latitude", "merch_lat"],
    lon=["lon", "lng", "long", "longitude", "merch_long"],
    cat=["cat", "category", "merchant_category", "merchant_category_code", "mcc", "purpose"],
    dev=["dev", "device_id", "device", "imei"],
    ip=["ip", "ip_address", "ipaddress", "ip_addr"],
    label=["label", "is_fraud", "isfraud", "fraud", "fraud_flag", "fraud_label", "class", "target", "is_scam", "flag"],
    sim=["sim"],
    rat=["rat", "recognized_screen_sharing_apps", "screen_sharing", "screen_share", "remote_access"],
    coll=["coll", "collect_request", "is_collect"],
    pers=["pers", "is_p2p", "is_person"],
)
# patterns that must not be features: they ARE the answer (or computed from it)
LEAK = re.compile(r"fraud|scam|label|target|chargeback|is_bad|risk_score|pattern", re.I)

STATE_CITY = {
    "maharashtra": "Mumbai", "delhi": "Delhi", "karnataka": "Bengaluru", "telangana": "Hyderabad", "tamil nadu": "Chennai",
    "west bengal": "Kolkata", "gujarat": "Ahmedabad", "rajasthan": "Jaipur", "uttar pradesh": "Lucknow", "bihar": "Patna",
    "punjab": "Chandigarh", "haryana": "Chandigarh", "kerala": "Kochi", "madhya pradesh": "Indore", "assam": "Guwahati",
    "andhra pradesh": "Hyderabad", "odisha": "Kolkata", "jharkhand": "Patna", "chhattisgarh": "Indore", "uttarakhand": "Delhi",
    "himachal pradesh": "Chandigarh", "goa": "Pune", "jammu and kashmir": "Chandigarh", "j&k": "Chandigarh",
}
CITYMAP = {c[0].lower(): c[0] for c in CITY}
CITYMAP.update({"bangalore": "Bengaluru", "bombay": "Mumbai", "calcutta": "Kolkata", "madras": "Chennai", "gurgaon": "Delhi",
                "gurugram": "Delhi", "noida": "Delhi", "new delhi": "Delhi", "navi mumbai": "Mumbai", "thane": "Mumbai"})

CHAN_WORDS = [
    ("atm", ("atm", "cash_out", "cash out", "withdraw", "cash_in", "cash-in")),
    ("pos", ("pos", "card_present", "card present", "in_store", "in store", "swipe", "tap", "contactless", "offline")),
    ("ecom", ("ecom", "e-com", "online", "card", "web", "debit", "credit", "gateway", "net banking", "netbanking", "wallet", "app_purchase")),
    ("imps", ("imps", "neft", "rtgs", "transfer", "bank", "payment_to_bank")),
    ("upi", ("upi", "p2p", "p2m", "p2b", "collect", "qr", "peer", "merchant payment", "payment", "bhim", "gpay", "phonepe", "paytm", "debit")),
]
DATE_FMT = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y/%m/%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]


def norm(c):
    return re.sub(r"[^a-z0-9]+", "_", (c or "").strip().lower()).strip("_")


def detect(fields, override=None):
    """header -> {canonical: original column}. First alias present wins, in alias priority order."""
    by = {norm(f): f for f in fields}
    m = {}
    for k, v in (override or {}).items():
        if v not in fields:
            raise ValueError("--map %s=%s: no such column. Columns: %s" % (k, v, ", ".join(fields)))
        m[k] = v
    for k, al in ALIAS.items():
        if k in m:
            continue
        for a in al:
            if a in by:
                m[k] = by[a]
                break
    # a location column is only a city if its values look like places (checked later); 'location' as "(lat, lon)" handled there
    return m


def _ts(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return bt._ts(v)
    except (ValueError, OverflowError):
        pass
    for f in DATE_FMT:
        try:
            return dt.datetime.strptime(v, f).replace(tzinfo=IST).timestamp()
        except ValueError:
            continue
    return None


def _chan(v, default):
    s = (v or "").strip().lower()
    if not s:
        return default
    if s in bt.CHANS:
        return s
    for ch, words in CHAN_WORDS:
        if any(w in s for w in words):
            return ch
    return default


def _city(v):
    s = (v or "").strip().lower()
    return CITYMAP.get(s) or STATE_CITY.get(s)


def _latlon(v):
    m = re.findall(r"-?\d+\.\d+", v or "")
    return (float(m[0]), float(m[1])) if len(m) >= 2 else None


def _label(v):
    s = (v or "").strip().lower()
    if s in ("1", "1.0", "true", "t", "yes", "y", "fraud", "fraudulent", "scam"):
        return "1"
    if s in ("0", "0.0", "false", "f", "no", "n", "legit", "legitimate", "genuine", "normal", ""):
        return "0"
    if s == "2":
        return "2"
    return None


def convert(text, override=None, chan=None, city=None, max_rows=bt.MAX_ROWS, sniff=2000):
    """Raw CSV text -> (canonical csv text, report). Raises ValueError with a plain explanation when it can't."""
    rd = csv.DictReader(io.StringIO(text))
    fields = [f for f in (rd.fieldnames or []) if f]
    if not fields:
        raise ValueError("empty file or no header row")
    m = detect(fields, override)
    rep = dict(mapped=dict(m), columns=len(fields), notes=[], dropped=0)
    missing = [k for k in ("ts", "uid", "amt") if k not in m]
    if missing:
        raise ValueError("could not find: %s. Pass --map, e.g. --map %s=<your column>. Columns: %s" % (
            ", ".join(missing), missing[0], ", ".join(fields[:40])))
    raw = []
    for i, r in enumerate(rd):
        if i >= max_rows:
            rep["notes"].append("stopped at %d rows (limit)" % max_rows)
            break
        raw.append(r)
    # sniff how location and channel columns behave before committing
    cc = m.get("city")
    if cc and "lat" not in m:
        sample = [r.get(cc, "") for r in raw[:sniff]]
        hit = sum(1 for v in sample if _city(v))
        ll = sum(1 for v in sample if _latlon(v))
        if ll > 0.8 * max(len(sample), 1):
            m["latlon_col"] = m.pop("city")
            cc = None
        elif hit < 0.5 * max(len(sample), 1):
            rep["notes"].append("column %r does not look like Indian cities/states (%d%% matched), so it was not used for location" % (cc, 100 * hit // max(len(sample), 1)))
            m.pop("city")
            cc = None
    dflt_city = _city(city) if city else None
    if "lat" in m and "lon" in m:
        geo = "lat/lon columns"
    elif cc or "latlon_col" in m:
        geo = "location column"
    else:
        geo = "none"
        dflt_city = dflt_city or "Mumbai"
        rep["notes"].append("no usable location, so every row is placed in %s. Impossible-travel and home-distance signals are switched off in effect; "
                            "expect the engine to rely on amount, payee, device and velocity instead." % dflt_city)
    rep["geo"] = geo
    dchan = chan or "upi"
    if "chan" not in m:
        rep["notes"].append("no channel column; every row treated as %s" % dchan)
    elif not any(_chan(r.get(m["chan"]), None) for r in raw[:sniff]):
        rep["notes"].append("column %r has no recognisable payment-channel words; every row treated as %s" % (m["chan"], dchan))
        m.pop("chan")
    if "mid" not in m:
        rep["notes"].append("no payee/merchant column; payee-graph features (fan-in, mule payees, new-payee) carry no signal")
    out = io.StringIO()
    w = csv.writer(out)
    cols = ["ts", "uid", "amt", "chan", "mid", "city", "lat", "lon", "cat", "dev", "ip", "pers", "coll", "rat", "sim", "label"]
    w.writerow(cols)
    n_ts_bad = n_amt_bad = 0
    for r in raw:
        ts = _ts(r.get(m["ts"]))
        try:
            a = float((r.get(m["amt"]) or "").replace(",", ""))
        except ValueError:
            a = None
        if ts is None:
            n_ts_bad += 1
            continue
        if a is None or a <= 0:
            n_amt_bad += 1
            continue
        ct, la, lo = "", "", ""
        if "lat" in m and "lon" in m:
            la, lo = r.get(m["lat"], ""), r.get(m["lon"], "")
        elif "latlon_col" in m:
            p = _latlon(r.get(m["latlon_col"]))
            la, lo = (p if p else ("", ""))
        elif cc:
            ct = _city(r.get(cc)) or dflt_city or ""
        else:
            ct = dflt_city
        if not (ct or (la != "" and lo != "")):
            ct = dflt_city or "Mumbai"
        lab = _label(r.get(m["label"], "")) if "label" in m else ""
        if lab is None:
            lab = ""
        rt = r.get(m["rat"], "").strip().lower() if "rat" in m else ""
        w.writerow([ts, r[m["uid"]], a, _chan(r.get(m.get("chan", "")), dchan), r.get(m.get("mid", ""), "") or r[m["uid"]] + "~self",
                    ct, la, lo, "", r.get(m.get("dev", ""), ""), r.get(m.get("ip", ""), ""), "", r.get(m.get("coll", ""), ""),
                    "0" if rt in ("", "[]", "0", "false", "none", "no", "nan") else "1", r.get(m.get("sim", ""), ""), lab])
    rep["dropped"] = n_ts_bad + n_amt_bad
    if n_ts_bad:
        rep["notes"].append("%d row(s) dropped: unreadable timestamp in %r" % (n_ts_bad, m["ts"]))
    if n_amt_bad:
        rep["notes"].append("%d row(s) dropped: amount missing, zero or negative" % n_amt_bad)
    if n_ts_bad > 0.5 * max(len(raw), 1):
        raise ValueError("timestamp column %r is unreadable in %d of %d rows (example: %r). Use the tabular path, or pass --map ts=<column>." % (
            m["ts"], n_ts_bad, len(raw), raw[0].get(m["ts"]) if raw else ""))
    if "label" not in m:
        rep["notes"].append("no label column found; fine for a backtest, but training needs one (--map label=<column>)")
    rep["rows"] = len(raw) - rep["dropped"]
    rep["mapped"] = m
    return out.getvalue(), rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a transactions CSV to the engine's canonical columns.")
    ap.add_argument("csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--map", default="", help="canonical=column pairs, comma separated, e.g. uid=sender_id,label=is_fraud")
    ap.add_argument("--chan", help="channel to assume when the file has none (default upi)")
    ap.add_argument("--city", help="city to assume when the file has no location")
    a = ap.parse_args(argv)
    ov = dict(p.split("=", 1) for p in a.map.split(",") if "=" in p)
    text, rep = convert(open(a.csv, encoding="utf-8-sig", errors="replace").read(), ov, a.chan, a.city)
    open(a.out, "w", newline="").write(text)
    print(json.dumps(rep["mapped"]))
    for n in rep["notes"]:
        print("note:", n, file=sys.stderr)
    print("%d rows -> %s" % (rep["rows"], a.out))


if __name__ == "__main__":
    main()
