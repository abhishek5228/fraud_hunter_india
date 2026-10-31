"""Synthetic Indian payments world.

Rails: UPI (P2M and P2P), card online, card in-person, ATM, and IMPS/net-banking transfers.
Legit behaviour: customers with a home city, devices, saved payees, monthly rent, an evening-heavy
rhythm and lognormal rupee spend. Fraud: eight typologies seen in Indian digital payments. Legit
lookalikes (travellers, new phones plus SIM changes, VPN users, shared kiosk devices, screen-sharing
for IT help, first-time payees, big festival purchases) make false positives a real tradeoff.
"""
import math
import time
import calendar
import random

from .geo import CITY, NIN, HOME_W, hav

T0 = calendar.timegm((2026, 9, 1, 0, 0, 0)) - 19800   # midnight IST, 1 Sep 2026
DAY = 86400
IST = 19800

# category: (static risk prior, amount multiplier on the customer's typical ticket)
CATS = {
    "grocery": (0.02, 1.0), "food": (0.02, 0.8), "fuel": (0.03, 2.5), "transit": (0.02, 0.3),
    "bills": (0.01, 2.0), "health": (0.03, 1.5), "education": (0.03, 3.0), "travel": (0.10, 6.0),
    "electronics": (0.20, 10.0), "fashion": (0.07, 3.0), "jewellery": (0.25, 15.0),
    "gift_cards": (0.45, 2.0), "crypto": (0.45, 4.0), "gaming": (0.40, 1.2), "digital": (0.12, 0.4),
    "p2p": (0.10, 1.0), "bank_transfer": (0.15, 3.0), "atm_cash": (0.12, 4.0),
}
PERS_CATS = ("p2p", "bank_transfer")      # payee is a person/account rather than a verified merchant
SAFE = ["grocery", "food", "fuel", "transit", "bills", "health", "fashion", "digital"]
RISKY = ["gift_cards", "crypto", "electronics", "jewellery", "gaming"]
BIG = ["travel", "electronics", "jewellery"]
FEST = ["fashion", "electronics", "jewellery"]
ONL = {"digital", "gift_cards", "crypto", "gaming", "electronics", "travel"}
HANDLES = ["ybl", "okaxis", "oksbi", "okhdfcbank", "paytm", "ibl", "axl", "upi"]
TYPS = ["card_test", "travel", "high_value", "ato", "sim_swap", "vishing", "upi_scam", "mule"]
LIM = (50000, 100000, 200000)              # payment-limit levels that structuring hugs
CAP = {"upi": 100000, "imps": 500000}       # per-transaction ceilings; cards/ATM capped at 3 lakh

# fraud episodes per simulated day at boost=1
RATE = {"card_test": 1.2, "travel": 2.0, "high_value": 2.5, "ato": 3.0, "sim_swap": 2.5, "vishing": 5.0, "upi_scam": 6.0, "mule": 1.0}


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
        s.seed, s.fest = seed, 1.0
        s.mers, s.byc, s.onl, s.atm = [], {i: [] for i in range(len(CITY))}, [], {}
        cats = [c for c in CATS if c not in ("atm_cash", "p2p", "bank_transfer")]
        for i in range(NIN):  # guarantee basics in each home city
            for c in ("grocery", "food", "fuel", "transit"):
                s._add(r, c, i)
            s.atm[i] = s._add(r, "atm_cash", i, pos=False)
        for i in range(NIN, len(CITY)):  # foreign hubs: somewhere to swipe a cloned card
            s._add(r, "fashion", i)
            s._add(r, "food", i)
        for _ in range(nmer):
            c = r.choice(cats)
            on = r.random() < (0.85 if c in ONL else 0.1)
            s._add(r, c, None if on else r.randrange(NIN))
        s.users = []
        for i in range(nusr):
            hc = r.choices(range(NIN), weights=HOME_W)[0]
            uid = "u%04d" % i
            night = r.random() < 0.08
            peak = 23.5 if night else r.gauss(19, 3) % 24
            w = [0.3 / 24 + 0.7 * math.exp(-min((h - peak) % 24, (peak - h) % 24) ** 2 / (2 * 3.5 ** 2)) for h in range(24)]
            tot = sum(w)
            u = dict(
                uid=uid, idx=i, hc=hc, mu=math.log(350) + r.gauss(0, 0.5), sg=0.55 + r.random() * 0.35,
                rate=max(0.5, r.lognormvariate(math.log(3.2), 0.5)), w=[x / tot for x in w],
                devs=["d%s%s" % (uid, k) for k in "ab"[: r.choice((1, 2))]],
                ips=["%d.%d.%d" % (10 + hc, i // 256, i % 256), "%d.%d.%d" % (30 + hc, i // 256, i % 256),
                     "%d.%d.%d" % (100 + hc, r.randrange(256), r.randrange(256))],
                vpa="%s@%s" % (uid, r.choice(HANDLES)), ct=[], ben=["ac%s-%d" % (uid, k) for k in range(3)],
                trip=None, swap=None, simc=None, swf=False, rent=None,
            )
            z = r.random()
            if z < 0.06:
                tc = r.choice([c for c in range(NIN) if c != hc])
                st = T0 + r.uniform(3, 60) * DAY
                u["trip"] = (st, st + r.uniform(3, 7) * DAY, tc, DAY)
            elif z < 0.15:  # day-hop: fly out, spend a day or two, fly back
                near = [c for c in range(NIN) if 500 < hav(CITY[hc][1], CITY[hc][2], CITY[c][1], CITY[c][2]) < 2500]
                if near:
                    st = T0 + r.uniform(3, 60) * DAY
                    u["trip"] = (st, st + r.uniform(0.8, 2) * DAY, r.choice(near), 3 * 3600)
            if r.random() < 0.08:  # new phone; half the time with a new SIM / number
                at = T0 + r.uniform(8, 60) * DAY
                u["swap"] = (at, "d%sn" % uid)
                if r.random() < 0.5:
                    u["simc"] = at
            elif r.random() < 0.02:
                u["simc"] = T0 + r.uniform(8, 60) * DAY
            if r.random() < 0.12:  # monthly rent to a landlord
                u["rent"] = (round(r.uniform(6000, 40000) / 500) * 500, "ac%s-rent" % uid)
            ps = [m for m in s.byc[hc] if s.mers[m]["cat"] in SAFE]
            on = [m for m in s.onl if s.mers[m]["cat"] in SAFE]
            u["fp"] = [r.choice(ps) for _ in range(4)] if ps else []
            u["fo"] = [r.choice(on) for _ in range(4)] if on else []
            s.users.append(u)
        bycity = {}
        for u in s.users:
            bycity.setdefault(u["hc"], []).append(u)
        for u in s.users:
            pool = [v for v in bycity[u["hc"]] if v is not u] or s.users
            u["ct"] = [v["vpa"] for v in r.sample(pool, min(6, len(pool)))]
        for _ in range(int(nusr * 0.03)):  # families sharing a phone or tablet
            a, b = r.sample(s.users, 2)
            b["devs"] = list(a["devs"])
        s.ring = []
        pool = r.sample(range(nusr), 24)
        for k in range(3):
            s.ring.append(dict(uids=pool[k * 8:(k + 1) * 8], devs=["dr%da" % k, "dr%db" % k], ci=r.randrange(NIN),
                               ips=["185.%d.%d" % (k, r.randrange(256)), "185.%d.%d" % (k + 10, r.randrange(256))]))
        s.adev = ["dx%02d" % i for i in range(14)]
        s.aip = [("%d.%d.%d" % (r.choice((45, 91, 103, 178, 194)), r.randrange(256), r.randrange(256)), r.randrange(len(CITY)))
                 for _ in range(24)]
        s.mp = ["mu%02d@%s" % (i, r.choice(HANDLES)) for i in range(25)]   # rented mule accounts, reused across victims
        s.onls = [m for m in s.onl if s.mers[m]["cat"] in ("digital", "gift_cards", "gaming")] or s.onl

    def _add(s, r, cat, ci, pos=True):
        m = dict(mid="mq%04d@%s" % (len(s.mers), r.choice(HANDLES)), cat=cat, ci=ci)
        s.mers.append(m)
        k = len(s.mers) - 1
        if ci is None:
            s.onl.append(k)
        elif pos:
            s.byc[ci].append(k)
        return k

    # ---- event construction -------------------------------------------------
    def mk(s, r, ts, uid, m, amt, ch, dev, ip, ci, lab=0, typ="legit", jit=0.05, pers=False, coll=False, rat=False, sim=1e4):
        c = CITY[ci]
        return dict(ts=ts, uid=uid, mid=m["mid"], cat=m["cat"], amt=round(min(max(amt, 1.0), CAP.get(ch, 300000)), 2), chan=ch,
                    dev=dev, ip=ip, lat=round(c[1] + r.gauss(0, jit), 4), lon=round(c[2] + r.gauss(0, jit), 4),
                    cty=c[3], city=c[0], pers=pers, coll=coll, rat=rat, sim=round(sim, 1), lab=lab, typ=typ)

    def person(s, r, uid):
        return dict(mid=uid, cat="p2p")

    def one(s, r, u, ts):
        ci, tr = u["hc"], u["trip"]
        away = bool(tr and tr[0] + tr[3] <= ts < tr[1])
        if tr and (tr[0] <= ts < tr[0] + tr[3] or tr[1] <= ts < tr[1] + tr[3]):
            return []  # in transit
        if away:
            ci = tr[2]
        typ = "trip" if away else "legit"
        fest = s.fest
        x = r.random()
        ch = "upi" if x < 0.70 else "ecom" if x < 0.81 else "pos" if x < 0.93 else "atm" if x < 0.96 else "imps"
        p2p = ch == "upi" and r.random() < 0.30
        pers, coll, rat = ch == "imps" or p2p, False, False
        big = ch in ("ecom", "pos", "upi") and not p2p and r.random() < 0.02 * fest
        pool = s.onl if (ch == "ecom" or (ch == "upi" and r.random() < 0.25)) else s.byc[ci]
        if ch == "atm":
            m = s.mers[s.atm[ci]]
            amt = r.choice((500, 1000, 2000, 5000, 10000))
        elif p2p or ch == "imps":
            contacts = u["ct"] if p2p else u["ben"]
            if r.random() < (0.9 if p2p else 0.88):
                m = dict(mid=r.choice(contacts), cat="p2p" if p2p else "bank_transfer")
            else:  # a person they have never paid: plumber, new flatmate, a vendor
                m = dict(mid=(r.choice(s.users)["vpa"] if p2p else "ac%s-%d" % (u["uid"], r.randrange(10, 99))),
                         cat="p2p" if p2p else "bank_transfer")
                if not away:
                    typ = "newpayee"
            if p2p and r.random() < 0.55:
                amt = r.choice((50, 100, 100, 200, 500, 500, 1000, 2000, 5000)) * (1 + (fest - 1) * 0.3)
            else:
                amt = math.exp(r.gauss(u["mu"] + math.log(CATS[m["cat"]][1]) + (math.log(2.5) if ch == "imps" else 0), u["sg"]))
        else:
            cand = []
            if big:
                cand = [k for k in pool if s.mers[k]["cat"] in BIG]
            elif fest > 1 and r.random() < 0.12 * (fest - 1):
                cand = [k for k in pool if s.mers[k]["cat"] in FEST]
            fav = u["fo"] if (ch == "ecom" or pool is s.onl) else u["fp"]
            if cand:
                m = s.mers[r.choice(cand)]
                if big and not away:
                    typ = "bigbuy"
            elif fav and not away and r.random() < 0.7:
                m = s.mers[r.choice(fav)]
            else:
                m = s.mers[r.choice(pool)]
            amt = math.exp(r.gauss(u["mu"] + math.log(CATS[m["cat"]][1]), u["sg"])) * (1 + (fest - 1) * 0.25)
            if typ == "bigbuy":
                amt *= r.uniform(2, 4)
            if ch == "upi" and r.random() < 0.6:
                amt = max(1, round(amt))
            if ch == "upi" and m["cat"] in ("bills", "digital") and r.random() < 0.05:
                coll = True  # a biller's legitimate collect request
        dev = ip = None
        ici = ci  # where the IP geolocates
        sim = 1e4
        if u["simc"] and ts >= u["simc"]:
            sim = (ts - u["simc"]) / 3600
        if ch in ("upi", "ecom", "imps"):
            dv = u["devs"]
            if u["swap"] and ts >= u["swap"][0]:
                dv = [u["swap"][1]]
                if not u["swf"]:
                    u["swf"] = True
                    if not away:
                        typ = "newphone"
            dev = r.choice(dv)
            if away:
                ip = "%d.%d.%d.%d" % (70 + ci, u["idx"] // 256, u["idx"] % 256, r.randrange(1, 255))
            else:
                ip = r.choices(u["ips"], weights=(6, 2, 2))[0] + ".%d" % r.randrange(1, 255)
            z = r.random()
            if z < 0.02:      # cleared app data / reinstalled: unseen device id, same person
                dev, typ = "dc%07d" % r.randrange(10 ** 7), "newphone" if typ == "legit" else typ
            elif z < 0.075:   # cafe / hotel / mobile-data churn: unseen network
                ip = "%d.%d.%d.%d" % (200 + ci, r.randrange(256), r.randrange(256), r.randrange(1, 255))
            elif z < 0.082:   # VPN: IP geolocates elsewhere
                ici = r.randrange(len(CITY))
                ip = "%d.%d.%d.%d" % (150 + ici, r.randrange(256), r.randrange(256), r.randrange(1, 255))
                typ = "vpn" if (ici != ci and typ == "legit") else typ
            elif z < 0.0845 and ch != "imps":  # cyber cafe / CSC kiosk device shared by many people
                dev, typ = "dp%d" % r.randrange(6), "kiosk"
                ip = "172.16.%d.%d" % (r.randrange(6), r.randrange(1, 255))
            elif z < 0.0885 and ch in ("upi", "imps"):  # screen-sharing during a video call or IT support
                rat = True
                typ = "screenshare" if typ == "legit" else typ
            elif z < 0.0985 and ch == "upi" and m["cat"] == "digital":
                amt, typ = r.choice((1, 2, 5, 10, 20)), "micro"
        e = s.mk(r, ts, u["uid"], m, amt, ch, dev, ip, ici, 0, typ, pers=pers, coll=coll, rat=rat, sim=sim)
        out = [e]
        if r.random() < 0.03 and ch != "atm" and not pers:
            f = dict(e)
            f.update(ts=ts + r.uniform(60, 240), amt=round(max(1.0, e["amt"] * r.uniform(0.2, 1.0)), 2), typ="burst")
            out.append(f)
        return out

    def rent(s, r, u, ts):
        amt, pay = u["rent"]
        ch = "upi" if amt < CAP["upi"] else "imps"
        dev = r.choice(u["devs"])
        ip = u["ips"][0] + ".%d" % r.randrange(1, 255)
        return [s.mk(r, ts, u["uid"], dict(mid=pay, cat="bank_transfer" if ch == "imps" else "p2p"), amt, ch, dev, ip, u["hc"], 0,
                     "rent", pers=True)]

    def legit(s, r, t0, t1):
        out, h0 = [], int(t0 // 3600)
        fest = s.fest
        for u in s.users:
            rent = u["rent"]
            for h in range(h0, int(math.ceil(t1 / 3600))):
                lam = u["rate"] * fest * u["w"][((h * 3600 + IST) // 3600) % 24]
                for _ in range(pois(r, lam)):
                    ts = h * 3600 + r.random() * 3600
                    if t0 <= ts < t1:
                        out += s.one(r, u, ts)
                if rent and time.gmtime(h * 3600 + IST).tm_mday <= 5 and r.random() < 1 / 120:
                    ts = h * 3600 + r.random() * 3600
                    if t0 <= ts < t1:
                        out += s.rent(r, u, ts)
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

    def mpay(s, r):
        """A mule payee: usually one of a small rented pool (so it accumulates victims), sometimes fresh."""
        return r.choice(s.mp) if r.random() < 0.7 else "s%06d@%s" % (r.randrange(10 ** 6), r.choice(HANDLES))

    def fraud(s, r, kind, ts, uid=None):
        ring = r.choice(s.ring) if kind == "mule" else None
        u = s.users[r.randrange(len(s.users))] if uid is None else next(z for z in s.users if z["uid"] == uid)
        mean, out, t = s.mean(u), [], ts
        ad, aip, aci = s.atk(r)
        vip = lambda: r.choice(u["ips"]) + ".%d" % r.randrange(1, 255)
        if kind == "card_test":
            slow = r.random() < 0.4  # low-and-slow evades naive micro-charge rules
            for _ in range(r.randint(3, 6) if slow else r.randint(5, 12)):
                t += r.uniform(30, 180) if slow else r.uniform(4, 30)
                m = s.mers[r.choice(s.onls)]
                amt = r.uniform(15, 120) if slow else r.choice((1, 1, 2, 5, 5, 9, 9.5))
                out.append(s.mk(r, t, u["uid"], m, amt, "ecom", ad, aip, aci, 1, kind))
            if r.random() < 0.6:
                t += r.uniform(20, 120)
                m = s.mers[r.choice([k for k in s.onl if s.mers[k]["cat"] in RISKY] or s.onl)]
                out.append(s.mk(r, t, u["uid"], m, mean * r.uniform(3, 14), "ecom", ad, aip, aci, 1, kind))
        elif kind == "ato":  # phished net-banking credentials: new device, new beneficiary, IMPS out
            for _ in range(r.randint(1, 3)):
                t += r.uniform(60, 500)
                if r.random() < 0.35:   # structuring just under a limit
                    amt = r.choice(LIM) * r.uniform(0.95, 0.995)
                else:
                    amt = min(mean * r.uniform(12, 60), 300000)
                ip, ci = ((("%d.%d.%d.%d" % (210 + u["hc"], r.randrange(256), r.randrange(256), r.randrange(1, 255))), u["hc"])
                          if r.random() < 0.4 else (aip, aci))
                out.append(s.mk(r, t, u["uid"], dict(mid=s.mpay(r), cat="bank_transfer"), amt, "imps", ad if r.random() < 0.15 else "dn%06d" % r.randrange(10 ** 6),
                                ip, ci, 1, kind, pers=True))
        elif kind == "sim_swap":  # attacker ports the number, binds UPI on a new phone, drains in a burst
            hrs = r.uniform(0.5, 48)
            dev = "dn%06d" % r.randrange(10 ** 6)
            for _ in range(r.randint(2, 5)):
                t += r.uniform(60, 300)
                amt = r.choice((49999, 99999, 95000, 90000, 24999)) * r.uniform(0.97, 1.0) if r.random() < 0.6 else min(mean * r.uniform(10, 40), 100000)
                out.append(s.mk(r, t, u["uid"], dict(mid=s.mpay(r), cat="p2p"), amt, "upi", dev, aip, aci, 1, kind, pers=True, sim=hrs + (t - ts) / 3600))
        elif kind == "vishing":  # caller convinces the customer to pay; often with a screen-share app running
            ch = "upi" if r.random() < 0.7 else "imps"
            rat = r.random() < 0.6
            for _ in range(r.randint(1, 4)):
                t += r.uniform(60, 600)
                amt = min(mean * r.uniform(6, 30), CAP[ch])
                out.append(s.mk(r, t, u["uid"], dict(mid=s.mpay(r), cat="p2p" if ch == "upi" else "bank_transfer"), amt, ch,
                                r.choice(u["devs"]), vip(), u["hc"], 1, kind, pers=True, rat=rat))
        elif kind == "upi_scam":  # QR / refund / fake-buyer scams and unverified-merchant collect requests
            coll = r.random() < 0.35
            for _ in range(r.randint(1, 3)):
                t += r.uniform(60, 400)
                amt = r.uniform(200, 2000) if coll else min(mean * r.uniform(2, 25), 50000)
                out.append(s.mk(r, t, u["uid"], dict(mid=s.mpay(r), cat="p2p"), amt, "upi", r.choice(u["devs"]), vip(), u["hc"], 1, kind,
                                pers=True, coll=coll))
        elif kind == "travel":  # cloned card used far away
            m0 = s.mers[r.choice(s.byc[u["hc"]])]
            out.append(s.mk(r, ts, u["uid"], m0, math.exp(r.gauss(u["mu"], u["sg"])), "pos", None, None, u["hc"], 0, "legit"))
            la, lo = CITY[u["hc"]][1], CITY[u["hc"]][2]
            near = r.random() < 0.4  # ambiguous: a plausible-but-fast hop vs. an obvious teleport
            d = lambda c: hav(la, lo, CITY[c][1], CITY[c][2])
            far = [c for c in range(len(CITY)) if c != u["hc"] and (600 < d(c) < 2500 if near else d(c) > 2500) and s.byc[c]]
            ci = r.choice(far or [c for c in range(NIN) if c != u["hc"]])
            t = ts + (r.uniform(2400, 7200) if near else r.uniform(120, 2400))
            for _ in range(r.randint(1, 3)):
                out.append(s.mk(r, t, u["uid"], s.mers[r.choice(s.byc[ci])], mean * r.uniform(2, 10), "pos", None, None, ci, 1, kind))
                t += r.uniform(120, 900)
        elif kind == "high_value":  # stolen card details used online
            m = s.mers[r.choice([k for k in s.onl if s.mers[k]["cat"] in RISKY] or s.onl)]
            out.append(s.mk(r, ts, u["uid"], m, min(mean * r.uniform(6, 25), 150000), "ecom", ad, aip, aci, 1, kind))
        elif kind == "mule":  # ring accounts cash out together from shared devices
            for k in r.sample(ring["uids"], r.randint(3, 5)):
                v, t = s.users[k], ts + r.uniform(0, 1800)
                for _ in range(r.randint(2, 5)):
                    t += r.uniform(30, 900)
                    own = r.random() < 0.4  # off-ring session: fresh device + local network, ring link not visible
                    ip = ("%d.%d.%d" % (210 + v["hc"], r.randrange(256), r.randrange(256)) if own else r.choice(ring["ips"])) + ".%d" % r.randrange(1, 255)
                    dev = "dn%06d" % r.randrange(10 ** 6) if own else r.choice(ring["devs"])
                    amt = r.choice((5000, 10000, 20000, 25000, 49999, 50000)) if r.random() < 0.6 else r.uniform(2000, 45000)
                    if r.random() < 0.5:
                        m = s.mers[r.choice([j for j in s.onl if s.mers[j]["cat"] in ("gift_cards", "crypto", "gaming")] or s.onl)]
                        out.append(s.mk(r, t, v["uid"], m, amt, "upi", dev, ip, v["hc"] if own else ring["ci"], 1, kind))
                    else:
                        out.append(s.mk(r, t, v["uid"], dict(mid=s.mpay(r), cat="p2p"), amt, "upi", dev, ip, v["hc"] if own else ring["ci"], 1, kind, pers=True))
        return out

    def window(s, r, t0, t1, boost=1.0):
        out = s.legit(r, t0, t1)
        for kind, rate in RATE.items():
            for _ in range(pois(r, rate * boost * (t1 - t0) / DAY)):
                out += s.fraud(r, kind, r.uniform(t0, t1))
        out.sort(key=lambda e: e["ts"])
        return out
