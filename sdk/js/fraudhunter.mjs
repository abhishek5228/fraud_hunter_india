// Fraud Hunter client for browsers and Node 18+. No dependencies.
//   import { FraudHunter } from "./fraudhunter.mjs";
//   const fh = new FraudHunter("https://fraud-hunter-api.onrender.com", { apiKey: "..." });
//   const d = await fh.score({ uid: "u0042", amt: 2500, mid: "shop@upi", chan: "upi", city: "Mumbai" });
//   if (d.decision !== "APPROVE") console.log(d.risk, d.reasons, d.customerMessage?.en);
export class FraudHunterError extends Error {
  constructor(status, detail) { super(`${status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`); this.status = status; this.detail = detail; }
}
export class FraudHunter {
  constructor(url, { apiKey, timeoutMs = 3000, retries = 2, fetchImpl } = {}) {
    Object.assign(this, { url: url.replace(/\/+$/, ""), apiKey, timeoutMs, retries, f: fetchImpl || ((...a) => fetch(...a)) });
  }
  async #call(method, path, body, safe = false) {
    const headers = { "content-type": "application/json", ...(this.apiKey ? { "x-api-key": this.apiKey } : {}) };
    const tries = safe ? this.retries + 1 : 1;
    for (let i = 0; i < tries; i++) {
      let r;
      try {
        r = await this.f(this.url + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(this.timeoutMs) });
      } catch (e) {
        if (i < tries - 1) { await new Promise(s => setTimeout(s, 200 * 2 ** i)); continue; }
        throw new FraudHunterError(0, `cannot reach ${this.url} (${e.name})`);
      }
      if (r.status >= 500 && i < tries - 1) { await new Promise(s => setTimeout(s, 200 * 2 ** i)); continue; }
      const js = await r.json().catch(() => null);
      if (!r.ok) throw new FraudHunterError(r.status, js?.detail ?? js);
      return js;
    }
  }
  async score({ uid, amt, mid = "shop@upi", chan = "upi", cat = "digital", commit = true, ...more }) {
    const raw = await this.#call("POST", "/api/score", { uid, amt, mid, chan, cat, commit, ...more }, !commit);
    return { id: raw.id, decision: raw.dname, risk: raw.score, probability: raw.p, reasons: raw.hits.map(h => h.code), drivers: raw.top.map(t => t.txt),
             why: raw.why, customerMessage: raw.msg, latencyUs: raw.lat_us, approved: raw.dname === "APPROVE", raw };
  }
  confirm(id, passed) { return this.#call("POST", "/api/confirm", { id, passed: !!passed }); }
  feedback(id, fraud, block = false) { return this.#call("POST", "/api/feedback", { id, verdict: fraud ? "fraud" : "legit", block }); }
  shield(text) { return this.#call("POST", "/api/shield", { text }, true); }
  health() { return this.#call("GET", "/api/health", undefined, true); }
}
