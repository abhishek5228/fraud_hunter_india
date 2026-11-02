/* Live ops tab */
const S = { feed: [], sel: null, filter: "all", snap: null, hist: [], dots: [], cfg: null, meta: null, paused: false };
const FEEDMAX = 160;

/* ---- KPI strip ---- */
function kpis(s) {
  const lf = s.lg_n ? (s.cm[1][0] + s.cm[2][0]) / s.lg_n : 0;
  const defs = [
    ["Processed", kfmt(s.n), `${s.tps.toFixed(1)} per second`, ""],
    ["Fraud stopped", mk(s.fr_stop), `${pct(s.recall, 1)} of fraud attempts caught`, "good"],
    ["Fraud leaked", mk(s.fr_leak), `${s.bps.toFixed(1)} bps of volume`, s.fr_leak > s.fr_stop ? "bad" : "warn"],
    ["Good customers touched", pct(lf, 2), `${s.cm[1][0]} challenged · ${s.cm[2][0]} declined`, lf > 0.04 ? "warn" : ""],
    ["Good sales lost", mk(s.lg_lost + s.so.lfa), "declines and abandoned challenges", "warn"],
    ["Decision latency", Math.round(s.p50) + " µs", `p99 ${Math.round(s.p99)} µs (one Python thread)`, ""],
    ["Approval rate", s.n ? pct((s.cm[0][0] + s.cm[0][1]) / s.n, 1) : "–", `${s.cm[1][0] + s.cm[1][1]} challenged · ${s.cm[2][0] + s.cm[2][1]} declined`, ""],
  ];
  const h = $("#kpis");
  if (h.children.length !== defs.length) h.replaceChildren(...defs.map(() => el("div", { class: "kpi" }, el("div", { class: "l" }), el("div", { class: "v" }), el("div", { class: "s" }))));
  defs.forEach((d, i) => { const k = h.children[i]; k.className = "kpi " + d[3]; k.children[0].textContent = d[0]; k.children[1].textContent = d[1]; k.children[2].textContent = d[2]; });
}

/* ---- feed ---- */
const keep = t => S.filter === "all" || (S.filter === "flag" && t.dec > 0) || (S.filter === "miss" && t.lab === 1 && (t.out === "approved" || t.out === "pass")) || (S.filter === "fa" && t.lab === 0 && t.dec > 0);
function rowFor(t) {
  const miss = t.lab === 1 && (t.out === "approved" || t.out === "pass"), fa = t.lab === 0 && t.dec > 0;
  const why = t.hits.length ? t.hits[0] : t.top[0] ? t.top[0].txt : "";
  const r = el("div", { class: "row" + (miss ? " miss" : fa ? " fa" : "") + (S.sel === t.id ? " sel" : ""), "data-id": t.id, tabindex: 0, role: "button" },
    el("div", { class: "t" }, stime(t.ts)),
    el("div", { class: "m" }, el("div", null, el("b", null, t.cat.replace("_", " ")), " · ", t.uid), el("div", { class: "sub" }, `${RAILN[t.chan] || t.chan} · ${t.city}` + (t.dec && why ? " · " + why : ""))),
    el("div", { class: "a" }, money(t.amt, t.amt < 100 ? 2 : 0), el("div", { class: "rk" }, el("i", { style: `width:${Math.max(2, 100 * Math.min(1, Math.log10(Math.max(t.p, 1e-4) * 1e4) / 4))}%` }))),
    el("div", { style: "text-align:right" }, el("span", { class: "tag d" + t.dec }, DN[t.dec])));
  const go = () => select(t.id);
  r.addEventListener("click", go); r.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  return r;
}
function addTx(list) {
  const f = $("#feed");
  if (f.querySelector(".empty")) f.replaceChildren();
  for (const t of list) {
    S.feed.unshift(t);
    S.dots.push({ t, born: performance.now() });
    if (keep(t)) f.prepend(rowFor(t));
  }
  if (S.feed.length > FEEDMAX) S.feed.length = FEEDMAX;
  while (f.children.length > FEEDMAX) f.lastChild.remove();
  $("#fcount").textContent = S.feed.length + " recent";
}
function refeed() {
  const f = $("#feed"); f.replaceChildren();
  const rows = S.feed.filter(keep).map(rowFor);
  f.append(...(rows.length ? rows : [el("div", { class: "empty" }, "Nothing matches this filter yet.")]));
}
async function select(id) {
  S.sel = id;
  $$(".row.sel").forEach(r => r.classList.remove("sel"));
  const r = $(`.row[data-id="${id}"]`); if (r) r.classList.add("sel");
  try {
    if (!S.cfg) S.cfg = await api("/api/policy");
    const c = await api("/api/case/" + id);
    renderCase($("#insp"), c, S.cfg, { actions: true });
  } catch (e) { $("#insp").replaceChildren(el("div", { class: "empty" }, "That case has aged out of the engine's recent-case window.")); }
}

/* ---- map: stylised world, recent transactions pulse then fade ---- */
const INDIA = [[68.1, 23.7], [69.2, 22.4], [70.8, 20.7], [72.8, 21.2], [72.9, 19.0], [73.4, 16.0], [74.4, 14.2], [75.0, 12.3], [76.3, 9.7], [77.5, 8.1], [78.2, 8.9], [79.9, 10.3], [80.3, 13.3], [80.1, 15.7], [82.2, 16.9], [84.9, 19.2], [86.9, 21.2], [88.3, 21.7], [89.0, 22.3], [88.7, 24.5], [89.8, 26.2], [91.7, 25.3], [92.3, 24.0], [93.3, 22.9], [94.5, 24.6], [95.2, 26.5], [97.3, 28.2], [95.9, 29.4], [94.0, 28.5], [92.1, 27.8], [90.0, 28.0], [88.9, 27.3], [88.2, 27.9], [86.0, 27.9], [84.0, 28.6], [81.9, 30.3], [79.1, 31.0], [78.7, 32.6], [79.4, 34.0], [77.8, 35.5], [75.9, 36.7], [74.4, 35.0], [74.7, 33.2], [75.2, 32.4], [74.0, 31.0], [74.4, 29.8], [72.9, 28.9], [70.5, 28.0], [69.5, 26.5], [70.2, 25.2]];
const HUBS = [["Delhi", 77.21, 28.61], ["Mumbai", 72.88, 19.08], ["Bengaluru", 77.59, 12.97], ["Kolkata", 88.36, 22.57], ["Chennai", 80.27, 13.08], ["Patna", 85.14, 25.59]];
const VIEW = { lon: [60, 106], lat: [4, 38] };
const DCOL = ["#0f8a66", "#e0a21a", "#cc2f46"];
function drawMap() {
  const cv = $("#map"); if (!cv || $("#tab-live").classList.contains("on") === false) return requestAnimationFrame(drawMap);
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const sx = W / (VIEW.lon[1] - VIEW.lon[0]), sy = H / (VIEW.lat[1] - VIEW.lat[0]), sc = Math.min(sx, sy), ox = (W - sc * (VIEW.lon[1] - VIEW.lon[0])) / 2, oy = (H - sc * (VIEW.lat[1] - VIEW.lat[0])) / 2;
  const X = lon => ox + (lon - VIEW.lon[0]) * sc, Y = lat => oy + (VIEW.lat[1] - lat) * sc;
  const inView = (lo, la) => lo >= VIEW.lon[0] && lo <= VIEW.lon[1] && la >= VIEW.lat[0] && la <= VIEW.lat[1];
  g.fillStyle = "#f3f6fa"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#e3e8f0"; g.lineWidth = 1;
  for (let lo = 65; lo <= 105; lo += 10) { g.beginPath(); g.moveTo(X(lo), 0); g.lineTo(X(lo), H); g.stroke(); }
  for (let la = 10; la <= 35; la += 5) { g.beginPath(); g.moveTo(0, Y(la)); g.lineTo(W, Y(la)); g.stroke(); }
  g.fillStyle = "#dde4ee"; g.beginPath(); INDIA.forEach(([lo, la], i) => (i ? g.lineTo(X(lo), Y(la)) : g.moveTo(X(lo), Y(la)))); g.closePath(); g.fill();
  g.fillStyle = "#8a97ab"; g.font = "10.5px system-ui"; g.textAlign = "left";
  for (const [n, lo, la] of HUBS) { g.fillRect(X(lo) - 1.5, Y(la) - 1.5, 3, 3); g.fillText(n, X(lo) + 5, Y(la) + 3); }
  const now = performance.now(), clampX = lo => Math.max(VIEW.lon[0] + 1.5, Math.min(VIEW.lon[1] - 1.5, lo)), clampY = la => Math.max(VIEW.lat[0] + 1.5, Math.min(VIEW.lat[1] - 1.5, la));
  S.dots = S.dots.filter(d => now - d.born < 7000);
  let abroad = 0;
  for (const d of S.dots) {
    const a = 1 - (now - d.born) / 7000, t = d.t, out = !inView(t.lon, t.lat), big = t.dec > 0;
    const x = X(out ? clampX(t.lon) : t.lon), y = Y(out ? clampY(t.lat) : t.lat);
    g.globalAlpha = Math.max(0.1, a) * (big ? 1 : 0.55);
    if (out) { abroad++; g.strokeStyle = DCOL[t.dec]; g.lineWidth = 2; g.setLineDash([3, 3]); g.beginPath(); g.arc(x, y, 6, 0, 7); g.stroke(); g.setLineDash([]); continue; }
    g.fillStyle = DCOL[t.dec]; g.beginPath(); g.arc(x, y, big ? 4.5 : 2.5, 0, 7); g.fill();
    if (big) { g.strokeStyle = DCOL[t.dec]; g.globalAlpha = a * 0.6; g.lineWidth = 1; g.beginPath(); g.arc(x, y, 5 + (1 - a) * 22, 0, 7); g.stroke(); }
  }
  g.globalAlpha = 1;
  if (abroad) { g.fillStyle = "#6b7a90"; g.font = "11px system-ui"; g.textAlign = "right"; g.fillText("dashed rings: used abroad (" + abroad + ")", W - 8, H - 8); }
  const sel = S.feed.find(t => t.id === S.sel);
  if (sel && inView(sel.lon, sel.lat)) { g.strokeStyle = "#0d1a2d"; g.lineWidth = 2; g.beginPath(); g.arc(X(sel.lon), Y(sel.lat), 9, 0, 7); g.stroke(); }
  requestAnimationFrame(drawMap);
}

/* ---- cumulative money + attack-type table ---- */
function cum() {
  const h = S.hist;
  lineChart($("#cum"), {
    title: "Cumulative money", x: h.map(p => p.ts), xfmt: (v, long) => stime(v, long), yfmt: v => mk(v),
    series: [
      { name: "Fraud stopped", short: "stopped", color: "#0f8a66", y: h.map(p => p.stop) },
      { name: "Fraud leaked", short: "leaked", color: "#cc2f46", y: h.map(p => p.leak) },
      { name: "Good sales lost", short: "lost", color: "#c77800", dash: "5 3", y: h.map(p => p.lost) },
    ], endLabels: true, w: 380, h: 175,
  });
}
function typTable(s) {
  const rows = Object.entries(s.typ).filter(([k]) => k in TYPN);
  const lab = TYPN;
  const h = $("#typ");
  if (!rows.length) { h.replaceChildren(el("div", { class: "empty" }, "No fraud seen yet. Launch an attack from the top bar.")); return; }
  rows.sort((a, b) => b[1][2] - a[1][2]);
  h.replaceChildren(el("table", { class: "t" }, el("thead", null, el("tr", null, el("th", null, "Attack"), el("th", { class: "r" }, "Txns"), el("th", null, "Stopped"), el("th", { class: "r" }, ""))),
    el("tbody", null, rows.map(([k, v]) => {
      const f = v[1] / v[2], tr = el("tr", null, el("td", null, lab[k]), el("td", { class: "r" }, v[2]),
        el("td", null, el("div", { class: "hb" }, el("i", { style: `width:${100 * f}%;background:${f > 0.85 ? "#0f8a66" : f > 0.6 ? "#e0a21a" : "#cc2f46"}` }))), el("td", { class: "r" }, pct(f, 0)));
      tr.addEventListener("pointermove", e => showTip(e, lab[k], [{ v: v[1] + " of " + v[2], l: "stopped" }, { v: v[0], l: "got through" }, { v: money(v[3]), l: "total value" }]));
      tr.addEventListener("pointerleave", hideTip); return tr;
    }))));
}

/* ---- drift: population stability of live traffic against training ---- */
async function drift() {
  if (!$("#tab-live").classList.contains("on")) return;
  const d = await api("/api/drift").catch(() => null), h = $("#drift"), st = $("#dstat");
  if (!d || !d.ready) return;
  st.className = "status sp " + d.status; st.textContent = d.status === "stable" ? "stable" : d.status === "moderate" ? "drifting" : "major drift";
  const top = d.feats.slice(0, 6), mx = Math.max(0.25, top[0].psi);
  h.replaceChildren(el("div", { class: "dr" }, top.flatMap(f => [el("div", { class: "mono", title: f.desc }, f.f),
    el("div", { class: "bar", onpointermove: e => showTip(e, f.f, [{ v: f.psi.toFixed(3), l: "population stability index" }, { v: f.desc, l: "" }]), onpointerleave: hideTip }, el("i", { style: `width:${Math.min(100, 100 * f.psi / mx)}%;background:${f.psi > 0.25 ? "#cc2f46" : f.psi > 0.1 ? "#e0a21a" : "#0f8a66"}` })),
    el("div", { class: "v mono", style: "text-align:right" }, f.psi.toFixed(2))])),
    el("div", { class: "note", style: "margin-top:8px" }, `PSI over the last ${d.n} payments. Under 0.10 is stable, 0.10 to 0.25 is worth watching, over 0.25 means retrain. Try Festival surge.`));
}

/* ---- stream + controls ---- */
function connect() {
  const es = new EventSource((window.FH_API || "") + "/api/stream");
  const nap = setTimeout(() => { $("#clk").textContent = "waking the free server, up to 50 s"; }, 4000);      // a free Render server sleeps when idle
  es.onopen = () => { clearTimeout(nap); $("#lv").classList.add("on"); };
  es.onerror = () => { $("#lv").classList.remove("on"); $("#clk").textContent = "reconnecting"; };
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.t === "tx") { if (!S.paused) addTx(m.d); }
    else if (m.t === "wire") { if (window.wireLoad && $("#tab-wire").classList.contains("on")) wireLoad(); }
    else if (m.t === "st") {
      const s = m.d; S.snap = s;
      $("#clk").textContent = "simulated " + stime(s.ts, true).replace(/\d{4}-\d{2}-\d{2} /, "").slice(0, 9) + " · " + s.tps.toFixed(0) + "/s";
      kpis(s); typTable(s);
      S.hist.push({ ts: s.ts, stop: s.fr_stop, leak: s.fr_leak, lost: s.lg_lost + s.so.lfa });
      if (S.hist.length > 240) S.hist.shift();
      cum();
      $("#pause").textContent = s.run ? "Pause" : "Resume";
    }
  };
}
function initLive() {
  $("#maplg").append(...["Approved", "Step-up", "Declined"].map((n, i) => el("span", null, el("i", { style: "border-color:" + DCOL[i] }), n)));
  $("#chips").addEventListener("click", e => { const b = e.target.closest(".chip"); if (!b) return; S.filter = b.dataset.f; $$(".chip").forEach(c => c.setAttribute("aria-pressed", c === b)); refeed(); });
  $("#pause").onclick = async () => { const s = await api("/api/sim", { run: !(S.snap ? S.snap.run : true) }); S.snap = s; $("#pause").textContent = s.run ? "Pause" : "Resume"; };
  $("#fest").onclick = async e => {
    const btn = e.currentTarget, on = btn.getAttribute("aria-pressed") !== "true";
    await api("/api/sim", { fest: on ? 2.5 : 1 });
    btn.setAttribute("aria-pressed", on); btn.textContent = "Festival surge: " + (on ? "on" : "off");
  };
  setInterval(drift, 4000);
  $("#spd").oninput = e => api("/api/sim", { spd: +e.target.value });
  $("#bst").oninput = e => api("/api/sim", { boost: +e.target.value });
  const m = $("#atkm");
  $("#atkb").onclick = e => { e.stopPropagation(); m.classList.toggle("open"); };
  document.addEventListener("click", () => m.classList.remove("open"));
  $("#atkp").addEventListener("click", async e => {
    const b = e.target.closest("button"); if (!b) return;
    await api("/api/attack", { kind: b.dataset.k }); S.filter = "all";
    if (S.snap && !S.snap.run) await api("/api/sim", { run: true });
  });
  if (window.FH_DEMO) $("#srcbar").hidden = true;        // the static demo has no server to fetch real data onto
  else $("#srcbar").addEventListener("click", e => { const b = e.target.closest("button"); if (b) liveSource(b.dataset.src === "real"); });
  connect(); drawMap();
}


/* real wall-clock time in India, independent of the simulator */
(function () {
  const f = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const tick = () => { const e = document.getElementById("rt"); if (e) e.textContent = f.format(new Date()).replace(",", "") + " IST"; };
  tick(); setInterval(tick, 1000);
})();
