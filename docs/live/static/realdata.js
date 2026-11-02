/* Real data tab + provenance strips. Everything here talks to /api/realdata. */
const PROV = {
  live: ["sim", "SIMULATED", "These payments come from the simulator (customers like u0187). There is no public stream of real Indian payments. Real public data is on the Real data tab."],
  review: ["sim", "SIMULATED", "Cases come from the simulator. Your confirm or legitimate verdicts are real actions that feed the engine and the audit log."],
  backtest: ["you", "YOUR FILE", "Your uploaded CSV is replayed as-is. The bundled 45-day sample is simulated."],
  redteam: ["sim", "SIMULATED", "An automated attacker against simulated customers. It finds holes in the rules; it does not prove the engine is safe against real fraudsters."],
  real: ["real", "REAL PUBLIC DATA", "Real card transactions and real text messages from public research datasets, fetched from their sources or uploaded by you."],
  shield: ["you", "YOUR INPUT", "Whatever you paste is checked. The buttons below load real messages from public datasets, with their true labels."],
  mules: ["sim", "SIMULATED", "The mule hubs come from the simulator's payee graph. Your confirm or legitimate rulings are real actions."],
  wire: ["real", "REAL (Razorpay TEST MODE)", "Payments arriving from Razorpay's webhook are real test-mode events, signature-checked. The 'Send a Razorpay-shaped payment' form creates a sample event."],
  lab: ["sim", "SIMULATED", "Re-decides a simulated held-out period under the costs you choose."],
  play: ["you", "YOUR INPUT", "A dry run of the payment you compose, against simulated customers' histories. Nothing is remembered."],
  model: ["sim", "SIMULATED", "Accuracy, shapes and the fairness report are on the simulator's held-out period. For real-data results see the Real data tab."],
};
function provStrips() {
  for (const [k, [cls, tag, txt]] of Object.entries(PROV)) {
    const sec = document.getElementById("tab-" + k); if (!sec || sec.querySelector(":scope > .prov")) continue;
    sec.insertBefore(el("div", { class: "prov " + cls }, el("b", null, tag), el("span", null, txt)), sec.firstChild);
  }
}
provStrips();

try { window.FH_KEY = window.FH_KEY || sessionStorage.getItem("fhkey") || ""; } catch (e) {}      // typed by the owner, kept only for this tab session
const RD = { jobs: {}, replay: null };
const fmtN = n => n.toLocaleString("en-IN"), p1 = v => (100 * v).toFixed(1) + "%";
const rdApi = async (u, opt) => {
  const r = await fetch((window.FH_API || "") + u, Object.assign({ headers: hdr() }, opt || {}));
  let j = null; try { j = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error((j && j.detail) || (u + " " + r.status)); return j;
};

async function realTab() {
  if (window.FH_DEMO) { renderDemoReal(); return; }
  let L; try { L = await rdApi("/api/realdata?verify=true"); } catch (e) { $("#rd-list").replaceChildren(el("div", { class: "empty" }, e.message)); return; }
  RD.L = L; $("#rd-note").textContent = "stored in " + L.data_dir;
  $("#rd-list").replaceChildren(keyRow(), ...L.datasets.map(dsCard));
  renderUlb(); renderShieldBench(); renderReplay();
}
function keyRow() {
  const inp = el("input", { type: "password", placeholder: "Server API key (only if you own this server)", autocomplete: "off", value: window.FH_KEY || "", style: "min-width:260px" });
  const b = el("button", { class: "btn sm", onclick: () => { window.FH_KEY = inp.value.trim(); try { sessionStorage.setItem("fhkey", window.FH_KEY); } catch (e) {} realTab(); } }, "Use key");
  return el("div", { class: "note", style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px" }, "Downloads, uploads and benchmarks need the server's API key. It stays in this browser tab only.", inp, b);
}
function dsCard(d) {
  const msg = el("div", { class: "note", role: "status" });
  let st;
  if (!d.present) st = el("span", { class: "st no" }, "NOT ON THE SERVER");
  else if (d.error) st = el("span", { class: "st warn" }, d.error);
  else st = el("span", { class: "st " + (d.verified ? "ok" : "warn") }, (d.verified ? "ON THE SERVER, VERIFIED" : "ON THE SERVER, COUNTS DIFFER FROM THE PUBLISHED DATA") + (d.counts ? " · " + fmtN(d.counts.rows) + " rows" + (d.counts.pos != null ? ", " + d.counts.pos + " fraud" : "") : ""));
  const fetchB = el("button", { class: "btn sm", onclick: async () => { fetchB.disabled = true; msg.textContent = "Downloading from the source…"; try { const j = await rdApi("/api/realdata/" + d.id + "/fetch", { method: "POST" }); await pollJob(j.job, p => { msg.textContent = p.msg || "downloading"; }); msg.textContent = "Done."; realTab(); } catch (e) { msg.textContent = e.message; fetchB.disabled = false; } } }, d.present ? "Download again" : "Download from source");
  const file = el("input", { type: "file", style: "display:none", onchange: async () => {
    const f = file.files[0]; if (!f) return; msg.textContent = "Uploading " + f.name + " (" + (f.size / 1e6).toFixed(1) + " MB)…";
    try { await rdApi("/api/realdata/" + d.id + "/upload", { method: "POST", body: f, headers: hdr({ "content-type": "application/octet-stream" }) }); msg.textContent = "Uploaded and checked."; realTab(); } catch (e) { msg.textContent = e.message; } } });
  const upB = el("button", { class: "btn sm", disabled: !RD.L.uploads, title: RD.L.uploads ? "" : "Uploads are off on this server (set FH_API_KEY or FH_ALLOW_UPLOADS=1)", onclick: () => file.click() }, d.present ? "Replace with my file" : "Upload my own copy");
  return el("div", { class: "ds" }, el("div", { class: "t" }, d.title), st,
    el("div", { class: "sub" }, d.note), el("div", { class: "sub" }, "Source: " + d.source + " · limit " + d.max_mb + " MB"),
    el("div", { class: "act", style: "padding:6px 0 0;gap:6px" }, fetchB, upB, file), msg);
}
async function pollJob(id, on) {
  for (;;) {
    const j = await rdApi("/api/realdata/job/" + id); on && on(j);
    if (j.state === "done") return j.result; if (j.state === "error") throw new Error(j.error);
    await new Promise(r => setTimeout(r, 800));
  }
}
function runBox(host, label, run, ok, render) {
  const bar = el("div", { class: "pbar", hidden: true }, el("i", { style: "width:0" })), msg = el("div", { class: "note", role: "status" }), out = el("div");
  const b = el("button", { class: "btn pri", disabled: !ok, onclick: async () => {
    b.disabled = true; bar.hidden = false; out.replaceChildren(); msg.textContent = "Starting…";
    try { const j = await rdApi(run, { method: "POST" }); const r = await pollJob(j.job, p => { bar.firstChild.style.width = (100 * p.progress) + "%"; msg.textContent = p.msg; }); bar.hidden = true; msg.textContent = ""; out.replaceChildren(render(r)); RD.L.can_replay = RD.L.can_replay || run.endsWith("ulb"); if (run.endsWith("ulb")) renderReplay(); }
    catch (e) { bar.hidden = true; msg.textContent = e.message; } b.disabled = !ok; } }, label);
  host.replaceChildren(b, bar, msg, out);
}
function table(head, rows) { return el("table", { class: "t" }, el("thead", null, el("tr", null, head.map((h, i) => el("th", { class: i ? "r" : "" }, h)))), el("tbody", null, rows.map(r => el("tr", null, r.map((c, i) => el("td", { class: i ? "r" : "" }, c)))))); }
function renderUlb() {
  const d = RD.L.datasets.find(x => x.id === "ulb"), ok = d.present;
  const host = $("#rd-ulb");
  runBox(host, ok ? "Run on the real card-fraud data" : "Download the data (about 144 MB) and run", "/api/realdata/run/ulb", true, r => el("div", null,
    el("div", { class: "note", style: "margin:8px 0" }, fmtN(r.rows) + " real transactions, " + r.fraud + " fraud. " + r.split + ". Test set: " + fmtN(r.test) + " payments with only " + r.test_fraud + " fraud, so the intervals are wide. Took " + r.seconds + " s on this server."),
    table(["Model", "AUC", "Average precision", "95% interval", "Fraud caught at 1% false alarms"], r.models.map(m => [m.name, m.auc.toFixed(3), m.ap.toFixed(3), m.ap_lo.toFixed(3) + " to " + m.ap_hi.toFixed(3), p1(m.rec1)])),
    el("div", { class: "note", style: "margin-top:8px" }, "Recorded earlier with outside baselines (scikit-learn), same split, for context:"),
    table(["Model", "AUC", "Average precision", "95% interval", "Caught at 1%"], RD.L.recorded.ulb_time.map(m => [m[0], m[1].toFixed(3), m[2].toFixed(3), m[3].toFixed(3) + " to " + m[4].toFixed(3), m[5].toFixed(1) + "%"])),
    el("div", { class: "note", style: "margin-top:8px" }, "Read it honestly: the gaps between these models are inside the intervals. This tests the additive model, not the behavioural engine (the data has no customer ids).")));
}
function renderShieldBench() {
  const need = ["smishtank", "uci_sms"].every(i => RD.L.datasets.find(x => x.id === i).present);
  runBox($("#rd-shield"), need ? "Run Scam Shield on the real messages" : "Download the message collections and run", "/api/realdata/run/shield", true, r => el("div", null,
    el("div", { class: "note", style: "margin:8px 0" }, r.rules + " rules; " + r.split + " (seed " + r.seed + ")."),
    table(["Real messages (test half)", "n", "Flagged (caution or higher)", "Rated danger"], r.rows.map(x => [x.group, fmtN(x.n), p1(x.caution), p1(x.danger)])),
    el("div", { class: "note", style: "margin-top:8px" }, "Smishing vs ordinary texts: recall " + p1(r.recall) + ", false-alarm rate " + (100 * r.false_alarm).toFixed(2) + "%, precision " + p1(r.precision) + " on a mix of " + fmtN(r.n_smish) + " smishing and " + fmtN(r.n_ordinary) + " ordinary. Precision depends on how common scams are (see BENCHMARKS.md)."),
    el("div", { class: "note" }, "Before the real data showed what scams look like, the same rules flagged 7.8% of real smishing. Most smishing here is US and English; the Indian-specific rules are not validated on real Indian scam texts.")));
}
function renderReplay(host = $("#rd-replay"), auto = false) {
  if (!RD.L.can_replay) { host.replaceChildren(el("div", { class: "empty" }, "Run section 1 first: it fits the model that scores the replay.")); return; }
  const feed = el("div", { class: "feed", style: "max-height:360px;overflow:auto" }), kp = el("div", { class: "kpis", style: "grid-template-columns:repeat(4,1fr);margin:8px 0" }), msg = el("div", { class: "note", role: "status" });
  let off = 0, timer = null, jump = false;
  const per = el("select", { "aria-label": "Payments per second" }, ...[["6", "slow (about 9 payments a second)"], ["30", "medium (about 40 a second)"], ["150", "fast (about 200 a second)"]].map(([v, t]) => el("option", { value: v }, t)));
  const skip = el("button", { class: "btn", onclick: () => { jump = true; step(); } }, "Jump to the next real fraud");
  const tile = (l, v, s) => el("div", { class: "kpi" }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s));
  const step = async () => {
    try {
      const r = await rdApi("/api/realdata/replay?offset=" + off + "&n=" + per.value + (jump ? "&to_fraud=true" : "")); jump = false; off = r.rows.length ? r.rows[r.rows.length - 1].i + 1 : off;
      for (const x of r.rows) feed.prepend(el("div", { class: "row", style: "grid-template-columns:70px 1fr 90px 90px" },
        el("div", { class: "t" }, "t+" + Math.round(x.t / 60) + "m"), el("div", { class: "m" }, el("div", null, "amount " + x.amt.toFixed(2)), el("div", { class: "sub" }, "model score " + (100 * x.p).toFixed(1) + "%")),
        el("div", null, el("span", { class: "tag " + (x.flag ? "d2" : "d0") }, x.flag ? "Flagged" : "Approved")), el("div", null, el("span", { class: "tag " + (x.fraud ? "fr" : "ok2") }, x.fraud ? "REAL FRAUD" : "genuine"))));
      while (feed.children.length > 80) feed.removeChild(feed.lastChild);
      const k = r.kpi; kp.replaceChildren(tile("Real fraud caught", k.caught + " of " + k.fraud, "so far"), tile("Fraud missed", String(k.missed), "amount " + k.amount_missed.toFixed(0)), tile("Genuine payments flagged", fmtN(k.false_alarms), "of " + fmtN(k.seen - k.fraud) + " genuine"), tile("Amount caught", k.amount_caught.toFixed(0), "of " + k.amount_total.toFixed(0) + " moved"));
      msg.textContent = "Payment " + fmtN(off) + " of " + fmtN(r.total) + ". Threshold " + (100 * r.threshold).toFixed(2) + "% (flags 1% of genuine payments in the validation period). Amounts are in the dataset's own units; the file does not name a currency.";
      if (off >= r.total) stop();
    } catch (e) { msg.textContent = e.message; stop(); }
  };
  const go = el("button", { class: "btn pri", onclick: () => { if (timer) return stop(); go.textContent = "Pause"; timer = setInterval(step, 700); step(); } }, "Start replay");
  const rs = el("button", { class: "btn", onclick: () => { stop(); off = 0; feed.replaceChildren(); kp.replaceChildren(); msg.textContent = ""; } }, "Restart");
  function stop() { clearInterval(timer); timer = null; go.textContent = off ? "Resume" : "Start replay"; }
  if (auto) setTimeout(() => go.click(), 50);
  host.replaceChildren(el("div", { class: "note" }, "The latest 20% of the real two days, in time order, scored by the model you just fitted. Each payment shows what the model said and what actually happened."), el("div", { class: "act", style: "padding:8px 0;gap:8px;align-items:center" }, go, rs, skip, per), kp, msg, feed);
}
function renderDemoReal() {
  const note = "Needs the live backend: it fetches the datasets onto the server and runs the benchmarks there. Recorded results from a real run are below.";
  $("#rd-list").replaceChildren(el("div", { class: "empty" }, note));
  const R = null;
  $("#rd-ulb").replaceChildren(el("div", { class: "note" }, "Recorded on 2026-11-01 on the real ULB card-fraud data (284,807 transactions, 492 fraud; test = the latest 20%, 75 fraud). Same split for every model."),
    table(["Model", "AUC", "Average precision", "95% interval", "Caught at 1% false alarms"], [["Additive model (this project)", "0.980", "0.760", "0.667 to 0.840", "86.7%"], ["Logistic regression (this project)", "0.971", "0.704", "0.600 to 0.792", "86.7%"], ["Logistic regression (scikit-learn)", "0.973", "0.706", "0.609 to 0.792", "86.7%"], ["Random forest (scikit-learn)", "0.941", "0.792", "0.705 to 0.870", "86.7%"], ["Gradient boosting (scikit-learn, untuned)", "0.769", "0.475", "0.360 to 0.592", "70.7%"]]));
  $("#rd-replay").replaceChildren(el("div", { class: "empty" }, note));
  $("#rd-shield").replaceChildren(el("div", { class: "note" }, "Recorded on real messages (test half): 45.3% of 528 real smishing texts flagged (7.8% before real data guided the rules), 0.04% of about 27,200 real ordinary texts falsely flagged, 0.06% of 3,487 real texts sent from India, none of 664 real Indian telecom messages (that last file was used to fix nine false alarms, so it is not held out). Details in docs/BENCHMARKS.md."));
}

/* Live ops on real data: the same replay, shown on the first tab. There is no public stream of real Indian payments, so this is the
   closest honest thing: real card transactions in time order, scored one by one by the model, with what actually happened. */
async function liveReal(host) {
  try { RD.L = await rdApi("/api/realdata"); } catch (e) { host.replaceChildren(el("div", { class: "empty" }, e.message)); return; }
  if (RD.L.can_replay) { renderReplay(host, true); return; }
  const box = el("div");
  runBox(box, "Start the real feed (downloads about 144 MB if needed, fits the model, then replays)", "/api/realdata/run/ulb", true, () => { RD.L.can_replay = true; renderReplay(host, true); return el("span"); });
  host.replaceChildren(el("div", { class: "note", style: "margin-bottom:8px" }, "Real card transactions from two days in September 2013, replayed in time order and scored by the model one at a time. The first start fits the model on the earliest 65% of the file."), keyRow(), box);
}
function liveSource(real) {
  const sim = $$("#tab-live > .live, #tab-live > #kpis");
  sim.forEach(e => { e.hidden = real; });
  $("#real-live").hidden = !real;
  document.body.classList.toggle("realmode", real);                    // the header's simulator controls do nothing to a real file
  $$("#srcbar button").forEach(b => b.setAttribute("aria-pressed", (b.dataset.src === "real") === real));
  const pv = $("#tab-live > .prov");
  if (pv) { pv.className = "prov " + (real ? "real" : "sim"); pv.firstChild.textContent = real ? "REAL PUBLIC DATA" : "SIMULATED"; pv.lastChild.textContent = real ? "Real card transactions (ULB / Worldline, 2013) replayed in time order and scored by the model. They have no customer, device or payee ids, so the behavioural engine, India map and attack types need the simulator." : PROV.live[2]; }
  if (real) liveReal($("#real-live"));
}
