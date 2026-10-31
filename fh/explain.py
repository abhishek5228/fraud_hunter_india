"""Turn feature contributions into sentences an analyst (or a customer-support agent) can read."""

def _lvl(v):
    return "high-risk" if v >= 0.25 else ("elevated-risk" if v >= 0.1 else "low-risk")


TXT = {
    "lamt": lambda r: "Amount $%.2f" % r["amt"],
    "zamt": lambda r: "Amount is %.1fx this customer's typical spend" % r["rat"],
    "rmax": lambda r: "Largest purchase on record is $%.0f" % r["mx"],
    "c1m": lambda r: "%d other charge(s) in the last minute" % r["c1"],
    "c10m": lambda r: "%d other charge(s) in the last 10 minutes" % r["c10"],
    "c1h": lambda r: "%d other charge(s) in the last hour" % r["c1h"],
    "c24h": lambda r: "%d charge(s) in the last 24 hours" % r["cd"],
    "s1h": lambda r: "$%.0f spent in the last hour" % r["s1h"],
    "ndev": lambda r: "First time this device is seen on the account" if r["ndev"] else "Recognised device / card-present",
    "nip": lambda r: "New network (IP range) for this customer" if r["nip"] else "Familiar network or card-present",
    "ncty": lambda r: "First transaction ever from %s" % r["cty"] if r["ncty"] else "Familiar country",
    "nmer": lambda r: "First purchase at this merchant" if r["nmer"] else "Repeat merchant",
    "ncat": lambda r: "New spending category (%s)" % r["cat"] if r["ncat"] else "Usual spending category",
    "hrar": lambda r: "Unusual hour for this customer (%02d:00 local)" % r["lh"],
    "dkm": lambda r: "%.0f km from the previous transaction" % r["km"],
    "sped": lambda r: "Implied travel speed %.0f km/h since previous transaction" % r["kmh"],
    "hkm": lambda r: "%.0f km from the customer's usual area" % r["hk"],
    "devu": lambda r: "Device used by %d other account(s) this week" % r["devu"],
    "ipu": lambda r: "Network used by %d other account(s) this week" % r["ipu"],
    "dbad": lambda r: "Device linked to %d confirmed fraud report(s)" % r["dbad"],
    "ibad": lambda r: "Network linked to %d confirmed fraud report(s)" % r["ibad"],
    "mbad": lambda r: "Merchant linked to %d confirmed fraud report(s)" % r["mbad"],
    "ecom": lambda r: "Online card-not-present purchase" if r["chan"] == "ecom" else "Card-present purchase",
    "atm": lambda r: "ATM cash withdrawal" if r["chan"] == "atm" else "Not a cash withdrawal",
    "crsk": lambda r: "%s is a %s category" % (r["cat"], _lvl(r["crsk"])),
    "cold": lambda r: "Thin history (%d prior transactions)" % r["n"] if r["n"] < 4 else "Established history",
    "tiny": lambda r: "Micro-amount after other small charges (card-testing shape)",
    "rnd": lambda r: "Round-number amount",
    "xdz": lambda r: "New device combined with an unusually large amount",
    "xdc": lambda r: "New device buying in a risky category",
    "xhz": lambda r: "Far from home and unusually large amount",
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
    lead += " Expected cost if approved $%.2f vs $%.2f for the chosen action." % (cost[0], cost[dec])
    return lead
