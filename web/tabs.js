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
  }));
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
