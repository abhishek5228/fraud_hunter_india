"""Deterministic guardrails. They never *lower* a decision, they only raise it:
final = max(model policy, strongest rule). Each hit carries a reason code."""
from .gen import ip24
from .fmt import inr

STEP, BLOCK = 1, 2


def check(x, r, st):
    hits = []
    pers, nmer, ch = r["pers"], r["nmer"], r["chan"]
    if r["kmh"] > 900 and r["km"] > 500:
        # card-present teleportation is physical proof; on UPI / online, IP-geo on a *known device* is probably a VPN
        lvl = BLOCK if (ch in ("pos", "atm") or r["ndev"]) else STEP
        hits.append((lvl, "IMPOSSIBLE_TRAVEL",
                     "Card used %.0f km from its last in-person use %.0f min earlier (%.0f km/h)" % (r["km"], (r["gap"] or 0) / 60, r["kmh"])))
    if r["sm5"] >= 3 and ch == "ecom" and x["amt"] < 10:
        hits.append((BLOCK, "CARD_TESTING", "%d micro-charges in 5 minutes, this is the next one" % r["sm5"]))
    if r["devu"] >= 6:  # a kiosk phone has many users too; it only matters when paying a stranger or moving real money
        if pers and nmer:
            hits.append((BLOCK, "DEVICE_RING", "Device touched by %d other accounts this week, paying a first-time person" % r["devu"]))
        elif x["amt"] >= 10000:
            hits.append((STEP, "DEVICE_RING", "Device touched by %d other accounts this week" % r["devu"]))
    elif r["devu"] >= 3 and pers and nmer:
        hits.append((STEP, "SHARED_NEW_DEVICE", "Device also seen on %d other accounts this week, paying a first-time person" % r["devu"]))
    if pers and r["mbad"] >= 2:
        hits.append((BLOCK, "MULE_PAYEE", "Payee linked to %d recent fraud complaints (bank reports, 1930 / cybercrime portal)" % r["mbad"]))
    if r["dbad"] >= 2 or r["ibad"] >= 3:
        hits.append((BLOCK, "BAD_REPUTATION", "Device/network tied to %d confirmed fraud reports" % max(r["dbad"], r["ibad"])))
    if r["ratf"]:
        if pers and nmer:
            hits.append((BLOCK, "SCREEN_SHARE_NEW_PAYEE", "Screen-sharing or remote-access app active while paying a first-time person"))
        elif pers or x["amt"] >= 5000:   # a screen-share during a Rs 40 chai payment is not worth interrupting
            hits.append((STEP, "SCREEN_SHARE_ACTIVE", "Screen-sharing or remote-access app active during payment"))
    if r["sim"] < 72 and r["ndev"]:
        if pers and nmer and x["amt"] >= 25000:
            hits.append((BLOCK, "SIM_SWAP_DRAIN", "New device %.0f h after a SIM change, large transfer to a first-time payee" % r["sim"]))
        elif x["amt"] >= 5000:
            hits.append((STEP, "SIM_CHANGE_NEW_DEVICE", "New device %.0f h after a SIM change, %s" % (r["sim"], inr(x["amt"], 0))))
    if pers and nmer and r["fan"] >= 3 and x["mid"] not in getattr(st, "allow", ()):
        hits.append((BLOCK if r["fan"] >= 6 else STEP, "PAYEE_FAN_IN", "First-time payee already paid by %d other customers this week" % r["fan"]))
    if pers and r["lim"]:
        hits.append((STEP, "LIMIT_STRUCTURING", "%s sits just under a payment limit" % inr(x["amt"], 0)))
    if r["coll"] and pers and nmer:
        hits.append((STEP, "COLLECT_FIRST_PAYEE", "Collect request from a first-time payee: approving it sends money out"))
    if r["ndev"] and x["amt"] >= 25000:
        hits.append((STEP, "NEW_DEVICE_HIGH_VALUE", "New device with a %s payment" % inr(x["amt"], 0)))
    if ch == "upi" and x["amt"] > 1_000_000:
        hits.append((BLOCK, "EXCEEDS_UPI_LIMIT", "%s is above every UPI transaction limit; a real UPI payment cannot be this large" % inr(x["amt"], 0)))
    P = st.u.get(x["uid"])
    if (P is None or P.n < 4) and x["amt"] >= 100_000:       # the model never saw big money from a stranger; do not let it extrapolate to "safe"
        hits.append((STEP, "NEW_CUSTOMER_HIGH_VALUE", "%s from a customer with almost no history" % inr(x["amt"], 0)))
    cp = getattr(st, "cons_plain", None)
    if cp and pers and x["mid"] in cp:
        hits.append((BLOCK, "CONSORTIUM_MULE", "Payee confirmed as flagged by %s through private set intersection (no customer data shared)" % cp[x["mid"]]["bank"]))
    cons = getattr(st, "cons", None)
    if cons and pers:                                    # a payee another member bank has strong evidence against (matched by keyed hash only)
        from . import consortium
        z = cons.get(consortium.tag(x["mid"]))
        if z:
            hits.append((BLOCK if z["n"] >= 2 else STEP, "CONSORTIUM_MULE", "Payee flagged by another bank in the sharing network (%d report(s); no customer data shared)" % z["n"]))
    for k in ("u:" + x["uid"], "d:" + str(x["dev"]), "i:" + str(ip24(x["ip"]))):
        if k in st.blk:
            hits.append((BLOCK, "BLOCKLIST", "Manually blocked entity %s" % k))
    return hits


def level(hits):
    return max((h[0] for h in hits), default=0)
