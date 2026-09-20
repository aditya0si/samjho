/**
 * Reading the syllabus.
 *
 * The syllabus is factual structure (chapter and section headings with page anchors) and it is
 * shipped in the repo at `data/syllabus/class10.json`. The API also serves it (`GET /subjects`,
 * CONTRACTS §4). We prefer the API — it is the thing that knows what has actually been ingested —
 * and fall back to the file on disk so the site is useful when the API is down or not yet built.
 *
 * Whichever route was taken is recorded in `source` and shown to the student, so a page is never
 * quietly serving stale structure.
 *
 * Server-only: this module touches `fs`. Anything a client component needs from the syllabus —
 * hrefs, citation labels — lives in `lib/links.ts` instead. The `server-only` import makes a
 * mistake here fail loudly at build time instead of dragging `node:fs` into the browser bundle.
 */

import "server-only";

import fs from "node:fs/promises";
import path from "node:path";

import { cache } from "react";

import { getSubjects, type ApiFailure } from "./api";
import type { Syllabus, SyllabusChapter, SyllabusSubject, SyllabusSection } from "./types";
import { slugify } from "./util";

export type SyllabusSource = "api" | "file";

export type SyllabusLoad = {
  syllabus: Syllabus | null;
  source: SyllabusSource | null;
  apiError: ApiFailure | null;
  fileError: string | null;
  filePath: string;
};

/** Where the local copy lives. `SAMJHO_SYLLABUS_PATH` overrides it for odd deployments. */
export function syllabusFilePath(): string {
  if (process.env.SAMJHO_SYLLABUS_PATH) return path.resolve(process.env.SAMJHO_SYLLABUS_PATH);
  return path.resolve(process.cwd(), "..", "data", "syllabus", "class10.json");
}

function candidatePaths(): string[] {
  const override = process.env.SAMJHO_SYLLABUS_PATH;
  if (override) return [path.resolve(override)];
  const cwd = process.cwd();
  return [
    path.resolve(cwd, "..", "data", "syllabus", "class10.json"), // web/ next to data/
    path.resolve(cwd, "data", "syllabus", "class10.json"), // run from the repo root
  ];
}

async function readSyllabusFile(): Promise<Syllabus | null> {
  for (const candidate of candidatePaths()) {
    try {
      const text = await fs.readFile(candidate, "utf8");
      const parsed = JSON.parse(text) as Syllabus;
      if (Array.isArray(parsed?.subjects) && parsed.subjects.length > 0) return parsed;
      return null;
    } catch {
      continue;
    }
  }
  return null;
}

export async function loadSyllabus(): Promise<SyllabusLoad> {
  const filePath = syllabusFilePath();
  const api = await getSubjects();
  if (api.ok) {
    return { syllabus: api.data, source: "api", apiError: null, fileError: null, filePath };
  }
  const fromFile = await readSyllabusFile();
  if (fromFile) {
    return {
      syllabus: fromFile,
      source: "file",
      apiError: api.error,
      fileError: null,
      filePath,
    };
  }
  return {
    syllabus: null,
    source: null,
    apiError: api.error,
    fileError: `No readable syllabus at ${filePath}`,
    filePath,
  };
}

// --- lookups ---------------------------------------------------------------------------------

/**
 * Same load, deduplicated per request: a page and its `generateMetadata` share one round trip.
 */
export const loadSyllabusCached = cache(loadSyllabus);

const SUBJECT_ALIASES: Record<string, string[]> = {
  maths: ["math", "mathematics", "maths"],
  science: ["science", "sci"],
};

/** Resolve a URL slug to a subject. Accepts the id, the display name, or a common alias. */
export function findSubject(syllabus: Syllabus, slug: string): SyllabusSubject | null {
  const wanted = slugify(decodeURIComponent(slug));
  for (const subject of syllabus.subjects) {
    const candidates = new Set<string>([slugify(subject.id), slugify(subject.name)]);
    for (const alias of SUBJECT_ALIASES[slugify(subject.id)] ?? []) candidates.add(alias);
    if (candidates.has(wanted)) return subject;
  }
  return null;
}

export function findChapter(subject: SyllabusSubject, raw: string): SyllabusChapter | null {
  const no = Number(decodeURIComponent(raw));
  if (!Number.isFinite(no)) return null;
  return subject.chapters.find((chapter) => chapter.no === no) ?? null;
}

export function sectionTitleFor(chapter: SyllabusChapter, sectionNo: string): string | null {
  return chapter.sections.find((section) => section.no === sectionNo)?.title ?? null;
}

export function missingSectionNumbers(chapter: SyllabusChapter, sectionNos: string[]): string[] {
  const known = new Set(chapter.sections.map((section) => section.no));
  return sectionNos.filter((no) => !known.has(no));
}

export type { SyllabusSection, SyllabusChapter, SyllabusSubject, Syllabus };
