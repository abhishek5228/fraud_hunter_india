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
    el("div", { class: "m" }, el("div", null, el("b", null, t.cat.replace("_", " ")), " · ", t.uid), el("div", { class: "sub" }, `${t.city} · ${t.chan === "ecom" ? "online" : t.chan}` + (t.dec && why ? " · " + why : ""))),
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
const LAND = [
  [[-168, 66], [-140, 70], [-95, 72], [-80, 68], [-62, 58], [-55, 48], [-70, 42], [-76, 35], [-81, 25], [-97, 26], [-105, 22], [-117, 32], [-124, 40], [-125, 49], [-140, 59], [-165, 60]],
  [[-55, 60], [-45, 60], [-20, 70], [-20, 82], [-60, 82], [-70, 76]],
  [[-80, 10], [-62, 11], [-50, 0], [-35, -6], [-40, -22], [-55, -35], [-68, -52], [-75, -48], [-72, -30], [-80, -6]],
  [[-10, 36], [-9, 43], [0, 50], [8, 58], [25, 70], [60, 70], [100, 77], [140, 72], [180, 68], [165, 60], [142, 52], [128, 40], [122, 30], [110, 20], [106, 10], [100, 3], [98, 15], [92, 22], [80, 10], [73, 18], [68, 24], [57, 26], [50, 30], [44, 12], [35, 30], [27, 37], [10, 38]],
  [[-17, 21], [-10, 35], [10, 37], [32, 31], [43, 12], [51, 11], [40, -10], [35, -25], [20, -35], [12, -18], [9, 4], [-8, 5], [-17, 14]],
  [[114, -22], [130, -12], [142, -11], [153, -26], [147, -39], [135, -35], [115, -34]],
];
const DCOL = ["#0f8a66", "#e0a21a", "#cc2f46"];
function drawMap() {
  const cv = $("#map"); if (!cv || $("#tab-live").classList.contains("on") === false) return requestAnimationFrame(drawMap);
  const dpr = devicePixelRatio || 1, W = cv.clientWidth, H = cv.clientHeight;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const X = lon => (lon + 180) / 360 * W, Y = lat => (78 - lat) / 135 * H;
  g.fillStyle = "#f3f6fa"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "#e3e8f0"; g.lineWidth = 1;
  for (let lo = -150; lo <= 150; lo += 30) { g.beginPath(); g.moveTo(X(lo), 0); g.lineTo(X(lo), H); g.stroke(); }
  for (let la = -60; la <= 60; la += 30) { g.beginPath(); g.moveTo(0, Y(la)); g.lineTo(W, Y(la)); g.stroke(); }
  g.fillStyle = "#dde4ee";
  for (const poly of LAND) { g.beginPath(); poly.forEach(([lo, la], i) => (i ? g.lineTo(X(lo), Y(la)) : g.moveTo(X(lo), Y(la)))); g.closePath(); g.fill(); }
  const now = performance.now();
  S.dots = S.dots.filter(d => now - d.born < 7000);
  for (const d of S.dots) {
    const a = 1 - (now - d.born) / 7000, t = d.t, x = X(t.lon), y = Y(t.lat), big = t.dec > 0;
    g.fillStyle = DCOL[t.dec]; g.globalAlpha = Math.max(0.1, a) * (big ? 1 : 0.55);
    g.beginPath(); g.arc(x, y, big ? 4.5 : 2.5, 0, 7); g.fill();
    if (big) { g.strokeStyle = DCOL[t.dec]; g.globalAlpha = a * 0.6; g.beginPath(); g.arc(x, y, 5 + (1 - a) * 22, 0, 7); g.stroke(); }
  }
  g.globalAlpha = 1;
  const sel = S.feed.find(t => t.id === S.sel);
  if (sel) { g.strokeStyle = "#0d1a2d"; g.lineWidth = 2; g.beginPath(); g.arc(X(sel.lon), Y(sel.lat), 9, 0, 7); g.stroke(); }
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
  const rows = Object.entries(s.typ).filter(([k]) => ["card_test", "ato", "ato_soft", "hijack", "travel", "high_value", "mule"].includes(k));
  const lab = { card_test: "Card testing", ato: "Account takeover", ato_soft: "Soft takeover", hijack: "Session hijack", travel: "Cloned card", high_value: "Stolen-card splurge", mule: "Mule ring" };
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

/* ---- stream + controls ---- */
function connect() {
  const es = new EventSource("/api/stream");
  es.onopen = () => { $("#lv").classList.add("on"); };
  es.onerror = () => { $("#lv").classList.remove("on"); $("#clk").textContent = "reconnecting"; };
  es.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.t === "tx") { if (!S.paused) addTx(m.d); }
    else {
      const s = m.d; S.snap = s;
      $("#clk").textContent = stime(s.ts, true).replace(" UTC", "") + " · " + s.tps.toFixed(0) + "/s";
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
  connect(); drawMap();
}
