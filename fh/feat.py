"""Streaming feature store.

Rule #1: features for a transaction are computed from state *before* that
transaction is committed (no leakage). Rule #2: labels only enter state through
delayed fraud reports (`report`), the way complaints and chargebacks really arrive.
India-specific state: a payee graph (mule accounts accumulate unrelated senders),
first-seen payees across the whole platform, SIM-change recency and screen-share signals.
"""
import math
from collections import deque, defaultdict

from .geo import hav
from .gen import CATS, ip24, LIM, IST

NAMES = [
    "lamt", "zamt", "rmax", "c1m", "c10m", "c1h", "c24h", "s1h",
    "ndev", "nip", "ncty", "nmer", "ncat", "hrar", "dkm", "sped", "hkm",
    "devu", "ipu", "dbad", "ibad", "mbad", "ecom", "atm", "upi", "imps", "crsk", "cold",
    "tiny", "rnd", "lim", "pers", "fanin", "pfirst", "simc", "rat", "coll",
    "xdz", "xdc", "xhz", "xrz", "xnz", "xsd", "xnf",
]
WEEK = 7 * 86400
CARD_PRESENT = ("pos", "atm")   # only these give a trustworthy physical location for travel-speed


class Prof:
    __slots__ = ("n", "mu", "m2", "mx", "hist", "devs", "ips", "ctys", "mers", "cats", "q",
                 "lt", "la", "lo", "sa", "so", "sn")

    def __init__(s):
        s.n, s.mu, s.m2, s.mx = 0, 0.0, 0.0, 0.0
        s.hist = [0] * 24
        s.devs, s.ips, s.ctys, s.mers, s.cats = set(), set(), set(), set(), set()
        s.q = deque()
        s.lt = None
        s.la = s.lo = s.sa = s.so = 0.0
        s.sn = 0


_EMPTY = Prof()


class Store:
    def __init__(s):
        s.u = {}
        s.du = defaultdict(dict)   # device -> {uid: last_ts}
        s.iu = defaultdict(dict)   # ip /24 -> {uid: last_ts}
        s.pu = defaultdict(dict)   # personal payee -> {uid: last_ts}   (mule accounts collect many senders)
        s.pf = set()               # every payee ever seen on the platform
        s.bad = defaultdict(deque)  # 'd:dev' / 'i:ip' / 'm:payee' -> report times (7-day window, avoids drift)
        s.blk = set()              # manual blocklist keys: 'u:' 'd:' 'i:'

    # ---------------------------------------------------------------- features
    def feats(s, x):
        P = s.u.get(x["uid"], _EMPTY)
        ts, amt, dev, ch, mid = x["ts"], x["amt"], x["dev"], x["chan"], x["mid"]
        ip = ip24(x["ip"])
        pers = 1 if x.get("pers") else 0
        c1 = c10 = c1h = cd = sm5 = 0
        s1h = 0.0
        for t, a, se in P.q:
            dt = ts - t
            if dt < 0 or dt > 86400:
                continue
            cd += 1
            if dt <= 3600:
                c1h += 1
                s1h += a
            if dt <= 600:
                c10 += 1
            if dt <= 60:
                c1 += 1
            if dt <= 300 and se:
                sm5 += 1
        la = math.log(amt)
        if P.n >= 4:
            sd = max(math.sqrt(P.m2 / (P.n - 1)), 0.25)
            z = max(-4.0, min(6.0, (la - P.mu) / sd))
        else:
            z = 0.0
        rat_ = amt / math.exp(P.mu) if P.n else 1.0
        rmax = min(math.log(1 + amt / (P.mx + 1)), 5.0) if P.n else 0.0
        ndev = 1 if (dev and P.n and dev not in P.devs) else 0
        nip = 1 if (ip and P.n and ip not in P.ips) else 0
        ncty = 1 if (P.n and x["cty"] not in P.ctys) else 0
        nmer = 1 if mid not in P.mers else 0
        ncat = 1 if (P.n and x["cat"] not in P.cats) else 0
        lh = int(((ts + IST) / 3600) % 24)
        hrar = min(7.0, max(0.0, -math.log((P.hist[lh] + 1) / (P.n + 24))))
        km = kmh = hk = 0.0
        if P.lt is not None:
            km = hav(P.la, P.lo, x["lat"], x["lon"])
            kmh = km / (max(ts - P.lt, 60.0) / 3600)
        if P.sn:
            hk = hav(P.sa / P.sn, P.so / P.sn, x["lat"], x["lon"])
        devu = sum(1 for k, t in s.du.get(dev, {}).items() if k != x["uid"] and ts - t <= WEEK) if dev else 0
        ipu = sum(1 for k, t in s.iu.get(ip, {}).items() if k != x["uid"] and ts - t <= WEEK) if ip else 0
        fan = sum(1 for k, t in s.pu.get(mid, {}).items() if k != x["uid"] and 0 <= ts - t <= WEEK) if pers else 0
        pfirst = 1 if (pers and mid not in s.pf) else 0
        dbad = s.nbad("d:" + dev, ts) if dev else 0
        ibad = s.nbad("i:" + ip, ts) if ip else 0
        mbad = s.nbad("m:" + mid, ts)
        crsk = CATS[x["cat"]][0]
        ecom = 1.0 if ch == "ecom" else 0.0
        tiny = ecom * (1.0 if amt < 10 else 0.0) * min(c10, 10) / 10
        rnd = 1.0 if (amt >= 1000 and amt % 500 == 0) else 0.0
        lim = 1.0 if any(0.95 * L <= amt < L for L in LIM) else 0.0
        sim = float(x.get("sim", 1e4) or 1e4)
        simc = 1 if sim < 72 else 0
        rat = 1 if x.get("rat") else 0
        coll = 1 if x.get("coll") else 0
        zp = max(z, 0.0)
        fln = math.log1p(fan)
        f = dict(
            lamt=la, zamt=z, rmax=rmax, c1m=math.log1p(c1), c10m=math.log1p(c10), c1h=math.log1p(c1h), c24h=math.log1p(cd),
            s1h=math.log1p(s1h), ndev=ndev, nip=nip, ncty=ncty, nmer=nmer, ncat=ncat, hrar=hrar, dkm=math.log1p(km),
            sped=math.log1p(kmh), hkm=math.log1p(hk), devu=math.log1p(devu), ipu=math.log1p(ipu), dbad=math.log1p(dbad),
            ibad=math.log1p(ibad), mbad=math.log1p(mbad), ecom=ecom, atm=1.0 if ch == "atm" else 0.0,
            upi=1.0 if ch == "upi" else 0.0, imps=1.0 if ch == "imps" else 0.0, crsk=crsk, cold=1.0 if P.n < 4 else 0.0,
            tiny=tiny, rnd=rnd, lim=lim, pers=float(pers), fanin=fln, pfirst=float(pfirst), simc=float(simc),
            rat=float(rat), coll=float(coll), xdz=ndev * zp, xdc=ndev * crsk, xhz=(1.0 if hk > 500 else 0.0) * zp,
            xrz=rat * zp, xnz=nmer * pers * zp, xsd=float(simc * ndev), xnf=nmer * pers * fln,
        )
        raw = dict(amt=amt, z=z, rat=rat_, mx=P.mx, c1=c1, c10=c10, c1h=c1h, cd=cd, s1h=s1h, sm5=sm5, ndev=ndev,
                   nip=nip, ncty=ncty, nmer=nmer, ncat=ncat, lh=lh, km=km, kmh=kmh, hk=hk, devu=devu, ipu=ipu,
                   dbad=dbad, ibad=ibad, mbad=mbad, cat=x["cat"], chan=ch, cty=x["cty"], n=P.n, pers=pers, fan=fan,
                   pfirst=pfirst, sim=sim, ratf=rat, coll=coll, lim=lim, mid=mid,
                   gap=(ts - P.lt) if P.lt is not None else None, crsk=crsk)
        return [f[n] for n in NAMES], raw

    # ------------------------------------------------------------------ state
    def commit(s, x, upd=True):
        """Record the transaction. `upd=False` keeps it out of the customer's own behavioural
        profile (declined / failed step-up attempts are not customer behaviour) but the
        device / network / payee graph always learns who touched what."""
        ts, uid = x["ts"], x["uid"]
        if x["dev"]:
            s.du[x["dev"]][uid] = ts
        ip = ip24(x["ip"])
        if ip:
            s.iu[ip][uid] = ts
        if x.get("pers") and uid not in s.pu[x["mid"]]:
            s.pu[x["mid"]][uid] = ts   # first-time senders only: strangers paying a mule, not friends paying friends
        s.pf.add(x["mid"])
        P = s.u.get(uid)
        if P is None:
            P = s.u[uid] = Prof()
        # Velocity counts every ATTEMPT, whatever its outcome: a bot's declined micro-charges are exactly the signal.
        P.q.append((ts, x["amt"], 1 if (x["chan"] == "ecom" and x["amt"] < 10) else 0))
        while P.q and ts - P.q[0][0] > 86400:
            P.q.popleft()
        if not upd:   # the behavioural profile (typical spend, trusted devices, home area) only learns from trusted payments
            return
        la = math.log(x["amt"])
        P.n += 1
        d = la - P.mu
        P.mu += d / P.n
        P.m2 += d * (la - P.mu)
        P.mx = max(P.mx, x["amt"])
        P.hist[int(((ts + IST) / 3600) % 24)] += 1
        if x["dev"]:
            P.devs.add(x["dev"])
        if ip:
            P.ips.add(ip)
        P.ctys.add(x["cty"])
        P.mers.add(x["mid"])
        P.cats.add(x["cat"])
        if x["chan"] in CARD_PRESENT:  # travel-speed anchor = last *card-present* location; IP geo is too noisy (VPNs)
            P.lt, P.la, P.lo = ts, x["lat"], x["lon"]
        P.sa += x["lat"]
        P.so += x["lon"]
        P.sn += 1

    def nbad(s, k, ts):
        q = s.bad.get(k)
        return sum(1 for t in q if 0 <= ts - t <= WEEK) if q else 0

    def report(s, x, now):
        """A confirmed fraud report (customer complaint, 1930 / cybercrime-portal case, analyst decision)
        arrives at `now`, hours after the event. Complaints about *authorised* scams (the customer was talked
        into paying) say nothing about the customer's own device or network, so they only taint the payee."""
        own = not x.get("app")
        for k in (("d:" + x["dev"]) if (x["dev"] and own) else None, ("i:" + ip24(x["ip"])) if (x["ip"] and own) else None, "m:" + x["mid"]):
            if k:
                q = s.bad[k]
                q.append(now)
                while now - q[0] > WEEK:
                    q.popleft()

    def prune(s, now):
        for g in (s.du, s.iu, s.pu):
            for k in [k for k, v in g.items() if len(v) > 40]:
                g[k] = {u: t for u, t in g[k].items() if now - t <= WEEK}
