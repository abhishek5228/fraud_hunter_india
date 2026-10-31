/* Tabs: policy lab, playground, model card */
function xyChart(host, o) {
  const W = 430, H = o.h || 250, m = { l: 50, r: 16, t: 10, b: 38 };
  const fx = o.xlog ? Math.log10 : v => v, fy = o.ylog ? Math.log10 : v => v;
  const X = v => m.l + (W - m.l - m.r) * (fx(v) - fx(o.xr[0])) / (fx(o.xr[1]) - fx(o.xr[0]));
  const Y = v => H - m.b - (H - m.t - m.b) * (fy(v) - fy(o.yr[0])) / (fy(o.yr[1]) - fy(o.yr[0]));
  const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.title });
  for (const t of o.yt) s.append(sv("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: "#e6eaf1" }), sv("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end", "font-size": 10.5, fill: "#6b7a90" }, o.yf(t)));
  for (const t of o.xt) s.append(sv("line", { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b, stroke: "#eef1f6" }), sv("text", { x: X(t), y: H - m.b + 15, "text-anchor": "middle", "font-size": 10.5, fill: "#6b7a90" }, o.xf(t)));
  s.append(sv("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle", "font-size": 11, fill: "#3c4d66" }, o.xl), sv("text", { transform: `translate(12 ${(m.t + H - m.b) / 2}) rotate(-90)`, "text-anchor": "middle", "font-size": 11, fill: "#3c4d66" }, o.yl));
  if (o.diag) s.append(sv("line", { x1: X(o.xr[0]), y1: Y(o.xr[0]), x2: X(o.xr[1]), y2: Y(o.xr[1]), stroke: "#9aa8bd", "stroke-width": 1 }));
  const all = [];
  for (const ln of o.lines) {
    const pts = ln.pts.filter(p => p[0] >= o.xr[0] && p[1] >= o.yr[0] && p[1] <= o.yr[1] * 1.0001);
    if (ln.line !== false) s.append(sv("path", { d: pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(""), fill: "none", stroke: ln.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-dasharray": ln.dash || "" }));
    for (const p of pts) { if (ln.dots) s.append(sv("circle", { cx: X(p[0]), cy: Y(p[1]), r: ln.r || 3.5, fill: ln.color, stroke: "#fff", "stroke-width": 1.5 })); all.push({ x: X(p[0]), y: Y(p[1]), p, ln }); }
  }
  const ring = sv("circle", { r: 6, fill: "none", stroke: "#0d1a2d", "stroke-width": 2, visibility: "hidden" });
  const hit = sv("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  hit.addEventListener("pointermove", e => {
    const r = s.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W, py = (e.clientY - r.top) / r.height * H;
    let b = null, bd = 1e9; for (const a of all) { const d = (a.x - px) ** 2 + (a.y - py) ** 2; if (d < bd) { bd = d; b = a; } }
    if (!b) return; ring.setAttribute("cx", b.x); ring.setAttribute("cy", b.y); ring.setAttribute("visibility", "visible");
    showTip(e, b.ln.name, o.tip(b.p, b.ln));
  });
  hit.addEventListener("pointerleave", () => { ring.setAttribute("visibility", "hidden"); hideTip(); });
  s.append(ring, hit);
  host.replaceChildren(s);
  if (o.lines.length > 1) host.append(el("div", { class: "legend" }, o.lines.map(l => el("span", null, el("i", { style: `border-color:${l.color};${l.dash ? "border-top-style:dashed" : ""}` }), l.name))));
}

function tabbing() {
  $$(".tabs button").forEach(b => b.addEventListener("click", () => {
    $$(".tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
    $$(".tab").forEach(t => t.classList.toggle("on", t.id === "tab-" + b.dataset.tab));
    if (b.dataset.tab === "lab") lab(); if (b.dataset.tab === "model") model(); if (b.dataset.tab === "play") play();
    if (b.dataset.tab === "review") review(); if (b.dataset.tab === "backtest") backtestTab(); if (b.dataset.tab === "redteam") redTab(); if (b.dataset.tab === "wire") wireTab(); if (b.dataset.tab === "shield") shieldTab(); if (b.dataset.tab === "mules") mulesTab();
  }));
}

/* ------------------------------------------------------------ mule graph + consortium */
let muSel = null, muT = null, muData = null;
async function mulesTab() {
  if (!muT) muT = setInterval(() => { if ($("#tab-mules").classList.contains("on")) loadMules(); }, 6000);
  loadMules(); consCard();
}
async function loadMules() {
  try { muData = await api("/api/graph"); } catch (e) { $("#mu-list").replaceChildren(el("div", { class: "empty" }, e.message)); return; }
  const cl = muData.clusters;
  $("#mu-count").textContent = muData.total + " found";
  if (!cl.length) { $("#mu-list").replaceChildren(el("div", { class: "empty" }, "No payee has 3 or more first-time senders this week. Launch a 'UPI payee scam' on Live ops.")); $("#mu-svg").replaceChildren(); return; }
  if (!cl.find(c => c.id === muSel)) muSel = cl[0].id;
  $("#mu-list").replaceChildren(...cl.map(c => el("div", { class: "hub" + (c.id === muSel ? " sel" : ""), tabindex: 0, role: "button", onclick: () => { muSel = c.id; loadMules(); }, onkeydown: e => { if (e.key === "Enter") { muSel = c.id; loadMules(); } } },
    el("b", { class: "mono" }, c.payee), el("span", { class: "tag " + (c.level === "high" ? "d2" : "d1") }, c.level === "high" ? "High" : "Watch"),
    el("div", { class: "sub" }, "confidence " + c.confidence + "/100 · " + c.senders + " senders · " + c.complaints + " complaint(s)" + (c.devices.length ? " · " + c.devices.length + " shared device(s)" : "")))));
  drawHub(cl.find(c => c.id === muSel));
}
function drawHub(c) {
  const W = 640, H = 420, cx = W / 2, cy = H / 2, R = 160, ns = "http://www.w3.org/2000/svg", N = c.nodes.length;
  const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Payee " + c.payee + " receives money from " + c.senders + " customers");
  const add = (t, a, txt) => { const e = document.createElementNS(ns, t); for (const k in a) e.setAttribute(k, a[k]); if (txt != null) e.textContent = txt; svg.append(e); return e; };
  const pos = {}; c.nodes.forEach((n, i) => { const a = -Math.PI / 2 + 2 * Math.PI * i / N; pos[n.id] = [cx + R * Math.cos(a), cy + R * 0.85 * Math.sin(a)]; });
  c.devices.forEach((d, k) => { const ids = d.senders.filter(x => pos[x]); for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++)
    add("line", { x1: pos[ids[i]][0], y1: pos[ids[i]][1], x2: pos[ids[j]][0], y2: pos[ids[j]][1], stroke: "#cc2f46", "stroke-width": 1.6, "stroke-dasharray": "4 3" }); });
  c.nodes.forEach(n => add("line", { x1: pos[n.id][0], y1: pos[n.id][1], x2: cx, y2: cy, stroke: n.first ? "#e0a21a" : "#9fb0c9", "stroke-width": n.first ? 2 : 1 }));
  c.nodes.forEach(n => { const [x, y] = pos[n.id]; add("circle", { cx: x, cy: y, r: 11, fill: n.first ? "#fff4d6" : "#eef3f9", stroke: n.first ? "#e0a21a" : "#9fb0c9", "stroke-width": 1.5 }); add("text", { x, y: y + 24, "text-anchor": "middle", "font-size": 10.5, fill: "#5b6b82" }, n.id); });
  add("circle", { cx, cy, r: 30, fill: "#cc2f46" }); add("text", { x: cx, y: cy + 4, "text-anchor": "middle", fill: "#fff", "font-size": 11, "font-weight": 700 }, "payee");
  add("text", { x: cx, y: cy + 50, "text-anchor": "middle", "font-size": 12, "font-weight": 700, fill: "#1b2638" }, c.payee);
  $("#mu-svg").replaceChildren(svg);
  $("#mu-title").textContent = "Who paid " + c.payee;
  $("#mu-why").replaceChildren(el("div", null, el("b", null, "Why it is flagged: "), c.why.join(" · ")), el("div", { class: "note" }, "Amber lines: that sender had never paid this payee before. Red dashed lines: two senders share a device."),
    ...(c.hints || []).map(h => el("div", { class: "note", style: "color:#9a6a00" }, "Note: " + h)),
    el("div", { class: "note" }, "Confidence adds up four independent kinds of evidence (first-time senders, complaints, shared devices, arrival in a burst). It is still a lead, not proof: a charity, a landlord or a popular seller can look like this. Your ruling below is recorded in the audit log."),
    el("div", { class: "act", style: "padding:8px 0 0" }, el("button", { class: "btn bad", onclick: ev => rule(ev, c, "mule") }, "Confirm mule: block this payee"), el("button", { class: "btn", onclick: ev => rule(ev, c, "legit") }, "Known legitimate: stop flagging it"), el("span", { class: "note", id: "mu-msg", role: "status" })));
}
async function rule(ev, c, v) {
  ev.target.disabled = true;
  try { await api("/api/graph/verdict", { id: c.id, verdict: v }); $("#mu-msg").textContent = v === "mule" ? "Recorded. The engine now treats this payee as reported." : "Recorded. It is hidden here and the first-time fan-in rule no longer fires on it."; setTimeout(loadMules, 900); }
  catch (e) { ev.target.disabled = false; $("#mu-msg").textContent = e.message; }
}
async function consCard() {
  const host = $("#mu-cons"); let st;
  try { st = await api("/api/consortium"); } catch (e) { host.replaceChildren(el("div", { class: "note" }, "Needs the live backend.")); return; }
  const msg = el("div", { class: "note", role: "status", style: "margin-top:6px" }), ta = el("textarea", { rows: 3, style: "width:100%;border:1px solid var(--line);border-radius:8px;padding:6px;font:11px var(--mono)", placeholder: "Paste a feed from another bank" });
  host.replaceChildren(
    el("div", { class: "note", style: "line-height:1.55" }, "Two ways for banks to warn each other without sharing customers. Keyed hashes (shared key; simple, but anyone with the key can test guesses) or private set intersection: each bank keeps its own secret and only learns which of ITS OWN payees the other bank flagged. Either way a flagged payee is stopped here before a customer loses money."),
    el("div", { class: "note", style: "margin:6px 0" }, "Private set intersection: " + (st.psi.peers.length ? st.psi.peers.length + " peer(s) configured, " : "no peers configured (FH_PSI_PEERS), ") + st.psi.matched + " payee(s) confirmed. "), el("div", { class: "note", style: "margin:6px 0" }, st.on ? "Key set. " + st.imported + " hash(es) imported from " + (st.banks.join(", ") || "no one yet") + "." : "Off: set FH_CONSORTIUM_KEY on the server."),
    el("button", { class: "btn sm", disabled: !st.on, onclick: async () => { try { const f = await api("/api/consortium/export?bank=this-bank", {}); const a = el("a", { href: URL.createObjectURL(new Blob([JSON.stringify(f, null, 1)], { type: "application/json" })), download: "mule-feed.json" }); a.click(); msg.textContent = "Exported " + f.items.length + " hash(es)."; } catch (e) { msg.textContent = e.message; } } }, "Export my feed"),
    ta, el("button", { class: "btn sm", style: "margin-top:6px", disabled: !st.on, onclick: async () => { try { const r = await api("/api/consortium/import", JSON.parse(ta.value)); msg.textContent = "Imported " + r.new + " new hash(es); " + r.total + " in total."; consCard(); } catch (e) { msg.textContent = e.message; } } }, "Import a feed"), msg);
}

/* ------------------------------------------------------------ fairness (Model card) */
async function fairCard(out) {
  const host = el("div", { class: "card" }, el("h3", null, "Who bears the friction?", el("span", { class: "note sp" }, "legitimate customers challenged or declined, by group")), el("div", { class: "body" }, el("div", { class: "empty" }, "Replaying three days of traffic…")));
  out.append(host);
  let f; try { f = await api("/api/fairness"); } catch (e) { host.lastChild.replaceChildren(el("div", { class: "empty" }, e.message)); return; }
  const mx = Math.max(...f.segments.map(s => s.hi || 0), 0.05);
  const rows = f.segments.map(s => el("tr", { class: s.small ? "mut" : "" }, el("td", null, s.group), el("td", null, s.seg, s.flag ? el("span", { class: "tag d2", style: "margin-left:6px" }, "higher") : null),
    el("td", { class: "r" }, s.n.toLocaleString("en-IN")),
    el("td", { style: "min-width:200px" }, s.touched == null ? "–" : el("div", { style: "display:flex;gap:8px;align-items:center" }, el("div", { class: "hb", style: "flex:1;position:relative" }, el("i", { style: `width:${100 * s.touched / mx}%;background:${s.flag ? "#cc2f46" : "#2b47ff"}` })), el("span", { class: "mono" }, pct(s.touched, 1) + " (" + pct(s.lo, 1) + "–" + pct(s.hi, 1) + ")"))),
    el("td", { class: "r" }, s.ratio == null ? "–" : s.ratio.toFixed(2) + "×"), el("td", { class: "r" }, s.caught == null ? "–" : pct(s.caught, 0))));
  host.lastChild.replaceChildren(el("div", { class: "note", style: "margin-bottom:8px;line-height:1.55" }, "Average: " + pct(f.base, 1) + " of " + f.legit_n.toLocaleString("en-IN") + " legitimate payments were challenged or declined. " + (f.flagged.length ? f.flagged.length + " group(s) are flagged (at least 1.5× average and still significant after correcting for all the groups compared)." : "No group is flagged.") + " " + f.note),
    el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Group"), el("th", null, "Segment"), el("th", { class: "r" }, "Legit payments"), el("th", null, "Challenged or declined (95% interval)"), el("th", { class: "r" }, "vs average"), el("th", { class: "r" }, "Fraud caught"))), el("tbody", null, rows)),
    el("div", { class: "note", style: "margin-top:8px" }, "Greyed rows have too few payments to judge. The simulator has no age, gender or religion, and a real system must not use them as inputs; auditing for them needs those fields joined in afterwards, with a lawful basis."));
}

/* ------------------------------------------------------------ live wire */
let wireT = null, wireBound = false;
const sampleRz = (amt, notes) => ({ event: "payment.captured", payload: { payment: { entity: { id: "pay_" + Math.random().toString(36).slice(2, 10), amount: Math.round(amt * 100), currency: "INR", method: "upi", status: "captured",
  contact: "+9198" + String(Math.floor(Math.random() * 1e8)).padStart(8, "0"), order_id: "order_demo", created_at: Math.floor(Date.now() / 1000), notes } } } });
async function wireTab() {
  if (!wireBound) {
    wireBound = true;
    $("#w-url").textContent = (window.FH_API || location.origin) + "/api/webhook/razorpay";
    const msg = t => { $("#w-msg").textContent = t; };
    $("#w-send").onclick = async () => {
      const n = {}; if ($("#w-ip").value.trim()) n.ip = $("#w-ip").value.trim(); if ($("#w-city").value.trim()) n.city = $("#w-city").value.trim();
      try { const r = await api("/api/webhook/razorpay/replay", sampleRz(+$("#w-amt").value || 1000, n)); msg(r.ignored ? "Ignored: " + r.ignored : r.decision + " (risk " + r.risk + "%) → " + r.action + (r.reasons.length ? " · " + r.reasons.join(", ") : "") + " · location " + r.location); wireLoad(); }
      catch (e) { msg(e.message); }
    };
    $("#w-alert").onclick = async () => { try { const r = await api("/api/alerts/test", {}); msg("Alert test: " + Object.entries(r).map(([k, v]) => k + " " + v).join(", ")); } catch (e) { msg(e.message); } };
    $("#w-llm").onclick = async () => {
      msg("Calling the AI once on a test case…");
      try { const r = await api("/api/llm/check", {}); msg(r.ok ? "AI wording works (" + r.model + "): " + r.text : "AI wording failed (" + r.model + "): " + r.error); } catch (e) { msg(e.message); }
    };
    $("#w-load").onclick = async () => {
      msg("Timing 3,000 payments…");
      try {
        const r = await api("/api/loadtest?n=3000", {}); msg("");
        $("#w-loadcard").hidden = false;
        $("#w-loadout").replaceChildren(el("div", { class: "kpis", style: "grid-template-columns:repeat(3,1fr)" },
          ...[["Throughput", r.per_sec.toLocaleString("en-IN") + "/s", r.n.toLocaleString("en-IN") + " payments in " + r.seconds + " s"], ["Median", (r.p50_us / 1000).toFixed(2) + " ms", "mean " + (r.mean_us / 1000).toFixed(2) + " ms"],
            ["p99", (r.p99_us / 1000).toFixed(2) + " ms", "p95 " + (r.p95_us / 1000).toFixed(2) + " ms · worst " + (r.max_us / 1000).toFixed(1) + " ms"]].map(([l, v, s]) => el("div", { class: "kpi" }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s)))),
          el("div", { class: "note", style: "margin-top:8px" }, r.note));
      } catch (e) { msg(e.message); }
    };
  }
  if (!wireT) wireT = setInterval(() => { if ($("#tab-wire").classList.contains("on")) wireLoad(); }, 3000);
  wireLoad();
}
async function wireLoad() {
  let ig, w;
  try { [ig, w] = await Promise.all([api("/api/integrations"), api("/api/wire")]); } catch (e) { $("#w-status").replaceChildren(el("div", { class: "empty" }, "This tab needs the live backend (" + e.message + ")")); return; }
  const dot = on => el("span", { class: "tag " + (on ? "d0" : "d1"), style: "min-width:44px;text-align:center" }, on ? "ON" : "OFF");
  const row = (n, on, d) => el("div", { style: "display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)" }, dot(on), el("div", null, el("b", null, n), el("div", { class: "sub" }, d)));
  $("#w-status").replaceChildren(
    row("Razorpay webhook", ig.razorpay.on, ig.razorpay.on ? ig.razorpay.ok + " scored · " + ig.razorpay.bad_sig + " rejected (bad signature) · " + ig.razorpay.ignored + " ignored" : "set RAZORPAY_WEBHOOK_SECRET on the server"),
    row("IP intelligence (ipinfo.io)", ig.ipinfo.on, ig.ipinfo.on ? ig.ipinfo.cached + " IPs cached · " + ig.ipinfo.errors + " lookup errors" : "set IPINFO_TOKEN: real IP → city + VPN / data-centre detection"),
    row("Alerts", ig.alerts.channels.length > 0, ig.alerts.channels.length ? ig.alerts.channels.join(" + ") + " · " + ig.alerts.sent + " sent · " + ig.alerts.dropped + " rate-limited · " + ig.alerts.failed + " failed" : "set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID, or SLACK_WEBHOOK_URL"),
    row("AI wording for analyst briefs (optional)", ig.llm.on, ig.llm.on ? "model " + ig.llm.model + " · facts only, no customer data" : "set ANTHROPIC_API_KEY; briefs use plain templates without it"),
    row("API key on scoring endpoints", ig.auth, ig.auth ? "X-API-Key required" : "open (set FH_API_KEY before going public)"));
  $("#w-list").replaceChildren(...(w.events.length ? w.events.map(e => el("div", { class: "row", style: "grid-template-columns:62px 1fr 84px 74px" },
    el("div", { class: "t" }, stime(e.t)),
    el("div", { class: "m" }, el("div", null, el("b", null, e.method || e.chan), " · ", e.uid), el("div", { class: "sub" }, (e.codes.join(", ") || e.why) + (e.anon ? " · VPN/proxy network" : "") + " · " + e.us + " µs")),
    el("div", { class: "a" }, money(e.amt, 0)), el("div", { style: "text-align:right" }, el("span", { class: "tag d" + e.dec }, DN[e.dec])))) : [el("div", { class: "empty" }, "No webhook payments yet. Send one on the left.")]));
}

/* ------------------------------------------------------------ review queue */
let revT = null, revSel = null;
async function review() {
  if (!revT) revT = setInterval(() => { if ($("#tab-review").classList.contains("on")) loadQueue(); }, 5000);
  loadQueue();
}
async function loadQueue() {
  let q; try { q = await api("/api/queue"); } catch (e) { $("#rlist").replaceChildren(el("div", { class: "empty" }, e.message)); return; }
  $("#rcount").textContent = q.open + " open";
  const rows = q.cases.map(c => {
    const r = el("div", { class: "row" + (revSel === c.id ? " sel" : ""), tabindex: 0, role: "button", style: "grid-template-columns:54px 1fr 70px 74px" },
      el("div", { class: "t" }, stime(c.ts)),
      el("div", { class: "m" }, el("div", null, el("b", null, c.cat.replace("_", " ")), " · ", c.uid), el("div", { class: "sub" }, (RAILN[c.chan] || c.chan) + " · " + c.city + (c.hits[0] ? " · " + c.hits[0] : ""))),
      el("div", { class: "a" }, money(c.amt, c.amt < 100 ? 2 : 0)), el("div", { style: "text-align:right" }, el("span", { class: "tag d" + c.dec }, DN[c.dec])));
    const go = async () => { revSel = c.id; $$("#rlist .row").forEach(x => x.classList.remove("sel")); r.classList.add("sel"); await openCase(c.id); };
    r.addEventListener("click", go); r.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
    return r;
  });
  $("#rlist").replaceChildren(...(rows.length ? rows : [el("div", { class: "empty" }, "Nothing waiting. Launch an attack on the Live ops tab to see cases arrive.")]));
}
async function openCase(id) {
  try {
    if (!S.cfg) S.cfg = await api("/api/policy");
    renderCase($("#rinsp"), await api("/api/case/" + id), S.cfg, { actions: true, onDone: () => { revSel = null; setTimeout(() => { loadQueue(); $("#rinsp").replaceChildren(el("div", { class: "empty" }, "Recorded. Pick the next payment.")); }, 700); } });
  } catch (e) { $("#rinsp").replaceChildren(el("div", { class: "empty" }, "That case has aged out of the engine's recent-case window.")); }
}

/* ------------------------------------------------------------ backtest */
let btId = null, btBound = false;
function backtestTab() {
  if (btBound) return; btBound = true;
  const demo = !!window.FH_DEMO;
  if (demo) { $("#bt-file").disabled = true; $("#bt-run").disabled = true; $("#bt-status").textContent = "Demo mode: uploads need the backend. The sample report below was recorded from the real engine."; }
  $("#bt-sample").onclick = () => runBt(null);
  $("#bt-run").onclick = () => { const f = $("#bt-file").files[0]; if (!f) { $("#bt-status").textContent = "Choose a CSV file first."; return; } runBt(f); };
  if (demo) runBt(null);
}
async function runBt(file) {
  const st = $("#bt-status"); st.textContent = file ? "Reading " + file.name + "…" : "Running the sample (about 10 seconds)…";
  $("#bt-out").style.opacity = 0.5;
  try {
    let r;
    if (file) {
      const txt = await file.text(); st.textContent = "Replaying " + (txt.split("\n").length - 1).toLocaleString("en-IN") + " rows…";
      const resp = await fetch((window.FH_API || "") + "/api/backtest", { method: "POST", headers: hdr({ "content-type": "text/csv" }), body: txt });
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || "Backtest failed (" + resp.status + ")");
      r = await resp.json();
    } else r = await api("/api/backtest/sample");
    btId = r.id; st.textContent = "Done in " + r.seconds + " s."; renderBt(r);
  } catch (e) { st.textContent = e.message; }
  $("#bt-out").style.opacity = 1;
}
function renderBt(r) {
  const out = $("#bt-out"), d = r.decisions, lab = r.labelled, I = r.impact, c = I && I.cur;
  const tile = (l, v, s, k) => el("div", { class: "kpi " + (k || "") }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s));
  const tiles = lab ? el("div", { class: "big" },
    tile("Net saving vs. approving everything", mk(I.allow.cost - c.cost), `cost ${mk(c.cost)} against ${mk(I.allow.cost)}`, "good"),
    tile("Fraud caught", pct(c.caught, 1), `${mk(r.fraud_amount - c.leak)} of ${mk(r.fraud_amount)} stopped · ${c.bps.toFixed(1)} bps leaks`, ""),
    tile("Good customers touched", pct(c.touched, 2), `${pct(c.declined_legit, 2)} declined outright`, c.touched > 0.05 ? "warn" : ""),
    tile("Ranking quality", "AUC " + (r.auc || 0).toFixed(3), `average precision ${(r.ap || 0).toFixed(3)} · ${r.fraud_n} fraud`, "")) :
    el("div", { class: "big" }, tile("Payments scored", r.scored.toLocaleString("en-IN"), `${r.warm.toLocaleString("en-IN")} used as warm-up`, ""),
      tile("Approved", pct(d.approve / r.scored, 1), `${d.approve.toLocaleString("en-IN")} payments`, ""), tile("Challenged", pct(d.step / r.scored, 1), `${d.step.toLocaleString("en-IN")} payments`, "warn"),
      tile("Declined", pct(d.decline / r.scored, 1), `${mk(r.flagged_amount)} flagged in total`, "bad"));
  const kids = [tiles];
  if (r.warnings && r.warnings.length) kids.push(el("div", { class: "card" }, el("div", { class: "body" }, r.warnings.map(w => el("div", { class: "truth warn", style: "margin:0 0 6px" }, w)))));
  if (r.problems && r.problems.length) kids.push(el("div", { class: "card" }, el("h3", null, "Rows that were skipped or adjusted"), el("div", { class: "body note" }, r.problems.map(p => el("div", null, p)))));
  if (lab) {
    const bars = [["This engine", c.cost, "#2b47ff"], ["Best single threshold (picked with hindsight)", I.best1.cost, "#9aa8bd"], ["Untuned: decline above 50%", I.naive.cost, "#c3ccdb"], ["Approve everything", I.allow.cost, "#c3ccdb"]];
    const mx = Math.max(...bars.map(b => b[1])), cb = el("div", { class: "econ", style: "grid-template-columns:270px 1fr 80px" });
    bars.forEach(([n, v, col], i) => cb.append(el("div", { class: i === 0 ? "pick" : "" }, el("span", { class: i === 0 ? "nm" : "" }, n)), el("div", { class: "bar" }, el("i", { style: `width:${100 * v / mx}%;background:${col}` })), el("div", { class: "v" }, mk(v))));
    kids.push(el("div", { class: "card" }, el("h3", null, "What it would have cost", el("span", { class: "note sp" }, `${r.scored.toLocaleString("en-IN")} payments after a ${r.warmup_days}-day warm-up`)),
      el("div", { class: "body" }, cb, el("div", { class: "note", style: "margin-top:8px" }, "Cost = fraud rupees that got through + fixed fraud fees + sales and goodwill lost to declines and abandoned challenges + the cost of each challenge. The single threshold was tuned on this same file, which flatters it."))));
  }
  const rail = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Rail"), el("th", { class: "r" }, "Payments"), lab ? el("th", { class: "r" }, "Fraud") : null, lab ? el("th", { class: "r" }, "Caught") : null, el("th", { class: "r" }, lab ? "Good touched" : "Flagged"))),
    el("tbody", null, r.by_rail.map(x => el("tr", null, el("td", null, RAILN[x.rail] || x.rail), el("td", { class: "r" }, x.n.toLocaleString("en-IN")), lab ? el("td", { class: "r" }, x.fraud) : null, lab ? el("td", { class: "r" }, x.fraud ? pct(x.caught, 0) : "–") : null, el("td", { class: "r" }, pct(lab ? x.touched : x.flagged, 1))))));
  const rs = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Reason"), el("th", { class: "r" }, "Flagged"), lab ? el("th", null, "Actually fraud") : null, lab ? el("th", { class: "r" }, "") : null)),
    el("tbody", null, r.reasons.map(x => el("tr", null, el("td", { class: "mono" }, x.code === "MODEL_ONLY" ? "model score only" : x.code), el("td", { class: "r" }, x.n.toLocaleString("en-IN")), lab ? el("td", null, hbar(x.fraud_share, true)) : null, lab ? el("td", { class: "r" }, pct(x.fraud_share, 0)) : null))));
  kids.push(el("div", { class: "grid2" }, el("div", { class: "card" }, el("h3", null, "By payment rail"), el("div", { class: "body" }, rail)),
    el("div", { class: "card" }, el("h3", null, "Why payments were flagged", el("span", { class: "note sp" }, lab ? "a low 'actually fraud' bar is a false-alarm source" : "")), el("div", { class: "body" }, rs))));
  const top = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Line"), el("th", null, "Customer"), el("th", null, "Rail"), el("th", { class: "r" }, "Amount"), el("th", { class: "r" }, "Risk"), el("th", null, "Decision"), el("th", null, "Reason"), lab ? el("th", null, "Truth") : null)),
    el("tbody", null, r.top_rows.map(x => el("tr", null, el("td", { class: "mono" }, x.line), el("td", { class: "mono" }, x.uid), el("td", null, RAILN[x.chan] || x.chan), el("td", { class: "r" }, money(x.amt, x.amt < 100 ? 2 : 0)), el("td", { class: "r" }, pr(x.p)),
      el("td", null, el("span", { class: "tag d" + x.dec }, DN[x.dec])), el("td", { class: "mono" }, x.codes[0] || "model"), lab ? el("td", null, x.label === 1 ? "fraud" : x.label === 0 ? "good" : "") : null))));
  const dl = !window.FH_DEMO ? el("button", { class: "btn sm sp", onclick: downloadBt }, "Download every decision (CSV)") : null;
  kids.push(el("div", { class: "card" }, el("h3", null, "The 15 riskiest payments", dl), el("div", { class: "body" }, top)));
  kids.push(el("div", { class: "note", style: "padding:0 4px" }, `Model ${r.model} · ${r.model_note}. Replayed in an isolated copy of the engine, nothing live was changed.`));
  out.replaceChildren(...kids);
}
async function downloadBt() {
  const resp = await fetch((window.FH_API || "") + "/api/backtest/" + btId + "/csv", { headers: hdr() });
  if (!resp.ok) { $("#bt-status").textContent = "That result has expired; run the backtest again."; return; }
  const a = el("a", { href: URL.createObjectURL(await resp.blob()), download: "decisions-" + btId + ".csv" }); document.body.append(a); a.click(); a.remove();
}

/* ------------------------------------------------------------ red team */
let rtBound = false, rtRounds = null;
async function redTab() {
  if (rtBound) return; rtBound = true;
  $("#rt-run").onclick = runRt;
  try { rtRounds = await api("/api/redteam/rounds"); } catch (e) { rtRounds = null; }
  if (window.FH_DEMO) { $("#rt-status").textContent = "Demo mode: showing the run recorded from the real engine."; }
  runRt();
}
async function runRt() {
  const st = $("#rt-status"); if (!window.FH_DEMO) st.textContent = "Attacking (about 10 seconds)…"; $("#rt-out").style.opacity = 0.5;
  try { const r = await api("/api/redteam/run", { seed: 1 + Math.floor(Math.random() * 1000) }); if (!window.FH_DEMO) st.textContent = `Tried ${r.evaluated.toLocaleString("en-IN")} attacks on ${r.victims} customers in ${r.seconds} s.`; renderRt(r); }
  catch (e) { st.textContent = e.message; }
  $("#rt-out").style.opacity = 1;
}
function lvLabel(lv, v) {
  if (lv === "gap") { const n = +v; return n < 60 ? n + " s" : n < 3600 ? n / 60 + " min" : n / 3600 + " h"; }
  if (lv === "mult") return +v === 0 ? "just under the limit" : "total x" + v;
  if (lv === "n") return v + (+v === 1 ? " payment" : " payments");
  if (lv === "rat" || lv === "sim" || lv === "social") return +v ? "yes" : "no";
  return ({ pool: "mule account", fresh: "brand-new account", merchant: "gift-card shop", contact: "saved contact", own: "victim's phone", new: "new phone", equal: "equal parts", random: "uneven parts", limit: "just under limit" }[v]) || v;
}
function renderRt(r) {
  const tile = (l, v, s, k) => el("div", { class: "kpi " + (k || "") }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s));
  const t0 = r.top[0], kids = [];
  kids.push(el("div", { class: "big" },
    tile("Best attack: expected haul", mk(r.best), `per customer, whose usual ticket is about ${money(r.mean_ticket)}`, "bad"),
    tile("Share of the attempt that lands", pct(t0.share, 0), t0.share >= 0.75 ? "nearly all of it gets through" : t0.share >= 0.4 ? "a large share gets through" : "a minority gets through", t0.share >= 0.4 ? "bad" : "warn"),
    tile("Customers where it is caught", pct(r.best_caught, 0), "attack stopped before most of the money moved", r.best_caught > 0.5 ? "good" : "bad"),
    tile("Strategies tried", r.evaluated.toLocaleString("en-IN"), `${r.curve.length} generations of evolution; each strategy tried on several customers`, "")));
  const cv = el("div", { class: "chart" });
  kids.push(el("div", { class: "card" }, el("h3", null, "How fast the attacker learns", el("span", { class: "note sp" }, "random guesses start near zero")), el("div", { class: "body" }, cv)));
  const tb = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Strategy"), el("th", { class: "r" }, "Haul"), el("th", { class: "r" }, "Lands"), el("th", { class: "r" }, "Caught"))),
    el("tbody", null, r.top.slice(0, 6).map(t => el("tr", null, el("td", { style: "max-width:520px;line-height:1.45" }, t.text), el("td", { class: "r" }, mk(t.extracted)), el("td", { class: "r" }, pct(t.share, 0)), el("td", { class: "r" }, pct(t.caught, 0))))));
  kids.push(el("div", { class: "card" }, el("h3", null, "The best strategies it found", el("span", { class: "note sp" }, "checked on 40 customers the search never saw")), el("div", { class: "body" }, tb)));
  const mx = Math.max(...r.levers.slice(0, 6).flatMap(l => l.rows.map(x => x.mean)), 1);
  const lv = el("div", { class: "grid2" }, r.levers.slice(0, 6).map(l => el("div", null, el("div", { style: "font-weight:600;margin-bottom:4px" }, ({ split: "How the money is split", gap: "Time between payments", mult: "Total vs. usual ticket", n: "Number of payments", ip: "Network", payee: "Who is paid", rail: "Rail", dev: "Device", hour: "Hour of day", rat: "Screen-share visible", sim: "Just swapped SIM", social: "Customer approves the challenge" }[l.lever] || l.lever)),
    el("div", { class: "econ", style: "grid-template-columns:120px 1fr 62px" }, l.rows.flatMap(x => [el("div", { class: "mono", style: "font-size:11.5px" }, lvLabel(l.lever, x.v)), el("div", { class: "bar" }, el("i", { style: `width:${Math.max(1, 100 * x.mean / mx)}%;background:#7c8dff` })), el("div", { class: "v" }, mk(x.mean))])))));
  kids.push(el("div", { class: "card" }, el("h3", null, "What helps an attacker most", el("span", { class: "note sp" }, "average haul of every attack that used each setting")), el("div", { class: "body" }, lv)));
  const hd = el("div", { id: "rt-harden" });
  kids.push(el("div", { class: "card" }, el("h3", null, "Closing the holes, and what it costs", el("span", { class: "note sp" }, "recorded: attack, train on what worked, attack again; median of 3 searches")), el("div", { class: "body" }, hd)));
  $("#rt-out").replaceChildren(...kids);
  lineChart(cv, { title: "attacker learning curve", x: r.curve.map(c => c.gen + 1), xfmt: v => "gen " + v, yfmt: v => mk(v), w: 640, h: 200, endLabels: true,
    series: [{ name: "Best attack in the generation", short: "best", color: "#cc2f46", y: r.curve.map(c => c.best) }, { name: "Average attack", short: "average", color: "#9aa8bd", y: r.curve.map(c => c.mean) }] });
  renderHarden(hd);
}
function renderHarden(h) {
  if (!rtRounds) { h.append(el("div", { class: "empty" }, "No recorded hardening run in this deployment. Run `python -m fh.redteam --harden 3`.")); return; }
  const R = rtRounds.rounds, g = x => x.regular || {}, mx = Math.max(...R.map(r => r.best));
  const tb = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Round"), el("th", null, "Attacker's best haul per customer"), el("th", { class: "r" }, "Accuracy (AP)"), el("th", { class: "r" }, "Fraud caught"), el("th", { class: "r" }, "Good customers touched"))),
    el("tbody", null, R.map((r, i) => el("tr", null, el("td", null, i === 0 ? "0  (shipped)" : String(i)), el("td", null, el("div", { style: "display:flex;gap:8px;align-items:center" }, el("div", { class: "hb", style: "flex:1" }, el("i", { style: `width:${100 * r.best / mx}%;background:${i === 0 ? "#cc2f46" : "#2b47ff"}` })), el("b", { class: "mono", style: "min-width:64px;text-align:right" }, mk(r.best)), el("span", { class: "note", style: "min-width:120px" }, r.best_min != null ? `(${mk(r.best_min)} to ${mk(r.best_max)})` : ""))),
      el("td", { class: "r" }, g(r).ap ? g(r).ap.toFixed(3) : "–"), el("td", { class: "r" }, g(r).caught ? pct(g(r).caught, 1) : "–"), el("td", { class: "r" }, g(r).touched ? pct(g(r).touched, 1) : "–")))));
  const a = R[0], b = R[1], later = R.slice(2), z = R[R.length - 1], dT = (g(b).touched - g(a).touched) * 100, dA = g(b).ap - g(a).ap;
  const acc = Math.abs(dA) < 0.005 ? "no real change in accuracy" : `accuracy ${dA < 0 ? "down" : "up"} ${Math.abs(dA).toFixed(3)}`;
  const improving = later.every((r, i) => r.best <= (i ? later[i - 1].best : b.best) * 0.8);
  h.append(tb, el("div", { class: "note", style: "margin-top:10px;line-height:1.65" },
    el("div", null, `Training on what round 0 found cut the attacker's median haul from ${mk(a.best)} to ${mk(b.best)} (${pct(1 - b.best / a.best, 0)} less), with ${acc} and ${Math.abs(dT).toFixed(1)} points ${dT >= 0 ? "more" : "less"} friction on good customers.`),
    el("div", { style: "margin-top:6px" }, `It is narrowed, not closed: the best of three searches still found ${mk(b.best_max)} against round 1. A single run would have understated that.`),
    later.length ? el("div", { style: "margin-top:6px" }, `Later rounds end at ${later.map(r => mk(r.best)).join(" and ")} (worst searches ${later.map(r => mk(r.best_max)).join(" and ")}). ${improving ? "They keep improving" : "They do not improve reliably"}, while friction reaches ${pct(g(z).touched, 1)} and accuracy ${g(z).ap.toFixed(3)}. Each patch closes the holes it was shown and the next search finds different ones.`) : null));
}

/* ------------------------------------------------------------ policy lab */
const SL = [
  ["risk", "Risk aversion", "How much a fraud rupee weighs against friction. 1.0 is neutral.", -1, 1, 0.05, v => "×" + Math.pow(10, v).toFixed(2), v => Math.pow(10, v)],
  ["fee", "Fixed cost per fraud", "Complaint handling, reversal operations and disputes, on top of the lost amount.", 0, 3000, 50, v => money(+v), v => v],
  ["churn", "Cost of declining a good customer", "Support contact and the chance they move their payments to another app.", 0, 2000, 25, v => money(+v), v => v],
  ["step", "Cost of a step-up challenge", "PIN or OTP re-entry, plus the friction of making someone wait.", 0, 100, 1, v => money(+v), v => v],
  ["marg", "Margin on a card payment", "Card payments earn this. UPI to a person, IMPS and ATM earn none; UPI to a merchant above ₹2,000 earns 0.4% (NPCI, from 15 Oct 2026).", 0, 0.05, 0.001, v => (100 * v).toFixed(1) + "%", v => v],
  ["lpass", "Good customers who pass a challenge", "The rest abandon the payment.", 0.7, 1, 0.01, v => (100 * v).toFixed(0) + "%", v => v],
  ["fpass", "Fraudsters assumed to pass a challenge", "The model's assumption. The live simulator shows how wrong it is for SIM swaps and scams.", 0, 0.5, 0.01, v => (100 * v).toFixed(0) + "%", v => v],
];
let LABV = null, DEF = null, labT = 0;
async function lab() {
  if (!LABV) {
    const base = await api("/api/policy"); DEF = { ...base }; LABV = { ...base };
    const h = $("#sliders");
    const DM = window.FH_DEMO ? { risk: [-0.602, 0.602, 0.301], churn: [150, 1000, 25], step: [5, 40, 1] } : null;   // recorded grid
    for (const [k, name, desc, mn0, mx0, st0, fmt, inv] of SL) {
      const dm = DM && DM[k], mn = dm ? dm[0] : mn0, mx = dm ? dm[1] : mx0, st = dm ? dm[2] : st0;
      const init = k === "risk" ? Math.log10(base[k]) : base[k];
      const o = el("output", { id: "o-" + k }, fmt(init));
      const inp = el("input", { type: "range", id: "s-" + k, min: mn, max: mx, step: st, value: init, "aria-label": name, disabled: DM && !dm ? "" : null });
      inp.addEventListener("input", () => { o.textContent = fmt(+inp.value); LABV[k] = inv(+inp.value); clearTimeout(labT); labT = setTimeout(runLab, 90); });
      h.append(el("div", { class: "sl" }, el("label", { for: "s-" + k }, name), o, inp, el("div", { class: "d" }, desc)));
    }
    if (DM) h.append(el("div", { class: "note" }, "Demo mode: risk aversion, churn cost and challenge cost snap to 45 recorded settings. Fee, margin and pass rates are fixed. Run the backend for full control."));
    $("#apply").onclick = async () => { await api("/api/policy", LABV); S.cfg = null; $("#apply").textContent = "Applied. Live decisions now use these costs"; setTimeout(() => ($("#apply").textContent = "Apply to live engine"), 2500); };
    $("#resetcfg").onclick = () => { LABV = { ...DEF }; for (const [k, , , , , , fmt] of SL) { const v = k === "risk" ? Math.log10(DEF[k]) : DEF[k]; $("#s-" + k).value = v; $("#o-" + k).textContent = fmt(v); } runLab(); };
  }
  runLab();
}
const hbar = (v, good) => el("div", { class: "hb" }, el("i", { style: `width:${100 * v}%;background:${good ? (v > .85 ? "#0f8a66" : v > .6 ? "#e0a21a" : "#cc2f46") : (v < .05 ? "#0f8a66" : v < .3 ? "#e0a21a" : "#cc2f46")}` }));
async function runLab() {
  const r = await api("/api/policy/lab", LABV), out = $("#labout"), c = r.cur;
  const vs2 = 1 - c.cost / r.best2.cost, vs1 = 1 - c.cost / r.best1.cost;
  const tile = (l, v, s, k) => el("div", { class: "kpi " + (k || "") }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s));
  const big = el("div", { class: "big" },
    tile("Total cost, held-out 12 days", mk(c.cost), `${vs2 >= 0 ? pct(vs2, 0) + " below" : pct(-vs2, 0) + " above"} the best tuned step-up and decline thresholds`, vs2 > 0 ? "good" : "bad"),
    tile("Fraud caught", pct(c.caught, 1), `${c.bps.toFixed(1)} bps of volume still leaks`, ""),
    tile("Good customers touched", pct(c.touched, 2), `${pct(c.declined_legit, 2)} declined outright`, c.touched > 0.05 ? "warn" : ""),
    tile("Decisions", `${pct(c.approve, 1)} approve`, `${pct(c.step, 1)} step-up · ${pct(c.decline, 1)} decline`, ""));
  const bars = [["This policy (amount-aware)", c.cost, "#2b47ff"], ["Best tuned step-up and decline thresholds", r.best2.cost, "#9aa8bd"], ["Best tuned single threshold", r.best1.cost, "#9aa8bd"], ["Untuned: decline above 50%", r.naive.cost, "#c3ccdb"], ["Hard rules only", r.rules.cost, "#c3ccdb"], ["Approve everything", r.allow.cost, "#c3ccdb"]];
  const mx = Math.max(...bars.map(b => b[1]));
  const cb = el("div", { class: "econ", style: "grid-template-columns:260px 1fr 80px" });
  bars.forEach(([n, v, col], i) => cb.append(el("div", { class: i === 0 ? "pick" : "" }, el("span", { class: i === 0 ? "nm" : "" }, n)), el("div", { class: "bar" }, el("i", { style: `width:${100 * v / mx}%;background:${col}` })), el("div", { class: "v" }, mk(v))));
  const fr = el("div", { class: "chart" }), cr = el("div", { class: "chart" });
  const grid2 = el("div", { class: "grid2" },
    el("div", { class: "card" }, el("h3", null, "Fraud leaked vs. customers touched", el("span", { class: "note sp" }, "each point is a risk-aversion setting")), el("div", { class: "body" }, fr)),
    el("div", { class: "card" }, el("h3", null, "Total cost vs. risk aversion", el("span", { class: "note sp" }, "the valley is the best trade")), el("div", { class: "body" }, cr)));
  const cell = x => `${pr(x.step)} / ${pr(x.decline)}`;
  const thr = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Payment"), el("th", { class: "r" }, "UPI to person"), el("th", { class: "r" }, "UPI to merchant"), el("th", { class: "r" }, "Card"))),
    el("tbody", null, r.thr.map(t => el("tr", null, el("td", null, money(t.amt)), el("td", { class: "r" }, cell(t.upi_p2p)), el("td", { class: "r" }, cell(t.upi_m)), el("td", { class: "r" }, cell(t.card))))));
  const rails = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Rail"), el("th", { class: "r" }, "Payments"), el("th", { class: "r" }, "Fraud"), el("th", { class: "r" }, "Caught"), el("th", { class: "r" }, "Good touched"))),
    el("tbody", null, Object.entries(r.rails).sort((a, b) => b[1].n - a[1].n).map(([k, v]) => el("tr", null, el("td", null, RAILN[k] || k), el("td", { class: "r" }, v.n.toLocaleString("en-IN")), el("td", { class: "r" }, v.fraud), el("td", { class: "r" }, v.fraud ? pct(v.caught, 0) : "–"), el("td", { class: "r" }, pct(v.touched, 1))))));
  const fraudT = Object.entries(r.typ).filter(([, v]) => v.fraud), legitT = Object.entries(r.typ).filter(([, v]) => !v.fraud);
  const nm = k => TYPN[k] || ({ newpayee: "paying a new person", newphone: "new phone or reinstall", kiosk: "shared kiosk phone", screenshare: "screen-share for IT help", vpn: "VPN user", trip: "travelling", bigbuy: "big purchase", rent: "monthly rent", burst: "quick follow-up", micro: "₹1 to ₹20 UPI", legit: "ordinary payments" }[k] || k);
  const tt = (rows, good) => el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, ""), el("th", { class: "r" }, "n"), el("th", null, "Flagged"), el("th", { class: "r" }, ""))),
    el("tbody", null, rows.sort((a, b) => b[1].flagged - a[1].flagged).map(([k, v]) => el("tr", null, el("td", null, nm(k)), el("td", { class: "r" }, v.n.toLocaleString("en-IN")), el("td", null, hbar(v.flagged, good)), el("td", { class: "r" }, pct(v.flagged, 0))))));
  out.replaceChildren(big,
    el("div", { class: "card" }, el("h3", null, "What each approach costs on the same 12 days"), el("div", { class: "body" }, cb, el("div", { class: "note", style: "margin-top:8px" }, "Cost = fraud rupees that got through + fixed fraud fees + margin and goodwill lost to declines and abandoned challenges + the cost of every challenge issued. The tuned baselines were fitted on this very period, which flatters them."))),
    grid2,
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", null, "The bar moves with the stakes and the rail", el("span", { class: "note sp" }, "risk where step-up / decline begin")), el("div", { class: "body" }, thr, el("div", { class: "note", style: "margin-top:8px" }, "A ₹100 payment is waved through at risk levels where a ₹50,000 one would be challenged. Rails that earn no margin are cheaper to decline, so they are challenged slightly earlier than card payments of the same size."))),
      el("div", { class: "card" }, el("h3", null, "By payment rail", el("span", { class: "note sp" }, "held-out period")), el("div", { class: "body" }, rails))),
    el("div", { class: "card" }, el("h3", null, "Fraud types and their lookalikes", el("span", { class: "note sp" }, "held-out period")), el("div", { class: "body" },
      el("div", { class: "grid2" }, el("div", null, el("div", { class: "note" }, "Fraud: higher is better"), tt(fraudT, true)), el("div", null, el("div", { class: "note" }, "Legitimate lookalikes: lower is better"), tt(legitT, false))))));
  const F = r.front;
  xyChart(fr, { title: "frontier", h: 250, xr: [0, Math.max(0.1, ...F.map(f => f.touched)) * 1.05], yr: [0, Math.max(...F.map(f => f.bps)) * 1.08], xt: [0, .02, .04, .06, .08, .1], yt: [0, 10, 20, 30, 40, 50], xf: v => pct(v, 0), yf: v => v, xl: "Good customers touched", yl: "Fraud leaked (bps of volume)",
    lines: [{ name: "Risk-aversion sweep", color: "#9aa8bd", pts: F.map(f => [f.touched, f.bps, f.risk]), dots: true, r: 3 }, { name: "Current setting", color: "#2b47ff", line: false, dots: true, r: 6, pts: [[c.touched, c.bps, LABV.risk]] }],
    tip: (p, l) => [{ v: pct(p[0], 2), l: "good customers touched" }, { v: p[1].toFixed(1) + " bps", l: "fraud leaked" }, { v: "×" + p[2].toFixed(2), l: "risk aversion" }] });
  lineChart(cr, { title: "cost vs risk", x: F.map(f => f.risk), xfmt: v => "×" + v.toFixed(2), yfmt: v => mk(v), w: 430, h: 250, series: [{ name: "Total cost", color: "#2b47ff", y: F.map(f => f.cost) }] });
}

/* ------------------------------------------------------------ playground */
let PU = [], PM = null;
async function play() {
  if (PM) return;
  PM = await api("/api/meta"); PU = await api("/api/users?n=14");
  S.cfg = PM.cfg;
  $("#p-uid").append(...PU.map(u => el("option", { value: u.uid }, `${u.uid} · ${u.city} · typical ${money(u.typ)}`)));
  $("#p-cat").append(...PM.cats.filter(c => !["p2p", "bank_transfer", "atm_cash"].includes(c)).map(c => el("option", { value: c, selected: c === "digital" ? "" : null }, c.replace("_", " "))));
  $("#p-city").append(el("option", { value: "" }, "Customer's home city"), ...PM.cities.map((c, i) => el("option", { value: c }, c + (i >= PM.nin ? " (abroad)" : ""))));
  $("#p-go").onclick = () => playGo();
  if (window.FH_DEMO) {
    $$("#tab-play .fm select, #tab-play .fm input, #p-go").forEach(e => (e.disabled = true));
    $("#p-go").parentElement.replaceChildren($("#p-go"), el("span", { class: "note", style: "align-self:center" }, "Free-form scoring needs the backend. The scenarios below replay real recorded runs."));
  }
  const sc = [
    ["Chai and groceries", "₹180 UPI payment to a usual merchant", async () => post({ amt: 180, cat: "grocery", chan: "upi", pay: "known" })],
    ["Paying another customer", "₹3,500 UPI to someone they have never paid: common, usually fine", async () => post({ amt: 3500, chan: "upi", pay: "peer" })],
    ["Rent day", "₹22,000 IMPS to the usual landlord account", async () => post({ amt: 22000, chan: "imps", pay: "ben" })],
    ["SIM-swap drain", "New phone, SIM changed 3 hours ago, ₹49,500 to a stranger", async () => post({ amt: 49500, chan: "upi", pay: "newpers", dev: "new", ip: "new", sim: 3 })],
    ["Vishing with screen-share", "Own phone, caller on the line, screen shared, ₹38,000 to a stranger", async () => post({ amt: 38000, chan: "upi", pay: "newpers", rat: true })],
    ["Mule magnet", "A payee four strangers paid minutes ago receives ₹7,500", async () => post({ amt: 7500, chan: "upi", pay: "fan" })],
    ["Teleporting card", "In-person at home, 20 minutes later in Dubai", async () => {
      await post({ amt: 240, cat: "food", chan: "pos", pay: "known", commit: true });
      return post({ amt: 18500, cat: "fashion", chan: "pos", city: "Dubai", pay: "newmer", dt: 1200 });
    }],
    ["Card-testing burst", "Seven ₹1 online charges, 15 seconds apart (remembered)", async () => {
      const dv = "bot-" + Math.random().toString(36).slice(2, 7); let r;
      for (let i = 0; i < 7; i++) r = await post({ amt: 1, cat: "digital", chan: "ecom", pay: "newmer", dev: dv, ip: "new", commit: true, dt: 15 * i });
      return r;
    }],
  ];
  $("#scen").append(...sc.map(([n, d, f]) => el("button", { class: "btn", onclick: async () => { renderOut(await f()); } }, el("b", null, n), el("div", { class: "note" }, d))));
}
const pu = () => PU.find(u => u.uid === $("#p-uid").value) || PU[0];
const rnd = () => Math.floor(Math.random() * 250) + 1, rid = () => Math.random().toString(36).slice(2, 8);
async function post(o) {
  const u = pu(), ch = o.chan || "upi", digital = ["upi", "ecom", "imps"].includes(ch);
  const ts = (S.snap ? S.snap.ts : PM.start) + (o.dt || 0) + 1, handles = ["ybl", "okaxis", "oksbi", "paytm"], hnd = handles[rnd() % 4];
  let mid, cat = o.cat || "digital", pers = false;
  if (ch === "atm") { mid = "atm-" + u.city; cat = "atm_cash"; }
  else if (o.pay === "newpers" || o.pay === "fan") { mid = `pg${rid()}@${hnd}`; cat = ch === "imps" ? "bank_transfer" : "p2p"; pers = true; }
  else if (o.pay === "peer") { mid = (PU.find(v => v.uid !== u.uid) || u).vpa; cat = ch === "imps" ? "bank_transfer" : "p2p"; pers = true; }
  else if (o.pay === "ben") { mid = u.ben; cat = "bank_transfer"; pers = true; }
  else if (o.pay === "newmer") mid = `pgshop${rid()}@${hnd}`;
  else if (ch === "imps") { mid = u.ben; cat = "bank_transfer"; pers = true; }
  else if (ch === "upi" && o.cat === undefined && o.pay === "known") { mid = u.merchant; cat = o.cat || "grocery"; }
  else mid = u.merchant;
  if (o.pay === "fan") {  // four other customers pay this payee for the first time, just before
    const others = PU.filter(v => v.uid !== u.uid).slice(0, 4);
    for (let i = 0; i < others.length; i++) await api("/api/score", { uid: others[i].uid, amt: 2000 + 500 * i, cat: "p2p", chan: "upi", city: others[i].city, mid, pers: true, dev: others[i].dev, ip: others[i].ip, ts: ts - 600 + 60 * i, commit: true });
  }
  const body = {
    uid: u.uid, amt: +o.amt, cat, chan: ch, city: o.city || u.city, ts, commit: !!o.commit, mid, pers, coll: !!o.coll, rat: !!o.rat, sim: o.sim === undefined ? null : o.sim,
    dev: digital ? (o.dev === "new" ? "new-" + rnd() + rnd() : o.dev && o.dev !== "known" ? o.dev : u.dev) : null,
    ip: digital ? (o.ip === "new" ? `203.${rnd()}.${rnd()}.${rnd()}` : u.ip) : null,
  };
  return api("/api/score", body);
}
async function playGo() {
  const v = id => $("#" + id).value, ch = v("p-chan");
  renderOut(await post({ amt: v("p-amt"), cat: v("p-cat"), chan: ch, city: v("p-city") || null, pay: v("p-pay"), dev: v("p-dev"), ip: v("p-ip"), sim: $("#p-sim").checked ? 6 : undefined, rat: $("#p-rat").checked, coll: $("#p-coll").checked }));
}
function renderOut(c) { renderCase($("#pinsp"), c, S.cfg, {}); }

/* ------------------------------------------------------------ model card */
let MODEL = null;
async function model() {
  if (MODEL) return;
  MODEL = await api("/api/model");
  const r = MODEL.rep, out = $("#modelout");
  const tile = (l, v, s, k) => el("div", { class: "kpi " + (k || "") }, el("div", { class: "l" }, l), el("div", { class: "v" }, v), el("div", { class: "s" }, s));
  const tiles = el("div", { class: "kpis", style: "grid-template-columns:repeat(6,1fr)" },
    tile("ROC AUC", r.auc.toFixed(4), `logistic baseline ${r.lr.auc.toFixed(4)}`), tile("Average precision", r.ap.toFixed(3), `logistic baseline ${r.lr.ap.toFixed(3)}`, "good"),
    tile("Recall at 1% false alarms", pct(r.rec1, 1), `baseline ${pct(r.lr.rec1, 1)}`), tile("Recall at 0.1% false alarms", pct(r.rec01, 1), `baseline ${pct(r.lr.rec01, 1)}`),
    tile("Calibration error (ECE)", r.ece.toFixed(4), "predicted vs. observed rate"), tile("Held-out payments", kfmt(r.n), `${r.npos} fraud · later in time than training`));
  const pc = el("div", { class: "chart" }), cc = el("div", { class: "chart" });
  const imp = r.importance.slice(0, 12), im = imp[0].v;
  const impT = el("div", { class: "econ", style: "grid-template-columns:70px 1fr 48px" });
  imp.forEach(i => { const s = MODEL.shapes.find(x => x.f === i.f); impT.append(el("div", { class: "mono", title: s.desc }, i.f), el("div", { class: "bar" }, el("i", { style: `width:${100 * i.v / im}%;background:#2b47ff` })), el("div", { class: "v" }, i.v.toFixed(2))); });
  const sl = Object.entries(r.slices).sort((a, b) => b[1].flagged - a[1].flagged);
  const slT = el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Segment"), el("th", { class: "r" }, "n"), el("th", { class: "r" }, "Flagged"), el("th", { class: "r" }, "Declined"))),
    el("tbody", null, sl.map(([k, v]) => el("tr", null, el("td", null, k.replace("_", " ")), el("td", { class: "r" }, v.n), el("td", { class: "r" }, pct(v.flagged, 1)), el("td", { class: "r" }, pct(v.declined, 1))))));
  const sh = el("div", { class: "shapes" });
  for (const s of MODEL.shapes) sh.append(shapeBox(s));
  out.replaceChildren(tiles,
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", null, "Precision vs. recall", el("span", { class: "note sp" }, "held-out period")), el("div", { class: "body" }, pc)),
      el("div", { class: "card" }, el("h3", null, "Calibration", el("span", { class: "note sp" }, "when it says 20%, is it 20%?")), el("div", { class: "body" }, cc))),
    el("div", { class: "grid2" },
      el("div", { class: "card" }, el("h3", null, "What the model leans on", el("span", { class: "note sp" }, "mean absolute contribution, log-odds")), el("div", { class: "body" }, impT)),
      el("div", { class: "card" }, el("h3", null, "Who gets flagged, at default costs"), el("div", { class: "body" }, slT))),
    el("div", { class: "card" }, el("h3", null, "Learned shape of every feature", el("span", { class: "note sp" }, "log-odds added to the score as the feature varies; the score is the sum of these")), el("div", { class: "body" }, sh)),
    el("div", { class: "card" }, el("h3", null, "How it works, and where it falls short"), el("div", { class: "body" }, el("ul", { class: "lim" },
      el("li", null, el("b", null, "Built for how India pays. "), "UPI is about 70% of volume; IMPS, cards and ATMs make up the rest. The payee graph matters most here: mule accounts are found by strangers paying them for the first time, not by anything the victim does."),
      el("li", null, el("b", null, "Streaming features, no leakage. "), "Every feature is computed from state before the payment is committed. Velocity windows, spend profile, travel speed from the last in-person use, and the device, network and payee graphs all update afterwards. The first week is burn-in and excluded from training."),
      el("li", null, el("b", null, "Delayed, honest labels. "), "Fraud reports reach the reputation counters hours late, count for 7 days, and a complaint about an authorised scam taints the payee but never the victim's own phone."),
      el("li", null, el("b", null, "Exact explanations. "), "The model is a boosted additive model, so each feature's contribution is the model's own arithmetic. There is no surrogate approximation."),
      el("li", null, el("b", null, "Cost-aware, rail-aware decisions. "), "Approve, step-up and decline are chosen per payment by expected cost. Rails that earn no margin (UPI to people, IMPS, ATM) are cheaper to decline; for them the cost is mostly goodwill. Rules can only escalate."),
      el("li", null, el("b", null, "Step-up is not a silver bullet. "), "The policy assumes 8% of fraudsters pass an OTP challenge. In the simulator a SIM-swapper receives the OTP, a vished customer reads it out and a scammed customer approves it themselves, so those attacks pass 45% to 60% of the time. Stopping them takes friction that targets the scam: first-payee warnings, cooling-off periods and screen-share blocking."),
      el("li", null, el("b", null, "Honest limits. "), "All data is synthetic, so these numbers show the engineering, not real-world performance. Pure social-engineering cases with no screen-share are only partly detectable, and shared kiosk phones look like mule rings. The SIM-change signal assumes telecom data that only some banks receive, and the simulator reflects that."))))
  );
  const pts = r.pr.rec.map((x, i) => [x, r.pr.prec[i]]);
  xyChart(pc, { title: "pr", xr: [0, 1], yr: [0, 1], xt: [0, .25, .5, .75, 1], yt: [0, .25, .5, .75, 1], xf: v => pct(v, 0), yf: v => pct(v, 0), xl: "Recall", yl: "Precision", lines: [{ name: "Held-out", color: "#2b47ff", pts }],
    tip: p => [{ v: pct(p[0], 1), l: "of fraud found" }, { v: pct(p[1], 1), l: "of alerts are fraud" }] });
  xyChart(cc, { title: "calibration", xlog: true, ylog: true, xr: [0.001, 1], yr: [0.001, 1], xt: [0.001, 0.01, 0.1, 1], yt: [0.001, 0.01, 0.1, 1], xf: v => pct(v, v < .01 ? 1 : 0), yf: v => pct(v, v < .01 ? 1 : 0), xl: "Predicted probability", yl: "Observed fraud rate", diag: true,
    lines: [{ name: "Score buckets", color: "#2b47ff", pts: r.calib.filter(b => b.obs > 0).map(b => [b.pred, b.obs, b.n]), dots: true, r: 4 }],
    tip: p => [{ v: pct(p[0], 2), l: "predicted" }, { v: pct(p[1], 2), l: "observed" }, { v: p[2], l: "transactions" }] });
  fairCard(out);
}
function shapeBox(s) {
  const W = 160, H = 54, v = s.v, n = v.length, mx = Math.max(0.3, ...v.map(Math.abs));
  const Y = y => H / 2 - (H / 2 - 4) * y / mx, g = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": s.f + " shape" });
  g.append(sv("line", { x1: 0, x2: W, y1: H / 2, y2: H / 2, stroke: "#dbe1ea" }));
  if (n <= 2) v.forEach((y, i) => g.append(sv("rect", { x: 30 + i * 60, width: 40, y: y >= 0 ? Y(y) : H / 2, height: Math.max(1, Math.abs(Y(y) - H / 2)), fill: y >= 0 ? "#cc2f46" : "#0f8a66", rx: 2 })));
  else {
    let d = ""; v.forEach((y, i) => { const x0 = W * i / n, x1 = W * (i + 1) / n; d += (i ? "L" : "M") + x0.toFixed(1) + " " + Y(y).toFixed(1) + "L" + x1.toFixed(1) + " " + Y(y).toFixed(1); });
    g.append(sv("path", { d, fill: "none", stroke: "#2b47ff", "stroke-width": 1.6 }));
  }
  const b = el("div", { class: "shape", title: s.desc }, el("b", null, s.f), el("div", { class: "note", style: "font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" }, s.desc), g);
  b.addEventListener("pointermove", e => showTip(e, s.f, [{ v: "−" + Math.min(...v).toFixed(2).replace("-", "") + " … +" + Math.max(...v).toFixed(2), l: "log-odds range" }, { v: n <= 2 ? "binary" : n + " bins", l: s.desc }]));
  b.addEventListener("pointerleave", hideTip);
  return b;
}

tabbing(); initLive();
