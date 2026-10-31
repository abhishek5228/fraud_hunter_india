"""Analyst copilot: turn one scored case into a short brief and a suspicious-transaction-report DRAFT.

The facts and the decision always come from the engine. Text is written from a template, so it works with no API key and can be
audited. If ANTHROPIC_API_KEY is set the brief can optionally be re-worded by an LLM that is shown ONLY the structured facts
(a pseudonymous customer id, amounts, reason codes), is told not to add anything, and whose output is rejected if it drops a
number or invents one. Any failure falls back to the template. The LLM never decides anything.

The report is a draft with the usual headings. It is NOT the FIU-IND FINnet format; an analyst must review and complete it.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

from .fmt import inr
from .gen import IST

ACT = {0: "approved", 1: "challenged with a step-up (OTP / in-app confirmation)", 2: "declined"}
RAIL = dict(upi="UPI", ecom="card, online", pos="card, in person", atm="ATM withdrawal", imps="IMPS / net-banking transfer")
HI = {
    "MULE_PAYEE": "प्राप्तकर्ता कई हालिया ठगी शिकायतों से जुड़ा है", "PAYEE_FAN_IN": "इस नए प्राप्तकर्ता को इस हफ़्ते कई अन्य ग्राहकों ने भी पहली बार पैसे भेजे",
    "SCREEN_SHARE_NEW_PAYEE": "स्क्रीन-शेयरिंग ऐप चालू है और भुगतान पहली बार के व्यक्ति को जा रहा है", "SCREEN_SHARE_ACTIVE": "भुगतान के दौरान स्क्रीन-शेयरिंग ऐप चालू था",
    "SIM_SWAP_DRAIN": "SIM बदलने के तुरंत बाद नए डिवाइस से बड़ी रकम पहली बार के प्राप्तकर्ता को", "SIM_CHANGE_NEW_DEVICE": "SIM बदलने के बाद नए डिवाइस से भुगतान",
    "IMPOSSIBLE_TRAVEL": "कार्ड का उपयोग इतनी दूर हुआ जितना इतने कम समय में संभव नहीं", "CARD_TESTING": "कुछ मिनटों में कई छोटे ऑनलाइन चार्ज (कार्ड टेस्टिंग)",
    "DEVICE_RING": "इस डिवाइस से इस हफ़्ते कई अन्य खातों ने भुगतान किया", "SHARED_NEW_DEVICE": "यह डिवाइस कई अन्य खातों पर भी दिखा",
    "BAD_REPUTATION": "डिवाइस या नेटवर्क कई पुष्ट ठगी रिपोर्टों से जुड़ा है", "LIMIT_STRUCTURING": "रकम भुगतान सीमा से ठीक नीचे रखी गई है",
    "COLLECT_FIRST_PAYEE": "पहली बार के प्राप्तकर्ता की कलेक्ट रिक्वेस्ट मंज़ूर की जा रही है", "NEW_DEVICE_HIGH_VALUE": "नए डिवाइस से बड़ी रकम",
    "EXCEEDS_UPI_LIMIT": "रकम किसी भी UPI सीमा से अधिक है", "NEW_CUSTOMER_HIGH_VALUE": "लगभग बिना इतिहास वाले ग्राहक से बड़ी रकम",
    "ANON_NETWORK": "भुगतान VPN, प्रॉक्सी या डेटा-सेंटर नेटवर्क से आया", "CONSORTIUM_MULE": "किसी दूसरे बैंक ने इस प्राप्तकर्ता को संदिग्ध बताया है", "BLOCKLIST": "यह इकाई हाथ से ब्लॉक की गई थी",
}
FOLLOW = {
    "MULE_PAYEE": "Place the payee on watch; check inbound credits and onward transfers; consider a hold on the beneficiary account.",
    "PAYEE_FAN_IN": "Review the other customers who paid this payee this week; contact them if any payment was authorised under pressure.",
    "SCREEN_SHARE_NEW_PAYEE": "Call the customer on the registered number (not the one in any message) and ask if anyone is guiding them.",
    "SCREEN_SHARE_ACTIVE": "Call the customer on the registered number to confirm the payment is theirs.",
    "SIM_SWAP_DRAIN": "Verify the SIM change with the telecom operator; restrict high-value transfers until confirmed.",
    "IMPOSSIBLE_TRAVEL": "Check card status; consider blocking and reissuing the card.",
    "CARD_TESTING": "Block the card and the merchant ID; review other cards seen on this device or network.",
    "DEVICE_RING": "Review all accounts that used this device this week.",
    "BAD_REPUTATION": "Review the device or network and the other accounts linked to it.",
    "LIMIT_STRUCTURING": "Review the last 30 days for repeated amounts just under a limit.",
    "EXCEEDS_UPI_LIMIT": "Treat as invalid or malformed; check the integration that submitted it.",
    "NEW_CUSTOMER_HIGH_VALUE": "Verify the customer's identity and source of funds before releasing.",
    "ANON_NETWORK": "Ask the customer to confirm; check for other payments from the same network.",
    "CONSORTIUM_MULE": "Another member bank has strong evidence against this payee; request details through the consortium channel.",
    "BLOCKLIST": "Entity was blocked manually; check the original analyst note.",
}


def facts(c, now=None):
    """The only things a writer (template or LLM) is allowed to talk about."""
    t = time.strftime("%d %b %Y, %H:%M IST", time.gmtime(c["ts"] + IST))
    return dict(id=c["id"], customer=c["uid"], when=t, amount=inr(c["amt"], 0 if c["amt"] >= 100 else 2), amount_raw=round(c["amt"], 2),
                rail=RAIL.get(c["chan"], c["chan"]), payee=c["mid"], category=c["cat"], city=c.get("city") or "unknown", risk_pct=c["score"],
                decision=c["dname"], action=ACT[c["dec"]], rules=[dict(code=h["code"], msg=h["msg"]) for h in c["hits"]],
                drivers=[t["txt"] for t in c["top"][:3] if t["c"] > 0], follow=[FOLLOW[h["code"]] for h in c["hits"] if h["code"] in FOLLOW])


def template(f):
    why = [r["msg"] for r in f["rules"]] or f["drivers"] or ["model score only; no single rule fired"]
    en = ("%s payment of %s by customer %s on %s, paying %s. Risk score %d%%; the engine %s. Main reasons: %s." % (
        f["rail"][0].upper() + f["rail"][1:], f["amount"], f["customer"], f["when"], f["payee"], f["risk_pct"], f["action"], "; ".join(why[:3])))
    hi = ("%s से %s का भुगतान, ग्राहक %s, %s, प्राप्तकर्ता %s। जोखिम स्कोर %d%%; इंजन ने इसे %s। मुख्य कारण: %s।" % (
        f["rail"], f["amount"], f["customer"], f["when"], f["payee"], f["risk_pct"],
        {"approved": "मंज़ूर किया", "declined": "अस्वीकार किया"}.get(f["action"], "स्टेप-अप (OTP/ऐप पुष्टि) के लिए रोका"), "; ".join(why[:3])))
    why_hi = [HI.get(r["code"], "नियम %s लागू हुआ" % r["code"]) for r in f["rules"]] or ["मॉडल स्कोर (ब्योरा अंग्रेज़ी रिपोर्ट में)"]
    hi = hi.rsplit("मुख्य कारण:", 1)[0] + "मुख्य कारण: " + "; ".join(why_hi[:3]) + "।"
    nxt = f["follow"] or ["Review the customer's recent history and confirm with them on the registered number if the decision was a step-up or decline."]
    st = "\n".join([
        "DRAFT SUSPICIOUS TRANSACTION REPORT (analyst must review; not the FIU-IND FINnet format)",
        "1. Reporting entity: [BANK NAME / BRANCH / PRINCIPAL OFFICER]",
        "2. Customer: %s (pseudonymous id; attach KYC details from the core system)" % f["customer"],
        "3. Transaction: id %s | %s | %s | %s | payee %s | category %s | location %s" % (f["id"], f["when"], f["amount"], f["rail"], f["payee"], f["category"], f["city"]),
        "4. Grounds of suspicion: " + "; ".join(why),
        "5. Automated assessment: risk %d%% (additive model with exact factor contributions; guardrail rules can only escalate)." % f["risk_pct"],
        "6. Action taken: payment %s." % f["action"],
        "7. Recommended follow-up: " + " ".join(nxt),
        "8. If the customer was deceived into paying: advise reporting at cybercrime.gov.in and the 1930 helpline, and record the complaint number here: [____].",
        "9. Analyst: [NAME] | Date: [____] | Decision: [report / no report] | Reason: [____]"])
    j = dict(draft=True, format="free-form headings, not FIU-IND FINnet", reporting_entity="[BANK NAME / BRANCH / PRINCIPAL OFFICER]",
             customer=dict(pseudonymous_id=f["customer"], kyc="[attach from core system]"),
             transaction=dict(id=f["id"], when=f["when"], amount_inr=f["amount_raw"], rail=f["rail"], payee=f["payee"], category=f["category"], location=f["city"]),
             grounds_of_suspicion=why, automated_risk_pct=f["risk_pct"], action_taken=f["action"], recommended_follow_up=nxt,
             complaint_reference="[cybercrime.gov.in / 1930 complaint number, if the customer was deceived]", analyst=dict(name="[ ]", date="[ ]", decision="[report / no report]", reason="[ ]"))
    return dict(en=en, hi=hi, str=st, str_json=j)


def _nums(s):
    return set(re.findall(r"\d[\d,]*\.?\d*", s))


def polish(f, base, call=None):
    """Optionally reword the English brief with an LLM. Returns (text, source). Never raises."""
    k = os.environ.get("ANTHROPIC_API_KEY")
    if not k:
        return base, "template"
    prompt = ("Rewrite these facts as a concise 3-4 sentence note for a bank fraud analyst. Use ONLY the facts below, add nothing, "
              "keep every number exactly as given.\n\n" + json.dumps({x: f[x] for x in f if x != "follow"}, ensure_ascii=False))
    try:
        out = (call or _call)(k, prompt).strip()
    except (urllib.error.URLError, OSError, ValueError, KeyError, TimeoutError):
        return base, "template (LLM unavailable)"
    allowed = _nums(json.dumps(f)) | _nums(base)
    if not out or not _nums(out) <= allowed:
        return base, "template (LLM output rejected: it added numbers)"
    return out, "llm"


def _call(key, prompt):
    body = json.dumps(dict(model=os.environ.get("FH_LLM_MODEL", "claude-sonnet-5-5"), max_tokens=400, messages=[dict(role="user", content=prompt)])).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read(100000))["content"][0]["text"]


def brief(c, llm=False, call=None):
    f = facts(c)
    b = template(f)
    b["source"] = "template"
    if llm:
        b["en"], b["source"] = polish(f, b["en"], call)
    b["facts"] = f
    return b
