"""Deterministic guardrails. They never *lower* a decision, they only raise it:
final = max(model policy, strongest rule). Each hit carries a reason code."""

from .gen import ip24

STEP, BLOCK = 1, 2


def check(x, r, st):
    hits = []
    if r["kmh"] > 900 and r["km"] > 500:
        # card-present teleportation is physical proof; for online IP-geo on a *known device* it is probably a VPN
        lvl = BLOCK if (x["chan"] != "ecom" or r["ndev"]) else STEP
        hits.append((lvl, "IMPOSSIBLE_TRAVEL",
                     "Card used %.0f km from its last in-person use %.0f min earlier (%.0f km/h)" % (r["km"], (r["gap"] or 0) / 60, r["kmh"])))
    if r["sm5"] >= 3 and x["amt"] < 5:
        hits.append((BLOCK, "CARD_TESTING", "%d micro-charges in 5 minutes, this is the next one" % r["sm5"]))
    if r["devu"] >= 6:
        hits.append((BLOCK, "DEVICE_RING", "Device touched by %d other accounts this week" % r["devu"]))
    elif r["devu"] >= 3:
        hits.append((STEP, "SHARED_NEW_DEVICE", "New device also seen on %d other accounts" % r["devu"]))
    if r["dbad"] >= 2 or r["ibad"] >= 3:
        hits.append((BLOCK, "BAD_REPUTATION", "Device/network tied to %d confirmed fraud reports" % max(r["dbad"], r["ibad"])))
    for k in ("u:" + x["uid"], "d:" + str(x["dev"]), "i:" + str(ip24(x["ip"]))):
        if k in st.blk:
            hits.append((BLOCK, "BLOCKLIST", "Manually blocked entity %s" % k))
    if r["ndev"] and x["amt"] >= 1000:
        hits.append((STEP, "NEW_DEVICE_HIGH_VALUE", "New device with a $%.0f purchase" % x["amt"]))
    return hits


def level(hits):
    return max((h[0] for h in hits), default=0)
