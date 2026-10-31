/* Backend-free demo mode.
   Loaded BEFORE lib.js only in demo builds. It answers every /api/* call and the live stream from output
   that the real engine produced offline (tools/build_demo.py, tools/capture_scenarios.py), so the unmodified
   dashboard runs on any static host. Nothing here scores anything: it replays recorded decisions. */
(function () {
  const realFetch = window.fetch.bind(window), RealES = window.EventSource;
  let D = null, snapT = 0;
  const S = { run: true, spd: 150, boost: 1, fest: 1, q: [], bi: 0, fi: 0, off: 0, last: 0, acc: 0, shift: {}, feStart: 0, wall: [], lat: [] };
  let st = null;
  const subs = new Set();
  const resetStats = () => { st = { n: 0, vol: 0, cm: [[0, 0], [0, 0], [0, 0]], am: [[0, 0], [0, 0], [0, 0]], so: { lp: 0, lf: 0, fp: 0, ff: 0, lfa: 0, ffa: 0, fpa: 0, lpa: 0 }, typ: {} }; };
  resetStats();

  const sig = (b, uh) => [Number(b.amt), b.chan, b.cat, b.city === uh[b.uid] ? "home" : b.city, !!b.rat, b.sim == null ? "" : b.sim, !!b.commit,
    b.dev && (String(b.dev).startsWith("new-") || String(b.dev).startsWith("bot-")) ? "new" : "known"].join("|");

  const ready = (async () => {
    const tag = document.getElementById("demo-data");
    D = tag ? JSON.parse(tag.textContent) : await (await realFetch("demo-data.json")).json();
    S.last = D.base[0].ts - 30;
    S.sc = {};
    const uh = {};
    (D.users || []).forEach(u => (uh[u.uid] = u.city));
    D.scenarios.forEach(c => (S.sc[sig(c.req, uh)] = c.res));
    banner();
    setInterval(tick, 100);
  })();

  function banner() {
    const d = document.createElement("div");
    d.style.cssText = "background:#243653;color:#e8edf6;padding:7px 14px;font-size:12.5px;text-align:center";
    d.textContent = "Demo mode: replaying decisions the real engine recorded offline (no backend needed). Run the Python backend for live scoring and free-form inputs.";
    document.body.prepend(d);
    const bst = document.getElementById("bst");
    if (bst) bst.closest("label").style.display = "none";
  }

  function nextEvent() {
    if (S.q.length) return S.q.shift();
    const src = S.fest > 1 ? D.fest : D.base, key = S.fest > 1 ? "fi" : "bi";
    if (S[key] >= src.length) { S[key] = 0; S.off = S.last - src[0].ts + 20; }
    return { m: src[S[key]++], shift: S.off };
  }

  function emit(n) {
    const out = [];
    for (let i = 0; i < n; i++) {
      const { m: raw, shift } = nextEvent();
      const ts = Math.max(raw.ts + shift, S.last + 1);
      S.shift[raw.id] = ts - D.cases[raw.id].ts; S.last = ts;
      const m = Object.assign({}, raw, { ts });
      out.push(m); account(m);
    }
    if (out.length) broadcast({ t: "tx", d: out });
  }

  function account(m) {
    const a = m.amt, s = st.so;
    st.n++; st.vol += a; st.cm[m.dec][m.lab]++; st.am[m.dec][m.lab] += a;
    if (m.dec === 1) { const k = (m.lab ? "f" : "l") + (m.out === "pass" ? "p" : "f"); s[k]++; s[k + "a"] = (s[k + "a"] || 0) + a; }
    const t = st.typ[m.typ] || (st.typ[m.typ] = [0, 0, 0, 0]);
    t[m.out === "approved" || m.out === "pass" ? 0 : 1]++; t[2]++; t[3] += a;
    S.lat.push(m.us); if (S.lat.length > 2000) S.lat.shift();
    S.wall.push(performance.now()); if (S.wall.length > 80) S.wall.shift();
    if (S.fest > 1) S.feStart++;
  }

  function snap() {
    const cm = st.cm, am = st.am, so = st.so;
    const frStop = am[2][1] + so.ffa, frLeak = am[0][1] + so.fpa, lgLost = am[2][0] + so.lfa;
    const vol = st.vol, lgN = cm[0][0] + cm[1][0] + cm[2][0], frN = cm[0][1] + cm[1][1] + cm[2][1], tp = cm[2][1] + so.ff, fn = cm[0][1] + so.fp;
    const v = S.lat.slice().sort((x, y) => x - y), pc = q => (v.length ? v[Math.min(v.length - 1, Math.floor(q * v.length))] : 0);
    const now = performance.now(), recent = S.wall.filter(w => now - w < 5000).length;
    return { ts: S.last, n: st.n, vol, cm, am, so, fr_stop: frStop, fr_leak: frLeak, lg_lost: lgLost, lg_fric: cm[1][0], fr_n: frN, lg_n: lgN,
      fr_tp: tp, fr_fn: fn, recall: frN ? tp / frN : 0, tps: recent / 5, p50: pc(0.5), p99: pc(0.99), spd: S.spd, run: S.run, boost: S.boost,
      typ: st.typ, queue: S.q.length, bps: vol ? 1e4 * frLeak / vol : 0, fest: S.fest };
  }

  function broadcast(msg) { const e = { data: JSON.stringify(msg) }; subs.forEach(s => s.onmessage && s.onmessage(e)); }

  function tick() {
    if (!S.run || !subs.size) return;
    S.acc += 0.8 * (S.spd / 150);
    const n = Math.floor(S.acc); S.acc -= n;
    if (n) emit(n);
    if (performance.now() - snapT > 1000) { snapT = performance.now(); broadcast({ t: "st", d: snap() }); }
  }

  window.EventSource = function (url) {
    if (!String(url).includes("/api/stream")) return new RealES(url);
    const es = { onopen: null, onmessage: null, onerror: null, close() { subs.delete(es); } };
    ready.then(() => { subs.add(es); es.onopen && es.onopen(); es.onmessage && es.onmessage({ data: JSON.stringify({ t: "st", d: snap() }) }); });
    return es;
  };

  const lg = Math.log2;
  function nearestLab(b) {
    let best = null, bd = 1e9;
    for (const k in D.labs) {
      const [r, c, s] = k.split("|").map(Number);
      const d = Math.abs(lg((b.risk || 1) / r)) + Math.abs(lg((b.churn || 400) / c)) + Math.abs(lg((b.step || 15) / s));
      if (d < bd) { bd = d; best = k; }
    }
    return D.labs[best];
  }

  function handle(path, method, b) {
    if (path === "/api/health") return { ok: true, n: st.n, p99_us: 0 };
    if (path === "/api/policy") return Object.assign({}, D.cfg, method === "POST" ? b : {});
    if (path === "/api/policy/lab") return nearestLab(b || {});
    if (path === "/api/model") return D.model;
    if (path === "/api/meta") return Object.assign({}, D.meta, { fest: S.fest });
    if (path === "/api/users") return D.users;
    if (path === "/api/drift") return Object.assign({}, S.fest > 1 && S.feStart > 120 ? D.drift.fest : D.drift.normal, { fest: S.fest });
    if (path === "/api/sim") {
      if (b.spd != null) S.spd = Math.max(10, Math.min(2000, b.spd));
      if (b.run != null) S.run = b.run;
      if (b.fest != null) { const f = Math.max(1, Math.min(4, b.fest)); if (f !== S.fest) { S.fest = f; S.feStart = 0; S.q = []; } }
      if (b.reset) resetStats();
      return snap();
    }
    if (path === "/api/attack") {
      const kinds = b.kind === "mix" ? D.meta.kinds : [b.kind];
      let n = 0;
      for (const k of kinds) {
        const eps = D.lib[k]; if (!eps) return { __err: 422, detail: "unknown kind" };
        const ep = eps[(S.ai = ((S.ai || 0) + 1)) % eps.length], base = S.last + 2 - ep[0].ts;
        ep.forEach(m => S.q.push({ m, shift: base })); n += ep.length;
      }
      return { kinds, injected: n };
    }
    if (path === "/api/feedback") return { ok: true, fb: { fraud: 0, legit: 0, blocks: 0 }, blocklist: 0 };
    if (path === "/api/confirm") return { ok: true };
    if (path.startsWith("/api/case/")) {
      const id = path.slice(10), c = D.cases[id];
      if (!c) return { __err: 404, detail: "case expired or unknown" };
      return Object.assign({}, c, { ts: c.ts + (S.shift[id] || 0) });
    }
    if (path === "/api/score") {
      const uh = {}; (D.users || []).forEach(u => (uh[u.uid] = u.city));
      const r = S.sc[sig(b, uh)];
      return r || { __err: 422, detail: "Free-form scoring needs the live backend. The scenario buttons replay real recorded runs." };
    }
    return { __err: 404, detail: "not available in demo mode" };
  }

  window.fetch = async function (url, opts) {
    const u = String(url), i = u.indexOf("/api/");
    if (i < 0) return realFetch(url, opts);
    await ready;
    const o = opts || {};
    let r;
    try { r = handle(u.slice(i).split("?")[0], o.method || "GET", o.body ? JSON.parse(o.body) : {}); } catch (e) { r = { __err: 500, detail: String(e) }; }
    return new Response(JSON.stringify(r.__err ? { detail: r.detail } : r), { status: r.__err || 200, headers: { "content-type": "application/json" } });
  };
})();
