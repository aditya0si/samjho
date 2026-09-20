/**
 * Copy the shipped syllabus into the web app, for deployments that upload only `web/`.
 *
 * `lib/syllabus.ts` reads the syllabus from outside this directory (`../data/syllabus/class10.json`)
 * when it runs beside the rest of the repo, and prefers the API when one is reachable. A Vercel build
 * uploads only `web/`, so neither path exists there and the deployed site would show no chapter list
 * at all. This copies the one committed source of truth to `web/data/syllabus/class10.json` at build
 * time; that copy is gitignored, so the repository still holds exactly one copy of the file.
 *
 * The syllabus is factual metadata — chapter and section structure, the same thing a printed table of
 * contents carries — not book text. See docs/adr/ADR-001-licensing-boundary.md for why that
 * distinction is the whole architecture. Nothing textbook-derived is copied here.
 *
 * Deliberately tolerant: if the source is missing (someone building `web/` on its own), it says so and
 * exits 0. The app then renders its explicit "no syllabus could be read" state, which is honest and is
 * verified behaviour rather than a blank page.
 */
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)); // web/scripts
const webRoot = resolve(here, ".."); // web/
const source = resolve(webRoot, "..", "data", "syllabus", "class10.json");
const target = resolve(webRoot, "data", "syllabus", "class10.json");

if (!existsSync(source)) {
  console.log(
    `[sync-syllabus] no syllabus at ${source} — skipping. The app will report that no syllabus could be read.`,
  );
  process.exit(0);
}

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log(`[sync-syllabus] copied ${source} -> ${target}`);
