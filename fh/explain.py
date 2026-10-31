"""Turn feature contributions into sentences an analyst (or a customer-support agent) can read,
and into short bilingual (English / Hindi) messages a customer can act on."""
from .fmt import inr

RAILS = {"upi": "UPI payment", "imps": "Net-banking transfer (IMPS/NEFT)", "ecom": "Online card payment",
         "pos": "In-person card payment", "atm": "ATM cash withdrawal"}


def _lvl(v):
    return "high-risk" if v >= 0.25 else ("elevated-risk" if v >= 0.1 else "low-risk")


def _amt(r):
    return inr(r["amt"], 0 if r["amt"] >= 100 else 2)


TXT = {
    "lamt": lambda r: "Amount %s" % _amt(r),
    "zamt": lambda r: "Amount is %.1fx this customer's typical spend" % r["rat"],
    "rmax": lambda r: "Largest payment on record is %s" % inr(r["mx"], 0),
    "c1m": lambda r: "%d other payment(s) in the last minute" % r["c1"],
    "c10m": lambda r: "%d other payment(s) in the last 10 minutes" % r["c10"],
    "c1h": lambda r: "%d other payment(s) in the last hour" % r["c1h"],
    "c24h": lambda r: "%d payment(s) in the last 24 hours" % r["cd"],
    "s1h": lambda r: "%s sent in the last hour" % inr(r["s1h"], 0),
    "ndev": lambda r: "First time this device is seen on the account" if r["ndev"] else "Recognised device or card-present",
    "nip": lambda r: "New network (IP range) for this customer" if r["nip"] else "Familiar network or card-present",
    "ncty": lambda r: "First transaction ever from %s" % r["cty"] if r["ncty"] else "Familiar country",
    "nmer": lambda r: "First payment to this payee" if r["nmer"] else "Existing payee",
    "ncat": lambda r: "New spending category (%s)" % r["cat"].replace("_", " ") if r["ncat"] else "Usual spending category",
    "hrar": lambda r: "Unusual hour for this customer (%02d:00 IST)" % r["lh"],
    "dkm": lambda r: "%.0f km from the last in-person transaction" % r["km"],
    "sped": lambda r: "Implied travel speed %.0f km/h since the last in-person transaction" % r["kmh"],
    "hkm": lambda r: "%.0f km from the customer's usual area" % r["hk"],
    "devu": lambda r: "Device used by %d other account(s) this week" % r["devu"],
    "ipu": lambda r: "Network used by %d other account(s) this week" % r["ipu"],
    "dbad": lambda r: "Device linked to %d recent fraud report(s)" % r["dbad"],
    "ibad": lambda r: "Network linked to %d recent fraud report(s)" % r["ibad"],
    "mbad": lambda r: "Payee linked to %d recent fraud complaint(s)" % r["mbad"],
    "ecom": lambda r: RAILS[r["chan"]],
    "atm": lambda r: RAILS[r["chan"]],
    "upi": lambda r: RAILS[r["chan"]],
    "imps": lambda r: RAILS[r["chan"]],
    "crsk": lambda r: "%s is a %s category" % (r["cat"].replace("_", " "), _lvl(r["crsk"])),
    "cold": lambda r: "Thin history (%d prior transactions)" % r["n"] if r["n"] < 4 else "Established history",
    "tiny": lambda r: "Micro-amount online after other small charges (card-testing shape)",
    "rnd": lambda r: "Round-number amount",
    "lim": lambda r: "Amount sits just under a payment limit" if r["lim"] else "Amount not near a payment limit",
    "pers": lambda r: "Payee is a person or account, not a verified merchant" if r["pers"] else "Verified merchant payee",
    "fanin": lambda r: "%d other customer(s) paid this payee this week" % r["fan"],
    "pfirst": lambda r: "Payee never seen before anywhere on the platform" if r["pfirst"] else "Payee already known to the platform",
    "simc": lambda r: "SIM changed %.0f hours ago" % r["sim"] if r["sim"] < 72 else "No recent SIM change",
    "rat": lambda r: "Screen-sharing or remote-access app active" if r["ratf"] else "No remote-access app detected",
    "coll": lambda r: "Payment approves a collect request" if r["coll"] else "Customer-initiated payment",
    "xdz": lambda r: "New device combined with an unusually large amount",
    "xdc": lambda r: "New device paying in a risky category",
    "xhz": lambda r: "Far from home and unusually large amount",
    "xrz": lambda r: "Screen-sharing combined with an unusually large amount",
    "xnz": lambda r: "First-time person payee combined with an unusually large amount",
    "xsd": lambda r: "New device right after a SIM change",
    "xnf": lambda r: "First-time payee that other customers have also just paid",
}


def reasons(names, con, r, k=8, eps=0.05):
    """Top-k contributions by magnitude, as [{f, c, txt}]; c > 0 pushes risk up."""
    ix = sorted(range(len(con)), key=lambda i: -abs(con[i]))
    return [dict(f=names[i], c=round(con[i], 3), txt=TXT[names[i]](r)) for i in ix[:k] if abs(con[i]) >= eps]


def summary(dec, p, top, hits, cost, amt):
    ok = [t for t in top if t["f"] != "lamt"]
    ups = [t["txt"] for t in ok if t["c"] > 0][:3]
    dns = [t["txt"] for t in ok if t["c"] < 0][:2]
    pc = "%.1f%%" % (100 * p) if p >= 0.001 else "<0.1%"
    if dec == 0:
        s = "Approved at %s fraud risk." % pc
        if dns:
            s += " Reassuring: " + "; ".join(dns) + "."
        if ups:
            s += " Watch: " + ups[0] + "."
        return s
    lead = ("Declined" if dec == 2 else "Challenged with step-up") + " at %s fraud risk." % pc
    if hits:
        lead += " Rule %s fired." % hits[0][1]
    if ups:
        lead += " Drivers: " + "; ".join(ups) + "."
    lead += " Expected cost if approved %s vs %s for the chosen action." % (inr(cost[0], 0), inr(cost[dec], 0))
    return lead


def customer_msg(dec, amt, payee, codes):
    """What the customer sees. Plain words, no jargon, never reveals the rule logic."""
    if dec == 0:
        return None
    a = inr(amt, 0 if amt >= 100 else 2)
    shr = any(c.startswith("SCREEN_SHARE") for c in codes)
    if dec == 1:
        en = ("Please confirm this %s payment to %s. Approve it with your UPI PIN or OTP only if you know the payee and "
              "you started this payment yourself. Nobody from a bank ever asks for your PIN or OTP." % (a, payee))
        hi = ("कृपया %s को किए जा रहे %s के भुगतान की पुष्टि करें। अपने UPI PIN या OTP से तभी स्वीकृत करें जब आप प्राप्तकर्ता को जानते हों "
              "और यह भुगतान आपने स्वयं शुरू किया हो। कोई भी बैंक कभी आपका PIN या OTP नहीं माँगता।" % (payee, a))
    else:
        en = ("We stopped a %s payment to %s to protect your account. If this was you, contact your bank. If someone asked you "
              "to make this payment, do not go ahead: report it on cybercrime.gov.in or call 1930." % (a, payee))
        hi = ("आपके खाते की सुरक्षा के लिए हमने %s को %s का भुगतान रोका है। यदि यह आपने किया था तो अपने बैंक से संपर्क करें। "
              "यदि किसी ने आपसे यह भुगतान करवाया है तो आगे न बढ़ें और cybercrime.gov.in पर शिकायत करें या 1930 पर कॉल करें।" % (payee, a))
    if shr:
        en += " A screen-sharing app is running: stop sharing your screen now."
        hi += " स्क्रीन-शेयरिंग ऐप चल रहा है: कृपया अभी स्क्रीन साझा करना बंद करें।"
    return dict(en=en, hi=hi)
