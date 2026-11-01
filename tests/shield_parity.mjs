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
console.log(JSON.stringify(T.map(x => { const t = expand(x); return rx.filter(([, r]) => r.test(t)).map(([id]) => id).sort(); })));
