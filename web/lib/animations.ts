/**
 * The animation host's data layer.
 *
 * CONTRACTS §6 freezes the registry shape:
 *   `web/components/animations/registry-science.ts` and `registry-maths.ts` export
 *   `{ conceptId, title, chapterRef, Component }[]`.
 *
 * Two builders write those files and they are not written yet, so this module:
 *  - imports them as namespaces (so a default export, a named export, or a module-level array all
 *    work) and normalises whatever it finds;
 *  - never assumes `chapterRef` is a particular type — it is documented as a reference, so it is
 *    read as "some string/number/object that names a subject and a chapter" and matched loosely;
 *  - reports what it could not place rather than guessing, so the chapter page can say so.
 *
 * Safe in both server and client components (no `fs`, no Node APIs). It is used from a client
 * component so that a registry marked `"use client"` still works.
 */

import type { ComponentType } from "react";

import * as mathsModule from "@/components/animations/registry-maths";
import * as scienceModule from "@/components/animations/registry-science";

export type ConceptAnimationProps = { className?: string };

export type AnimationEntry = {
  conceptId: string;
  title: string;
  Component: ComponentType<ConceptAnimationProps>;
};

export type ChapterAnimations = {
  /** Entries whose chapterRef points at this chapter. */
  entries: AnimationEntry[];
  /** Entries the registries exported that carry no usable chapterRef. Never rendered blindly. */
  unplaceable: string[];
  /** Everything the two registries exported, matched or not. */
  total: number;
};

type RawEntry = {
  conceptId: string;
  title: string;
  chapterRef: unknown;
  Component: ComponentType<ConceptAnimationProps>;
};

/** Pull an array of entries out of whatever the registry module exports. */
function pickArray(mod: unknown): unknown[] {
  if (Array.isArray(mod)) return mod;
  if (mod && typeof mod === "object") {
    const record = mod as Record<string, unknown>;
    if (Array.isArray(record.default)) return record.default;
    for (const value of Object.values(record)) {
      if (Array.isArray(value)) return value;
    }
  }
  return [];
}

function isComponent(value: unknown): value is ComponentType<ConceptAnimationProps> {
  return typeof value === "function" || (typeof value === "object" && value !== null);
}

function normaliseEntry(value: unknown): RawEntry | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const component = row.Component ?? row.component ?? row.default;
  if (!isComponent(component)) return null;
  const conceptId = typeof row.conceptId === "string" ? row.conceptId : null;
  const title = typeof row.title === "string" ? row.title : null;
  if (!conceptId && !title) return null;
  return {
    conceptId: conceptId ?? title ?? "animation",
    title: title ?? conceptId ?? "Concept animation",
    chapterRef: row.chapterRef ?? row.chapter_ref ?? row.chapter ?? null,
    Component: component,
  };
}

function allEntries(): RawEntry[] {
  const raw = [...pickArray(scienceModule), ...pickArray(mathsModule)];
  const seen = new Set<string>();
  const out: RawEntry[] = [];
  for (const item of raw) {
    const entry = normaliseEntry(item);
    if (!entry) continue;
    const key = `${entry.conceptId}:${entry.title}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(entry);
  }
  return out;
}

const SUBJECT_TOKENS: Record<string, string[]> = {
  science: ["science", "sci", "jesc"],
  maths: ["maths", "math", "mathematics", "jemh"],
};

function tokensFor(subjectId: string): string[] {
  const id = subjectId.toLowerCase();
  return SUBJECT_TOKENS[id] ?? [id];
}

/** Every integer that appears in a string, e.g. "science-ch-9" -> [9]. */
function numbersIn(value: string): number[] {
  const matches = value.match(/\d+/g);
  return matches ? matches.map(Number) : [];
}

function refMentionsOtherSubject(value: string, subjectId: string): boolean {
  const lowered = value.toLowerCase();
  const own = new Set(tokensFor(subjectId));
  const others = Object.entries(SUBJECT_TOKENS)
    .filter(([id]) => id !== subjectId.toLowerCase())
    .flatMap(([, tokens]) => tokens);
  return others.some((token) => !own.has(token) && new RegExp(`(^|[^a-z])${token}([^a-z]|$)`).test(lowered));
}

function matchesChapter(ref: unknown, subjectId: string, chapterNo: number): boolean {
  if (ref === null || ref === undefined) return false;

  if (Array.isArray(ref)) {
    return ref.some((item) => matchesChapter(item, subjectId, chapterNo));
  }

  if (typeof ref === "number") return ref === chapterNo;

  if (typeof ref === "string") {
    const value = ref.trim();
    if (value === "") return false;
    if (/^\d+$/.test(value)) return Number(value) === chapterNo;
    if (refMentionsOtherSubject(value, subjectId)) return false;
    return numbersIn(value).includes(chapterNo);
  }

  if (typeof ref === "object") {
    const row = ref as Record<string, unknown>;
    const subject = row.subject ?? row.subject_id ?? row.subjectId;
    if (typeof subject === "string" && subject.trim() !== "") {
      const lowered = subject.toLowerCase();
      const own = tokensFor(subjectId);
      if (!own.some((token) => lowered === token || lowered.includes(token))) return false;
    }
    const no = row.chapter_no ?? row.chapterNo ?? row.no ?? row.chapter ?? row.number;
    if (typeof no === "number") return no === chapterNo;
    if (typeof no === "string") return numbersIn(no).includes(chapterNo);
    return false;
  }

  return false;
}

export function getChapterAnimations(subjectId: string, chapterNo: number): ChapterAnimations {
  const entries = allEntries();
  const matched: AnimationEntry[] = [];
  const unplaceable: string[] = [];
  for (const entry of entries) {
    if (entry.chapterRef === null || entry.chapterRef === undefined) {
      unplaceable.push(entry.title);
      continue;
    }
    if (matchesChapter(entry.chapterRef, subjectId, chapterNo)) {
      matched.push({ conceptId: entry.conceptId, title: entry.title, Component: entry.Component });
    }
  }
  return { entries: matched, unplaceable, total: entries.length };
}

/** Counts per chapter, for the chapter list on a subject page. */
export function countAnimationsForChapter(subjectId: string, chapterNo: number): number {
  return getChapterAnimations(subjectId, chapterNo).entries.length;
}
