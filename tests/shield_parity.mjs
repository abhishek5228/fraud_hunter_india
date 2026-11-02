// Prints, for every fixture text, the Scam Shield rule ids the BROWSER implementation would match (same JSON rules as the server).
import fs from "fs";
const R = JSON.parse(fs.readFileSync(new URL("../fh/shield_rules.json", import.meta.url), "utf8"));
const T = JSON.parse(fs.readFileSync(new URL("./fixtures/shield_texts.json", import.meta.url), "utf8"));
const rx = R.rules.map(r => [r.id, new RegExp(r.re, "i")]);
function expand(text) {
  let t = text;
  for (const m of text.matchAll(/upi:\/\/\S+/gi)) {
    try { const q = new URL(m[0]).searchParams; t += " " + ["pa", "pn", "tn"].filter(k => q.get(k)).map(k => k + " " + q.get(k)).join(" "); } catch (e) {}
  }
  return t;
}
function shTokens(text) {
  const t = text.toLowerCase().replace(/https?:\/\/\S+|www\.\S+/g, " urltok ").replace(/[0-9]+/g, "0"), w = t.match(/[a-z0-9]+/g) || [];
  return w.concat(w.slice(1).map((x, i) => w[i] + "_" + x));
}
function modelHit(text) {
  const M = R.model; if (!M) return [];
  let z = M.bias; for (const k of new Set(shTokens(text))) z += M.w[k] || 0;
  return 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z)))) >= M.t ? ["text_model"] : [];
}
function modelP(text) { const M = R.model; let z = M.bias; for (const k of new Set(shTokens(text))) z += M.w[k] || 0; return 1 / (1 + Math.exp(-Math.max(-30, Math.min(30, z)))); }
if (process.argv[2] === "p") { console.log(JSON.stringify(T.map(modelP))); process.exit(0); }
console.log(JSON.stringify(T.map(x => { const t = expand(x); return rx.filter(([, r]) => r.test(t)).map(([id]) => id).concat(modelHit(x)).sort(); })));
