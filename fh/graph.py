"""Mule-network view: personal payees that many unrelated customers paid for the first time this week, with the devices
that tie those senders together. Built from the live feature store, so a launched attack shows up as a growing hub."""
import hashlib

WEEK = 7 * 86400


def short(s):
    return hashlib.sha1(str(s).encode()).hexdigest()[:4]


def mask(s):
    """Show enough to recognise a handle, not enough to publish it: ab***@ybl, 98****21."""
    s = str(s)
    if "@" in s:
        a, b = s.split("@", 1)
        return a[:2] + "***@" + b
    return s if len(s) <= 6 or s[0] in "uc" and s[1:].isdigit() else s[:2] + "****" + s[-2:]


def build(st, now, min_fan=3, top=10, max_senders=14):
    cl = []
    for pay, snd in st.pu.items():
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
        score = len(rec) + 4 * bad + 3 * len(links)
        why = ["%d different customers paid it this week" % len(rec)]
        if first:
            why.append("%d of them had never paid it before" % first)
        if bad:
            why.append("%d fraud complaint(s) already linked" % bad)
        if links:
            why.append("%d device(s) shared between its senders" % len(links))
        cl.append(dict(id=short(pay), payee=mask(pay) + " \u00b7" + short(pay), senders=len(rec), complaints=bad, first_time=first, score=score,
                       level="high" if (bad >= 2 or len(rec) >= 6) else "watch", why=why,
                       nodes=[dict(id=u, kind="sender", first=(st.u.get(u) is None or pay not in st.u[u].mers)) for u in shown],
                       devices=[dict(id=mask(d), senders=sorted(set(us))) for d, us in links.items()][:6]))
    cl.sort(key=lambda c: -c["score"])
    return dict(clusters=cl[:top], total=len(cl), at=now)
