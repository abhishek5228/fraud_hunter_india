/* helpers, charts, and the shared explanation inspector */
const NS = "http://www.w3.org/2000/svg";
const $ = (s, e = document) => e.querySelector(s);
const $$ = (s, e = document) => [...e.querySelectorAll(s)];
function el(tag, at, ...kids) {
  const e = document.createElement(tag);
  for (const k in at || {}) {
    if (k === "class") e.className = at[k];
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), at[k]);
    else if (at[k] !== undefined && at[k] !== null) e.setAttribute(k, at[k]);
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
function sv(tag, at, ...kids) {
  const e = document.createElementNS(NS, tag);
  for (const k in at || {}) e.setAttribute(k, at[k]);
  for (const c of kids.flat()) if (c) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const money = (n, d = 0) => (n < 0 ? "-" : "") + "₹" + Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
const kfmt = n => Math.abs(n) >= 1e6 ? (n / 1e6).toFixed(2) + "M" : Math.abs(n) >= 1e4 ? (n / 1e3).toFixed(1) + "k" : Math.round(n).toLocaleString("en-IN");
const mk = n => { const a = Math.abs(n), s = n < 0 ? "-" : ""; return a >= 1e7 ? s + "₹" + (a / 1e7).toFixed(2) + " Cr" : a >= 1e5 ? s + "₹" + (a / 1e5).toFixed(2) + " L" : a >= 1e3 ? s + "₹" + (a / 1e3).toFixed(1) + "k" : s + "₹" + Math.round(a); };
const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
const pr = p => p >= 0.1 ? (100 * p).toFixed(0) + "%" : p >= 0.001 ? (100 * p).toFixed(1) + "%" : p >= 0.00005 ? (100 * p).toFixed(2) + "%" : "<0.01%";
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function stime(ts, long) {
  const d = new Date((ts + 19800) * 1000), h = d.toISOString().slice(11, 19);   // IST = UTC+5:30
  return long ? DAYS[d.getUTCDay()] + " " + d.toISOString().slice(0, 10) + " " + h + " IST" : h.slice(0, 5);
}
const RAILN = { upi: "UPI", imps: "IMPS / net banking", ecom: "Card online", pos: "Card in person", atm: "ATM" };
const railK = (chan, a, pers) => (chan === "pos" || chan === "ecom") ? 1 : (chan === "upi" && !pers && a > 2000 ? 0.4 / 1.8 : 0);   // share of card margin earned: UPI to merchants above Rs 2,000 carries 0.4% MDR from 15 Oct 2026
const TYPN = { card_test: "Card testing", travel: "Cloned card", high_value: "Stolen-card splurge", ato: "Net-banking takeover", sim_swap: "SIM-swap drain", vishing: "Vishing and screen-share", upi_scam: "UPI payee scam", mule: "Mule cash-out" };
const DN = ["Approve", "Step-up", "Decline"];
const hdr = extra => Object.assign({}, window.FH_KEY ? { "x-api-key": window.FH_KEY } : {}, extra);
const api = async (u, body) => {
  const r = await fetch((window.FH_API || "") + u, body === undefined ? { headers: hdr() } : { method: "POST", headers: hdr({ "content-type": "application/json" }), body: JSON.stringify(body) });
  if (!r.ok) { let m = u + " " + r.status; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r.json();
};

/* ---- tooltip: values lead, labels follow, line keys not boxes ---- */
const tipEl = () => $("#tip");
function showTip(ev, head, rows) {
  const t = tipEl();
  t.replaceChildren();
  if (head) t.append(el("div", { class: "mut", style: "color:#9fb0c9" }, head));
  for (const r of rows) t.append(el("div", { class: "k" }, r.color ? el("i", { style: "border-color:" + r.color }) : null, el("b", null, r.v), el("span", { style: "color:#c4d0e4" }, r.l)));
  t.style.display = "block";
  const w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = Math.min(innerWidth - w - 8, ev.clientX + 14) + "px";
  t.style.top = Math.min(innerHeight - h - 8, ev.clientY + 14) + "px";
}
const hideTip = () => (tipEl().style.display = "none");

/* ---- policy mirror (identical formulas to fh/policy.py) ---- */
function costs(p, a, c, k = 1) {
  const fr = c.risk * (c.loss * a + c.fee), m = c.marg * k * a;
  return [p * fr, c.step + (1 - p) * (1 - c.lpass) * (m + 0.5 * c.churn) + p * c.fpass * fr, (1 - p) * (m + c.churn)];
}
const pick = ([a, s, d]) => (a <= s && a <= d ? 0 : s <= d ? 1 : 2);
function zones(a, c, k) {
  const z = []; let last = -1;
  for (let i = 0; i <= 400; i++) {
    const p = Math.pow(10, -4 + 4 * i / 400), d = pick(costs(p, a, c, k));
    if (d !== last) { z.push({ from: i / 400, d }); last = d; }
  }
  return z;
}

/* ---- line chart with crosshair + one tooltip listing every series ---- */
function lineChart(host, o) {
  const W = o.w || 380, H = o.h || 170, m = { l: 44, r: o.endLabels ? 70 : 12, t: 8, b: 22 };
  const xs = o.x, n = xs.length;
  host.replaceChildren();
  if (n < 2) { host.append(el("div", { class: "empty" }, "Collecting data…")); return; }
  const ymax = Math.max(1e-9, ...o.series.flatMap(s => s.y)) * 1.08;
  const X = i => m.l + (W - m.l - m.r) * i / (n - 1), Y = v => H - m.b - (H - m.t - m.b) * v / ymax;
  const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": o.title });
  for (let k = 0; k <= 3; k++) {
    const v = ymax * k / 3, y = Y(v);
    s.append(sv("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, stroke: "#e6eaf1", "stroke-width": 1 }), sv("text", { x: m.l - 6, y: y + 4, "text-anchor": "end", "font-size": 10.5, fill: "#6b7a90" }, o.yfmt(v)));
  }
  const ticks = [0, Math.floor((n - 1) / 2), n - 1];
  for (const i of ticks) s.append(sv("text", { x: X(i), y: H - 6, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle", "font-size": 10.5, fill: "#6b7a90" }, o.xfmt(xs[i])));
  const ey = []; // end labels: keep them 13px apart so they never overprint
  if (o.endLabels) {
    const ord = o.series.map((se, i) => [Y(se.y[n - 1]), i]).sort((a, b) => a[0] - b[0]);
    ord.forEach(([y, i], k) => { ey[i] = k && y < ey[ord[k - 1][1]] + 13 ? ey[ord[k - 1][1]] + 13 : y; });
  }
  for (const [si, se] of o.series.entries()) {
    s.append(sv("path", { d: se.y.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(""), fill: "none", stroke: se.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-dasharray": se.dash || "" }));
    if (o.endLabels) s.append(sv("text", { x: W - m.r + 6, y: ey[si] + 4, "font-size": 11, fill: "#3c4d66", "font-weight": 600 }, se.short || se.name));
  }
  const cross = sv("line", { y1: m.t, y2: H - m.b, stroke: "#9aa8bd", "stroke-width": 1, visibility: "hidden" });
  const hit = sv("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  hit.addEventListener("pointermove", e => {
    const r = s.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
    const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
    cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
    showTip(e, o.xfmt(xs[i], true), o.series.map(se => ({ color: se.color, v: o.yfmt(se.y[i], true), l: se.name })));
  });
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
  s.append(cross, hit);
  host.append(s, el("div", { class: "legend" }, o.series.map(se => el("span", null, el("i", { style: `border-color:${se.color};${se.dash ? "border-top-style:dashed" : ""}` }), se.name))));
}

/* ---- the decision ruler: risk on a log axis, zones move with the amount at stake ---- */
function ruler(p, amt, cfg, chan, pers) {
  const W = 520, H = 42, L = 6, R = 6, w = W - L - R, col = ["#0f8a66", "#e0a21a", "#cc2f46"];
  const s = sv("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Risk ruler" });
  const z = zones(amt, cfg, railK(chan, amt, pers));
  z.forEach((q, i) => {
    const x0 = L + w * q.from, x1 = L + w * (z[i + 1] ? z[i + 1].from : 1);
    s.append(sv("rect", { x: x0, y: 14, width: Math.max(0, x1 - x0), height: 8, fill: col[q.d], opacity: 0.85 }));
  });
  [1e-4, 1e-3, 1e-2, 1e-1, 1].forEach(t => {
    const x = L + w * (Math.log10(t) + 4) / 4;
    s.append(sv("line", { x1: x, x2: x, y1: 22, y2: 27, stroke: "#9aa8bd" }), sv("text", { x, y: 38, "text-anchor": x > W - 20 ? "end" : x < 20 ? "start" : "middle", "font-size": 10, fill: "#6b7a90" }, t >= 1 ? "100%" : (t * 100) + "%"));
  });
  const px = L + w * Math.max(0, Math.min(1, (Math.log10(Math.max(p, 1e-4)) + 4) / 4));
  s.append(sv("path", { d: `M${px} 24 l-6 -10 h12 z`, fill: "#0d1a2d", transform: "translate(0,-12)" }), sv("rect", { x: px - 1.5, y: 8, width: 3, height: 18, fill: "#0d1a2d", rx: 1 }));
  const st = z.find(q => q.d >= 1), dc = z.find(q => q.d === 2);
  const lbl = `At ${money(amt, amt < 100 ? 2 : 0)} on ${RAILN[chan] || chan}: step-up from ${st ? pr(Math.pow(10, -4 + 4 * st.from)) : "never"}, decline from ${dc ? pr(Math.pow(10, -4 + 4 * dc.from)) : "never"}`;
  return { svg: s, lbl };
}

/* ---- the inspector: why this decision, in order of importance ---- */
function renderCase(host, c, cfg, o = {}) {
  host.replaceChildren();
  const tr = c.truth, dec = c.dec;
  const tag = el("span", { class: "tag d" + dec }, DN[dec]);
  const badges = [c.sim != null && c.sim < 72 ? `SIM changed ${Math.round(c.sim)} h ago` : null, c.rat ? "Screen-share active" : null, c.coll ? "Collect request" : null].filter(Boolean);
  const top = el("div", { class: "top2" },
    el("div", null, el("div", { class: "amt" }, money(c.amt, c.amt < 100 ? 2 : 0)),
      el("div", { class: "meta" }, `${RAILN[c.chan] || c.chan} · ${c.cat.replace("_", " ")} · ${c.city || "?"}, ${c.cty}`),
      el("div", { class: "meta mono", style: "font-size:11.5px" }, `to ${c.mid}${c.pers ? " (person)" : ""}`),
      el("div", { class: "meta mono", style: "font-size:11.5px" }, `${c.uid} · ${stime(c.ts, true)}${c.dev ? " · " + c.dev : ""}`),
      badges.length ? el("div", { class: "badges" }, badges.map(b => el("span", { class: "bdg" }, b))) : null),
    el("div", { class: "verdict" }, tag, el("div", { class: "pp" }, `fraud probability `, el("b", { style: "color:var(--ink)" }, pr(c.p))), el("div", { class: "pp" }, `scored in ${Math.round(c.lat_us)} µs`)));
  host.append(top);
  if (tr) {
    let k = "nt", t;
    const fraud = tr.lab === 1, thru = tr.out === "approved" || tr.out === "pass";
    if (fraud && !thru) { k = "ok"; t = `Simulation truth: fraud (${tr.typ.replace("_", " ")}). Stopped.`; }
    else if (fraud) { k = "bad"; t = `Simulation truth: fraud (${tr.typ.replace("_", " ")}). It got through.`; }
    else if (dec === 2) { k = "bad"; t = `Simulation truth: legitimate (${tr.typ}). A good customer was declined.`; }
    else if (dec === 1) { k = "warn"; t = `Simulation truth: legitimate (${tr.typ}). Customer was challenged${tr.out === "fail" ? " and abandoned" : " and passed"}.`; }
    else { k = "ok"; t = `Simulation truth: legitimate (${tr.typ}). Approved without friction.`; }
    host.append(el("div", { class: "truth " + k }, t));
  }
  host.append(el("div", { class: "why" }, c.why));

  const r = ruler(c.p, c.amt, cfg, c.chan, c.pers);
  host.append(el("div", { class: "sec" }, el("h4", null, "Decision ruler ", el("span", null, r.lbl)), el("div", { class: "ruler" }, r.svg)));

  if (c.hits.length) host.append(el("div", { class: "sec" }, el("h4", null, "Guardrail rules", el("span", null, "rules can only escalate, never relax")),
    el("div", { class: "hits" }, c.hits.map(h => el("div", { class: "hit" + (h.lvl === 1 ? " s" : "") }, el("b", null, h.code), " ", h.lvl === 2 ? "(decline)" : "(step-up)", el("div", null, h.msg))))));

  const sum = c.top.reduce((a, t) => a + t.c, 0), rest = (c.logit - c.base) - sum;
  const mx = Math.max(0.5, ...c.top.map(t => Math.abs(t.c)), Math.abs(rest));
  const rows = c.top.map(t => [t.txt, t.c]);
  if (Math.abs(rest) >= 0.05) rows.push(["All other small factors", rest]);
  const wf = el("div", { class: "wf" });
  for (const [txt, v] of rows) {
    wf.append(el("div", { class: "lb", title: txt }, txt),
      el("div", { class: "tr" }, el("i", { class: v > 0 ? "up" : "dn", style: `width:${Math.min(50, 50 * Math.abs(v) / mx)}%` })),
      el("div", { class: "vv " + (v > 0 ? "up" : "dn") }, (v > 0 ? "+" : "−") + Math.abs(v).toFixed(2)));
  }
  host.append(el("div", { class: "sec" }, el("h4", null, "Why this score ", el("span", null, "exact log-odds contributions; red raises risk, green lowers it")), wf,
    el("div", { class: "eq" }, `typical transaction ${c.base.toFixed(2)}  +  factors ${(c.logit - c.base >= 0 ? "+" : "−")}${Math.abs(c.logit - c.base).toFixed(2)}  =  log-odds ${c.logit.toFixed(2)}  →  ${pr(c.p)}`)));

  const mxc = Math.max(...c.cost, 1e-9), best = Math.min(...c.cost);
  const econ = el("div", { class: "econ" });
  c.cost.forEach((v, i) => econ.append(el("div", { class: i === c.dpol ? "pick" : "" }, el("span", { class: i === c.dpol ? "nm" : "" }, DN[i])),
    el("div", { class: "bar " + (i === c.dpol ? "pick" : "") }, el("i", { style: `width:${Math.max(1.5, 100 * v / mxc)}%` })), el("div", { class: "v" }, money(v, v < 10 ? 2 : 0))));
  host.append(el("div", { class: "sec" }, el("h4", null, "Expected cost of each action ", el("span", null, "the cheapest wins; fraud loss vs. customer friction")), econ));

  if (c.msg) {
    const box = el("div", { class: "phone" }), set = lang => { box.textContent = c.msg[lang]; box.lang = lang === "hi" ? "hi" : "en"; en.setAttribute("aria-pressed", lang === "en"); hi.setAttribute("aria-pressed", lang === "hi"); };
    const en = el("button", { class: "chip", onclick: () => set("en") }, "English"), hi = el("button", { class: "chip", onclick: () => set("hi") }, "हिन्दी");
    host.append(el("div", { class: "sec" }, el("h4", null, "What the customer sees ", el("span", null, "plain words, no rule logic leaked")), el("div", { class: "chips", style: "padding:0 0 6px" }, en, hi), box));
    set("en");
  }
  if (o.actions) {
    const fb = (verdict, block) => async ev => {
      ev.target.disabled = true;
      try { await api("/api/feedback", { id: c.id, verdict, block }); ev.target.textContent = "Recorded"; o.onDone && o.onDone(); } catch (e) { ev.target.textContent = "Case expired"; }
    };
    host.append(el("div", { class: "act" }, el("button", { class: "btn bad", onclick: fb("fraud", false) }, "Confirm fraud"),
      el("button", { class: "btn bad", onclick: fb("fraud", true) }, "Confirm fraud and block device, network and payee"), el("button", { class: "btn", onclick: fb("legit", false) }, "Mark legitimate")));
  } else host.append(el("div", { style: "height:14px" }));
}
