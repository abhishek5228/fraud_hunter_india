/* Scam Shield: the rules are the server's shield_rules.json, fetched, so browser and server cannot disagree. */
let SHR = null;
async function shieldRules() { return SHR || (SHR = await api("/api/shield/rules")); }

function shieldLocal(R, text) {
  let t = text;
  for (const m of text.matchAll(/upi:\/\/\S+/gi)) {
    try { const q = new URL(m[0]).searchParams; t += " " + ["pa", "pn", "tn"].filter(k => q.get(k)).map(k => k + " " + q.get(k)).join(" "); } catch (e) {}
  }
  const hit = [];
  for (const r of R.rules) { const m = new RegExp(r.re, "i").exec(t); if (m) hit.push({ id: r.id, w: r.w, en: r.en, hi: r.hi, seen: m[0].slice(0, 70) }); }
  const mail = new Set(["gmail", "yahoo", "outlook", "hotmail", "rediffmail", "icloud", "proton", "protonmail"]);
  const handles = (t.match(/\b[a-z0-9._\-]{2,}@[a-z]{2,}\b/gi) || []).filter(h => !mail.has(h.split("@")[1].toLowerCase()));
  return finishShield(R, hit, handles, null);
}
function finishShield(R, hit, handles, net) {
  let keep = 1; for (const h of hit) keep *= 1 - h.w / 100;
  const score = Math.round(100 * (1 - keep)), lv = score >= R.levels.danger ? "danger" : score >= R.levels.caution ? "caution" : "none";
  hit.sort((a, b) => b.w - a.w);
  return { score, level: lv, reasons: hit, handles, actions: R.actions[lv], network: net };
}

const SH_SAMPLES = [
  ["Bijli bill threat", "Dear customer, your electricity connection will be disconnected tonight 9:30 PM because last month bill is not updated. Call 9876543210 immediately."],
  ["KYC + AnyDesk", "Sir aapka KYC expire ho gaya hai. Abhi AnyDesk download karo aur OTP bata do, warna account block ho jayega."],
  ["Digital arrest", "This is CBI. A parcel in your name contains drugs. Join the video call now or you will face digital arrest. Transfer money to the safe account."],
  ["Refund handle (QR)", "upi://pay?pa=sbi.refund.support@ybl&pn=SBI%20Refund&am=4999"],
  ["Fake bank link", "Your SBI YONO account is suspended. Update now: https://sbi-kyc-update.xyz/login"],
  ["Normal payment", "Pay 480 to Ramesh Kirana Store ramesh@okaxis for milk and bread"]];

function shieldTab() {
  if (shieldTab.done) return; shieldTab.done = true;
  $("#sh-samples").replaceChildren(...SH_SAMPLES.map(([n, t]) => el("button", { class: "chip", onclick: () => { $("#sh-text").value = t; runShield(); } }, n)));
  $("#sh-go").onclick = runShield;
}
async function runShield() {
  const text = $("#sh-text").value.trim(), out = $("#sh-out");
  if (!text) { out.replaceChildren(el("div", { class: "card" }, el("div", { class: "empty" }, "Paste something to check."))); return; }
  const R = await shieldRules();
  let r = shieldLocal(R, text);
  if (!window.FH_DEMO) {            // live server: same rules plus what the engine knows about the payee
    try { r = await api("/api/shield", { text }); } catch (e) { if (/429|too many/i.test(e.message)) { out.replaceChildren(el("div", { class: "card" }, el("div", { class: "empty" }, e.message))); return; } }
  }
  renderShield(r);
}
function renderShield(r) {
  const out = $("#sh-out"); let lang = "en";
  const head = { danger: ["High risk: do not pay", "Do not pay"], caution: ["Be careful: verify first", ""], none: ["No known scam pattern found", ""] }[r.level][0];
  const body = el("div");
  const draw = () => {
    body.replaceChildren(
      ...(r.reasons.length ? r.reasons.map(x => el("div", { class: "rsn" }, el("div", { lang: lang === "hi" ? "hi" : "en" }, x[lang]), x.seen ? el("div", { class: "seen" }, "matched: " + x.seen) : null)) : [el("div", { class: "note" }, lang === "hi" ? "कोई चेतावनी संकेत नहीं मिला।" : "No warning signs matched.")]),
      el("h4", { style: "margin:14px 0 4px" }, lang === "hi" ? "क्या करें" : "What to do"), el("ul", { class: "acts", lang: lang === "hi" ? "hi" : "en" }, r.actions[lang].map(a => el("li", null, a))));
  };
  const en = el("button", { class: "chip", "aria-pressed": "true", onclick: () => { lang = "en"; en.setAttribute("aria-pressed", true); hi.setAttribute("aria-pressed", false); draw(); } }, "English");
  const hi = el("button", { class: "chip", "aria-pressed": "false", onclick: () => { lang = "hi"; hi.setAttribute("aria-pressed", true); en.setAttribute("aria-pressed", false); draw(); } }, "हिन्दी");
  draw();
  out.replaceChildren(el("div", { class: "card" }, el("div", { class: "body" },
    el("div", { class: "verdict " + r.level }, el("div", { class: "big" }, head), el("div", { class: "note" }, "warning score " + r.score + " / 100" + (r.handles.length ? " · payment handle: " + r.handles.join(", ") : ""))),
    r.owner ? el("div", { class: "note", style: "margin-top:8px" }, "Registered to: " + r.owner + " (from the payment network)") : null,
    r.network ? el("div", { class: "note", style: "margin-top:8px" }, "Risk engine says: " + r.network.fan_in + " first-time senders this week, " + r.network.complaints + " fraud complaint(s) for this payee.") : null,
    el("div", { class: "chips", style: "padding:10px 0 0" }, en, hi), body)));
}
