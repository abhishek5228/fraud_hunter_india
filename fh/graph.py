"""Mule-network view: personal payees that many unrelated customers paid for the first time this week, with the devices
that tie those senders together. Built from the live feature store, so a launched attack shows up as a growing hub."""
import hashlib

WEEK = 7 * 86400


def short(s):
    return hashlib.sha1(str(s).encode()).hexdigest()[:8]


def mask(s):
    """Show enough to recognise a handle, not enough to publish it: ab***@ybl, 98****21."""
    s = str(s)
    if "@" in s:
        a, b = s.split("@", 1)
        return a[:2] + "***@" + b
    return s if len(s) <= 6 or s[0] in "uc" and s[1:].isdigit() else s[:2] + "****" + s[-2:]


def build(st, now, min_fan=3, top=10, max_senders=14):
    cl = []
    allow = getattr(st, "allow", set())
    for pay, snd in st.pu.items():
        if pay in allow:
            continue                                       # an analyst already ruled this one legitimate
        rec = [u for u, t in snd.items() if 0 <= now - t <= WEEK]
        if len(rec) < min_fan:
            continue
        bad = st.nbad("m:" + pay, now)
        rec.sort(key=lambda u: -snd[u])
        shown = rec[:max_senders]
        dev = {}
        for u in shown:
            P = st.u.get(u)
            for d in (P.devs if P else ()):
                if len([v for v in st.du.get(d, {}) if v in shown]) >= 2:
                    dev.setdefault(d, []).append(u)
        links = {d: us for d, us in dev.items() if len(set(us)) >= 2}
        first = sum(1 for u in rec if (st.u.get(u) is None or pay not in st.u[u].mers))
        share = first / len(rec)
        span_h = (max(snd[u] for u in rec) - min(snd[u] for u in rec)) / 3600
        # Confidence that this is a mule and not a shop, landlord or charity: four independent kinds of evidence.
        pts = (25 if share >= 0.8 else 10 if share >= 0.5 else 0) + (35 if bad >= 2 else 15 if bad == 1 else 0) + (20 if links else 0) + (20 if span_h <= 6 else 8 if span_h <= 24 else 0)
        why = ["%d different customers paid it this week" % len(rec), "%d of them had never paid it before" % first]
        if bad:
            why.append("%d fraud complaint(s) already linked" % bad)
        if links:
            why.append("%d device(s) shared between its senders" % len(links))
        if span_h <= 6:
            why.append("all of it arrived within %.0f hours" % max(span_h, 1))
        hints = []
        if share < 0.5:
            hints.append("Most senders had paid it before, which looks like a popular shop, landlord or charity rather than a mule.")
        if not bad and not links:
            hints.append("No complaints and no shared devices yet: novelty alone is weak evidence.")
        cl.append(dict(id=short(pay), payee=mask(pay) + " \u00b7" + short(pay), senders=len(rec), complaints=bad, first_time=first, score=pts, confidence=pts,
                       level="high" if pts >= 60 else "watch", why=why, hints=hints, span_hours=round(span_h, 1),
                       nodes=[dict(id=u, kind="sender", first=(st.u.get(u) is None or pay not in st.u[u].mers)) for u in shown],
                       devices=[dict(id=mask(d), senders=sorted(set(us))) for d, us in links.items()][:6]))
    cl.sort(key=lambda c: (-c["confidence"], -c["senders"]))
    return dict(clusters=cl[:top], total=len(cl), at=now)


def find(st, cid):
    """Resolve a cluster id (short hash) back to the payee it stands for."""
    for pay in st.pu:
        if short(pay) == cid:
            return pay
    return None


def verdict(st, cid, v, now):
    """An analyst's ruling on a hub. 'mule' adds fraud complaints against the payee (so the engine blocks it); 'legit' allowlists it
    (hides it here and stops the first-time-fan-in rule from firing on it). Returns the payee id, or None if the hub has aged out."""
    pay = find(st, cid)
    if pay is None:
        return None
    if v == "mule":
        for _ in range(2):
            st.bad["m:" + pay].append(now)
    elif v == "legit":
        st.__dict__.setdefault("allow", set()).add(pay)
    else:
        raise ValueError("verdict must be 'mule' or 'legit'")
    return pay
