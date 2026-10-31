"""Synthetic payments world.

Legit behaviour: users with home city, devices, favourite merchants, hour-of-day
rhythm and lognormal spend. Fraud: six typologies. Hard negatives (trips, new phones,
big purchases, shared family devices, quick follow-up charges) make false positives
a real tradeoff instead of a free lunch.
"""
import math
import calendar
import random

from .geo import CITY, hav

T0 = calendar.timegm((2026, 9, 1, 0, 0, 0))
DAY = 86400

# category: (static risk prior, amount multiplier)
CATS = {
    "grocery": (0.02, 1.5), "restaurant": (0.03, 0.9), "fuel": (0.04, 1.2),
    "transport": (0.03, 0.5), "utilities": (0.01, 2.5), "health": (0.03, 1.4),
    "travel": (0.10, 5.0), "electronics": (0.20, 4.0), "fashion": (0.07, 2.0),
    "gift_cards": (0.45, 3.0), "crypto": (0.50, 4.0), "gambling": (0.35, 1.5),
    "digital": (0.15, 0.6), "atm_cash": (0.12, 3.0), "luxury": (0.30, 8.0),
}
SAFE = ["grocery", "restaurant", "fuel", "transport", "utilities", "health", "fashion", "digital"]
RISKY = ["gift_cards", "crypto", "electronics", "luxury", "gambling"]
BIG = ["travel", "electronics", "luxury"]
ONL = {"digital", "gift_cards", "crypto", "gambling", "electronics", "travel"}
TYPS = ["card_test", "ato", "ato_soft", "hijack", "travel", "high_value", "mule"]
HOME_W = [5, 5, 5, 4, 4, 3, 2, 2, 2, 2, 2, 2, 1, 2]

# fraud episodes per simulated day at boost=1
RATE = {"card_test": 2.5, "ato": 7.0, "ato_soft": 5.0, "hijack": 3.0, "travel": 4.0, "high_value": 6.0, "mule": 1.0}


def pois(r, lam):
    if lam <= 0:
        return 0
    lim, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= r.random()
        if p <= lim:
            return k
        k += 1


def ip24(ip):
    return ".".join(ip.split(".")[:3]) if ip else None


class World:
    def __init__(s, seed=7, nusr=1200, nmer=500):
        r = random.Random(seed)
        s.seed = seed
        s.mers, s.byc, s.onl, s.atm = [], {i: [] for i in range(len(CITY))}, [], {}
        cats = [c for c in CATS if c != "atm_cash"]
        for i in range(len(CITY)):  # guarantee basics in each city
            for c in ("grocery", "restaurant", "fuel"):
                s._add(c, i)
            s.atm[i] = s._add("atm_cash", i, pos=False)
        for _ in range(nmer):
            c = r.choice(cats)
            on = r.random() < (0.85 if c in ONL else 0.15)
            s._add(c, None if on else r.randrange(len(CITY)))
        s.users = []
        for i in range(nusr):
            hc = r.choices(range(len(CITY)), weights=HOME_W)[0]
            uid = "u%04d" % i
            night = r.random() < 0.08
            peak = 23.5 if night else r.gauss(18, 3) % 24
            w = [0.3 / 24 + 0.7 * math.exp(-min((h - peak) % 24, (peak - h) % 24) ** 2 / (2 * 3.5 ** 2)) for h in range(24)]
            tot = sum(w)
            u = dict(
                uid=uid, idx=i, hc=hc, mu=math.log(35) + r.gauss(0, 0.55), sg=0.55 + r.random() * 0.35,
                rate=max(0.4, r.lognormvariate(math.log(2.6), 0.5)), w=[x / tot for x in w],
                tz=int(round(CITY[hc][2] / 15)),
                devs=["d%s%s" % (uid, k) for k in "ab"[: r.choice((1, 2))]],
                ips=["%d.%d.%d" % (10 + hc, i // 256, i % 256), "%d.%d.%d" % (30 + hc, i // 256, i % 256),
                     "%d.%d.%d" % (100 + hc, r.randrange(256), r.randrange(256))],
                trip=None, swap=None, swf=False,
            )
            z = r.random()
            if z < 0.06:
                tc = r.choice([c for c in range(len(CITY)) if c != hc])
                st = T0 + r.uniform(3, 60) * DAY
                u["trip"] = (st, st + r.uniform(3, 7) * DAY, tc, DAY)
            elif z < 0.15:  # day-hop: fly out, spend a day or two, fly back
                near = [c for c in range(len(CITY)) if 500 < hav(CITY[hc][1], CITY[hc][2], CITY[c][1], CITY[c][2]) < 2500]
                if near:
                    st = T0 + r.uniform(3, 60) * DAY
                    u["trip"] = (st, st + r.uniform(0.8, 2) * DAY, r.choice(near), 3 * 3600)
            if r.random() < 0.06:
                u["swap"] = (T0 + r.uniform(8, 60) * DAY, "d%sn" % uid)
            ps = [m for m in s.byc[hc] if s.mers[m]["cat"] in SAFE]
            on = [m for m in s.onl if s.mers[m]["cat"] in SAFE or s.mers[m]["cat"] == "digital"]
            u["fp"] = [r.choice(ps) for _ in range(4)] if ps else []
            u["fo"] = [r.choice(on) for _ in range(4)] if on else []
            s.users.append(u)
        for _ in range(int(nusr * 0.03)):  # families sharing a device
            a, b = r.sample(s.users, 2)
            b["devs"] = list(a["devs"])
        s.ring = []
        pool = r.sample(range(nusr), 24)
        for k in range(3):
            ci = r.randrange(len(CITY))
            s.ring.append(dict(
                uids=pool[k * 8:(k + 1) * 8], devs=["dr%da" % k, "dr%db" % k], ci=ci,
                ips=["185.%d.%d" % (k, r.randrange(256)), "185.%d.%d" % (k + 10, r.randrange(256))]))
        s.adev = ["dx%02d" % i for i in range(14)]
        s.aip = [("%d.%d.%d" % (r.choice((45, 91, 103, 178, 194)), r.randrange(256), r.randrange(256)), r.randrange(len(CITY)))
                 for _ in range(24)]
        s.onls = [m for m in s.onl if s.mers[m]["cat"] in ("digital", "gift_cards", "gambling")] or s.onl

    def _add(s, cat, ci, pos=True):
        m = dict(mid="m%04d" % len(s.mers), cat=cat, ci=ci)
        s.mers.append(m)
        k = len(s.mers) - 1
        if ci is None:
            s.onl.append(k)
        elif pos:
            s.byc[ci].append(k)
        return k

    # ---- event construction -------------------------------------------------
    def mk(s, r, ts, uid, m, amt, ch, dev, ip, ci, lab=0, typ="legit", jit=0.05):
        c = CITY[ci]
        return dict(ts=ts, uid=uid, mid=m["mid"], cat=m["cat"], amt=round(min(max(amt, 0.5), 9000), 2), chan=ch,
                    dev=dev, ip=ip, lat=round(c[1] + r.gauss(0, jit), 4), lon=round(c[2] + r.gauss(0, jit), 4),
                    cty=c[3], city=c[0], lab=lab, typ=typ)

    def one(s, r, u, ts):
        ci, tr = u["hc"], u["trip"]
        away = bool(tr and tr[0] + tr[3] <= ts < tr[1])
        if tr and (tr[0] <= ts < tr[0] + tr[3] or tr[1] <= ts < tr[1] + tr[3]):
            return []  # in transit
        if away:
            ci = tr[2]
        typ = "trip" if away else "legit"
        x = r.random()
        ch = "ecom" if x < 0.42 else ("pos" if x < 0.95 else "atm")
        big = ch != "atm" and r.random() < 0.025
        pool = s.onl if ch == "ecom" else s.byc[ci]
        if ch == "atm":
            m = s.mers[s.atm[ci]]
        else:
            cand = [k for k in pool if s.mers[k]["cat"] in BIG] if big else []
            fav = u["fo"] if ch == "ecom" else u["fp"]
            if cand:
                m = s.mers[r.choice(cand)]
            elif fav and not away and r.random() < 0.7:
                m = s.mers[r.choice(fav)]
            else:
                m = s.mers[r.choice(pool)]
            if cand:
                typ = "bigbuy" if not away else typ
        if ch == "atm":
            amt = r.choice((20, 40, 60, 100, 200, 300))
        else:
            amt = math.exp(r.gauss(u["mu"] + math.log(CATS[m["cat"]][1]), u["sg"]))
            if typ == "bigbuy":
                amt *= r.uniform(2, 4)
        dev = ip = None
        ici = ci  # where the IP geolocates
        if ch == "ecom":
            dv = u["devs"]
            if u["swap"] and ts >= u["swap"][0]:
                dv = [u["swap"][1]]
                if not u["swf"]:
                    u["swf"] = True
                    if not away:
                        typ = "newdev"
            dev = r.choice(dv)
            if away:
                ip = "%d.%d.%d.%d" % (70 + ci, u["idx"] // 256, u["idx"] % 256, r.randrange(1, 255))
            else:
                ip = r.choices(u["ips"], weights=(6, 2, 2))[0] + ".%d" % r.randrange(1, 255)
            z = r.random()
            if z < 0.02:      # cleared cookies / new browser: unseen device id, same person
                dev, typ = "dc%07d" % r.randrange(10 ** 7), "newdev"
            elif z < 0.045:   # cafe / hotel wifi: unseen network
                ip = "%d.%d.%d.%d" % (200 + ci, r.randrange(256), r.randrange(256), r.randrange(1, 255))
            elif z < 0.052:   # VPN: IP geolocates elsewhere
                ici = r.randrange(len(CITY))
                ip = "%d.%d.%d.%d" % (150 + ici, r.randrange(256), r.randrange(256), r.randrange(1, 255))
                typ = "vpn" if ici != ci else typ
            elif z < 0.0545:  # library / office machine shared by many people
                dev, typ = "dp%d" % r.randrange(6), "public"
                ip = "172.16.%d.%d" % (r.randrange(6), r.randrange(1, 255))
            elif z < 0.0645 and m["cat"] == "digital":  # app-store style micro charges
                amt, typ = r.choice((0.99, 1.99, 2.99, 4.99)), "micro"
        e = s.mk(r, ts, u["uid"], m, amt, ch, dev, ip, ici, 0, typ)
        out = [e]
        if r.random() < 0.03 and ch != "atm":
            f = dict(e)
            f.update(ts=ts + r.uniform(60, 240), amt=round(max(0.5, e["amt"] * r.uniform(0.2, 1.0)), 2), typ="burst")
            out.append(f)
        return out

    def legit(s, r, t0, t1):
        out, h0 = [], int(t0 // 3600)
        for u in s.users:
            for h in range(h0, int(math.ceil(t1 / 3600))):
                lam = u["rate"] * u["w"][(h + u["tz"]) % 24]
                for _ in range(pois(r, lam)):
                    ts = h * 3600 + r.random() * 3600
                    if t0 <= ts < t1:
                        out += s.one(r, u, ts)
        return out

    # ---- fraud typologies ---------------------------------------------------
    def mean(s, u):
        return math.exp(u["mu"] + u["sg"] ** 2 / 2)

    def atk(s, r):
        """Attacker infrastructure: a small reused pool, but mostly fresh devices and networks."""
        if r.random() < 0.3:
            ad = r.choice(s.adev)
            ip, ci = r.choice(s.aip)
        else:
            ad, ci = "dn%06d" % r.randrange(10 ** 6), r.randrange(len(CITY))
            ip = "%d.%d.%d" % (r.choice((45, 91, 103, 178, 194)), r.randrange(256), r.randrange(256))
        return ad, ip + ".%d" % r.randrange(1, 255), ci

    def fraud(s, r, kind, ts, uid=None):
        ring = r.choice(s.ring) if kind == "mule" else None
        u = s.users[r.randrange(len(s.users))] if uid is None else next(z for z in s.users if z["uid"] == uid)
        mean, out, t = s.mean(u), [], ts
        ad, aip, aci = s.atk(r)
        if kind == "card_test":
            slow = r.random() < 0.4  # low-and-slow evades naive micro-charge rules
            for _ in range(r.randint(3, 6) if slow else r.randint(5, 12)):
                t += r.uniform(30, 180) if slow else r.uniform(4, 30)
                m = s.mers[r.choice(s.onls)]
                amt = r.uniform(5, 14) if slow else r.choice((0.5, 1, 1, 1.99, 2, 2.5, 3, 4.99))
                out.append(s.mk(r, t, u["uid"], m, amt, "ecom", ad, aip, aci, 1, kind))
            if r.random() < 0.6:
                t += r.uniform(20, 120)
                m = s.mers[r.choice([k for k in s.onl if s.mers[k]["cat"] in RISKY] or s.onl)]
                out.append(s.mk(r, t, u["uid"], m, mean * r.uniform(2, 10), "ecom", ad, aip, aci, 1, kind))
        elif kind in ("ato", "ato_soft"):
            soft = kind == "ato_soft"
            for _ in range(r.randint(1, 2) if soft else r.randint(1, 4)):
                t += r.uniform(60, 600)
                mix = soft or r.random() < 0.4
                if mix:
                    pool = [k for k in s.onl if s.mers[k]["cat"] in SAFE or s.mers[k]["cat"] in ("electronics", "travel")] or s.onl
                    amt = mean * r.uniform(0.9, 3.5)
                else:
                    pool = [k for k in s.onl if s.mers[k]["cat"] in RISKY] or s.onl
                    amt = mean * r.uniform(3, 15)
                if soft or r.random() < 0.45:  # residential proxy near the victim
                    ip, ci = "%d.%d.%d.%d" % (210 + u["hc"], r.randrange(256), r.randrange(256), r.randrange(1, 255)), u["hc"]
                else:
                    ip, ci = aip, aci
                dev = ad if (not soft and r.random() < 0.15) else "dn%06d" % r.randrange(10 ** 6)
                if soft and r.random() < 0.3:  # spoofed / cloned device fingerprint
                    dev = r.choice(u["devs"])
                out.append(s.mk(r, t, u["uid"], s.mers[r.choice(pool)], amt, "ecom", dev, ip, ci, 1, kind))
        elif kind == "hijack":  # remote-access trojan: runs on the victim's own device and network
            for _ in range(r.randint(1, 3)):
                t += r.uniform(60, 900)
                pool = [k for k in s.onl if s.mers[k]["cat"] in RISKY + ["travel", "digital"]] or s.onl
                ip = r.choice(u["ips"]) + ".%d" % r.randrange(1, 255)
                out.append(s.mk(r, t, u["uid"], s.mers[r.choice(pool)], mean * r.uniform(2.5, 9), "ecom",
                                r.choice(u["devs"]), ip, u["hc"], 1, kind))
        elif kind == "travel":
            m0 = s.mers[r.choice(s.byc[u["hc"]])]
            out.append(s.mk(r, ts, u["uid"], m0, math.exp(r.gauss(u["mu"], u["sg"])), "pos", None, None, u["hc"], 0, "legit"))
            la, lo = CITY[u["hc"]][1], CITY[u["hc"]][2]
            near = r.random() < 0.4  # ambiguous: a plausible-but-fast hop vs. an obvious teleport
            far = [c for c in range(len(CITY)) if (600 < hav(la, lo, CITY[c][1], CITY[c][2]) < 2500 if near else hav(la, lo, CITY[c][1], CITY[c][2]) > 2500)]
            ci = r.choice(far or [c for c in range(len(CITY)) if c != u["hc"]])
            t = ts + (r.uniform(2400, 7200) if near else r.uniform(120, 2400))
            for _ in range(r.randint(1, 3)):
                m = s.mers[r.choice(s.byc[ci])]
                out.append(s.mk(r, t, u["uid"], m, mean * r.uniform(1.5, 6), "pos", None, None, ci, 1, kind))
                t += r.uniform(120, 900)
        elif kind == "high_value":
            ch = r.choice(("ecom", "pos"))
            amt = min(mean * r.uniform(5, 25), 6000)
            if ch == "ecom":
                m = s.mers[r.choice([k for k in s.onl if s.mers[k]["cat"] in RISKY] or s.onl)]
                out.append(s.mk(r, ts, u["uid"], m, amt, ch, ad, aip, aci, 1, kind))
            else:
                ci = r.choice([c for c in range(len(CITY)) if c != u["hc"]])
                m = s.mers[r.choice(s.byc[ci])]
                out.append(s.mk(r, ts, u["uid"], m, amt, ch, None, None, ci, 1, kind))
        elif kind == "mule":
            for k in r.sample(ring["uids"], r.randint(3, 5)):
                v, t = s.users[k], ts + r.uniform(0, 1800)
                for _ in range(r.randint(2, 5)):
                    t += r.uniform(30, 900)
                    m = s.mers[r.choice([j for j in s.onl if s.mers[j]["cat"] in ("gift_cards", "crypto", "digital", "gambling")] or s.onl)]
                    own = r.random() < 0.4  # off-ring session: fresh device + local network, ring link not visible
                    ip = ("%d.%d.%d" % (210 + v["hc"], r.randrange(256), r.randrange(256)) if own else r.choice(ring["ips"])) + ".%d" % r.randrange(1, 255)
                    amt = r.choice((100, 150, 200, 250, 300, 500, 750, 1000)) if r.random() < 0.6 else r.uniform(60, 900)
                    out.append(s.mk(r, t, v["uid"], m, amt, "ecom", "dn%06d" % r.randrange(10 ** 6) if own else r.choice(ring["devs"]),
                                    ip, v["hc"] if own else ring["ci"], 1, kind))
        return out

    def window(s, r, t0, t1, boost=1.0):
        out = s.legit(r, t0, t1)
        for kind, rate in RATE.items():
            for _ in range(pois(r, rate * boost * (t1 - t0) / DAY)):
                out += s.fraud(r, kind, r.uniform(t0, t1))
        out.sort(key=lambda e: e["ts"])
        return out
