/**
 * Contrast check for web/styles/globals.css.
 *
 * Reads the CSS custom properties straight out of the stylesheet (so it cannot drift from what is
 * shipped) and measures every foreground/background pair the UI actually renders, against the WCAG
 * 2.1 thresholds: 4.5:1 for body text, 3:1 for large text and for non-text UI (focus rings,
 * borders that carry meaning).
 *
 *   node scripts/contrast-check.mjs
 *
 * Exits 1 if any pair fails. No dependencies.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const cssPath = path.join(here, "..", "styles", "globals.css");
const css = readFileSync(cssPath, "utf8");

/** Every `--token: #rrggbb;` in the :root block. */
function tokens() {
  const out = new Map();
  const root = css.slice(css.indexOf(":root"), css.indexOf("/* ---------------------------------------------------------------- base */"));
  for (const match of root.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) {
    out.set(match[1], match[2].toLowerCase());
  }
  return out;
}

const T = tokens();

function rgb(hex) {
  const value = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16) / 255);
}

function luminance(hex) {
  const [r, g, b] = rgb(hex).map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** [foreground token, background token, required ratio, what it is] */
const PAIRS = [
  ["ink", "bg", 4.5, "body text"],
  ["ink", "surface", 4.5, "text on cards"],
  ["ink", "surface-quiet", 4.5, "text on quiet cards / footer"],
  ["ink-muted", "bg", 4.5, "lede / muted text"],
  ["ink-muted", "bg-sunken", 4.5, "muted text on sunken panels"],
  ["ink-muted", "surface-quiet", 4.5, "footer text"],
  ["ink-subtle", "surface-quiet", 4.5, "small print"],
  ["accent", "bg", 4.5, "links"],
  ["accent", "surface", 4.5, "links on cards"],
  ["accent-hover", "bg", 4.5, "hovered links"],
  ["accent-hover", "accent-wash", 4.5, "citation chips"],
  ["accent-hover", "bg-sunken", 4.5, "hovered list rows"],
  ["accent-ink", "accent", 4.5, "primary button label"],
  ["accent-ink", "accent-hover", 4.5, "hovered primary button label"],
  ["ok-ink", "ok-bg", 4.5, "ingested badge / ok notice"],
  ["warn-ink", "warn-bg", 4.5, "not-ingested badge / warn notice"],
  ["refuse-ink", "refuse-bg", 4.5, "refusal panel"],
  ["info-ink", "info-bg", 4.5, "info notice"],
  ["ink", "refuse-bg", 4.5, "text inside a wrong-answer card"],
  ["ink", "warn-bg", 4.5, "text inside a :target section"],
  ["ink", "ok-bg", 4.5, "text inside an ok panel"],
  ["focus", "bg", 3, "focus ring on page"],
  ["focus", "surface-quiet", 3, "focus ring on quiet surfaces"],
  ["focus", "bg-sunken", 3, "focus ring on sunken surfaces"],
  ["focus", "accent-wash", 3, "focus ring on chips"],
  ["focus", "refuse-bg", 3, "focus ring inside refusal panels"],
  ["focus", "warn-bg", 3, "focus ring inside warn panels"],
  ["focus", "info-bg", 3, "focus ring inside info panels"],
  ["focus", "ok-bg", 3, "focus ring inside ok panels"],
  ["border-strong", "bg", 3, "input and chip borders (non-text UI)"],
  ["border-strong", "surface-quiet", 3, "input borders on quiet surfaces"],
  ["focus-alt", "accent", 3, "outer halo on focused primary buttons"],
];

let failures = 0;
const rows = [];
for (const [fgName, bgName, required, label] of PAIRS) {
  const fg = T.get(fgName);
  const bg = T.get(bgName);
  if (!fg || !bg) {
    failures += 1;
    rows.push({ label, fgName, bgName, value: "TOKEN MISSING", required, pass: false });
    continue;
  }
  const value = ratio(fg, bg);
  const pass = value >= required;
  if (!pass) failures += 1;
  rows.push({ label, fg: fg, bg: bg, value: value.toFixed(2), required, pass });
}

const width = Math.max(...rows.map((r) => r.label.length));
console.log(`contrast check — ${cssPath}\n`);
for (const row of rows) {
  console.log(
    `${row.pass ? "PASS" : "FAIL"}  ${row.label.padEnd(width)}  ${String(row.value).padStart(6)}:1  (needs ${row.required}:1)  ${row.fg ?? row.fgName} on ${row.bg ?? row.bgName}`,
  );
}
console.log(`\n${rows.length - failures}/${rows.length} pairs pass`);
if (failures > 0) {
  console.error(`\n${failures} pair(s) below threshold — fix the tokens in web/styles/globals.css`);
  process.exit(1);
}
