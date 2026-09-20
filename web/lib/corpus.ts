/**
 * "Is the book text actually ingested?" — answered honestly, and cheaply.
 *
 * Order of evidence, strongest first:
 *   1. per-chapter ingest fields on `GET /subjects`, when the API sends them (no extra calls);
 *   2. `GET /chapters/{subject}/{no}` for the chapters in question;
 *   3. `GET /health`'s `corpus_chunks` — if the API says it holds zero chunks, then no chapter can
 *      be ingested, which is a sound negative for every chapter.
 *
 * When none of those settle it, the answer is `null` and the UI says "ingest status unknown"
 * rather than inventing a "not ingested" badge. Server-only.
 */

import "server-only";

import { getChapter, getHealth, type ApiFailure } from "./api";
import type { Health, SyllabusChapter, SyllabusSubject } from "./types";
import { mapLimit } from "./util";

export type CorpusStatus = {
  ingested: boolean | null;
  chunkCount: number | null;
  /** One sentence saying how this was determined. Rendered next to the badge. */
  detail: string;
};

export type HealthResult = { ok: true; data: Health } | { ok: false; error: ApiFailure };

export type SubjectCorpus = {
  statuses: Map<number, CorpusStatus>;
  ingestedChapters: number | null;
  totalChapters: number;
  health: HealthResult;
  /** One sentence for the subject page banner. */
  detail: string;
};

const UNKNOWN_DETAIL = "The API did not report ingest state for this chapter.";

function fromHealthOnly(health: HealthResult): CorpusStatus {
  if (!health.ok) {
    return { ingested: null, chunkCount: null, detail: `Could not ask the API (${health.error.message})` };
  }
  if (health.data.corpus_chunks === 0) {
    return {
      ingested: false,
      chunkCount: 0,
      detail: "The API reports it is holding 0 corpus chunks.",
    };
  }
  return { ingested: null, chunkCount: null, detail: UNKNOWN_DETAIL };
}

/** Status for a single chapter, used by the chapter and study pages. */
export async function getChapterCorpus(
  subjectId: string,
  chapterNo: number,
  chapterFromSyllabus: SyllabusChapter | null,
  health: HealthResult,
): Promise<{ status: CorpusStatus; sections: SyllabusChapter["sections"] | null; chapterTitle: string | null }> {
  const detail = await getChapter(subjectId, chapterNo);
  if (!detail.ok) {
    const status = fromHealthOnly(health);
    return {
      status: {
        ...status,
        detail: `${status.detail} Chapter detail request failed: ${detail.error.message}`,
      },
      sections: chapterFromSyllabus?.sections ?? null,
      chapterTitle: chapterFromSyllabus?.title ?? null,
    };
  }
  const ingested =
    detail.data.ingested !== null
      ? detail.data.ingested
      : health.ok && health.data.corpus_chunks === 0
        ? false
        : null;
  return {
    status: {
      ingested,
      chunkCount: detail.data.chunkCount,
      detail:
        detail.data.ingested !== null
          ? "Reported by GET /chapters/{subject}/{no}."
          : ingested === false
            ? "The API reports it is holding 0 corpus chunks."
            : UNKNOWN_DETAIL,
    },
    sections: detail.data.sections ?? chapterFromSyllabus?.sections ?? null,
    chapterTitle: detail.data.chapter_title ?? chapterFromSyllabus?.title ?? null,
  };
}

export async function getHealthResult(): Promise<HealthResult> {
  const result = await getHealth();
  return result.ok ? { ok: true, data: result.data } : { ok: false, error: result.error };
}

/** Status for every chapter of a subject, used by the subject page. */
export async function getSubjectCorpus(subject: SyllabusSubject): Promise<SubjectCorpus> {
  const health = await getHealthResult();
  const statuses = new Map<number, CorpusStatus>();

  // 1. the syllabus itself told us — cheapest and most direct.
  const flagged = subject.chapters.filter((chapter) => typeof chapter.ingested === "boolean");
  if (flagged.length === subject.chapters.length) {
    for (const chapter of subject.chapters) {
      statuses.set(chapter.no, {
        ingested: chapter.ingested ?? null,
        chunkCount: chapter.chunk_count ?? null,
        detail: "Reported by GET /subjects.",
      });
    }
    const ingestedChapters = subject.chapters.filter((chapter) => chapter.ingested === true).length;
    return {
      statuses,
      ingestedChapters,
      totalChapters: subject.chapters.length,
      health,
      detail: "Ingest state came from the API's own syllabus response.",
    };
  }

  // 2. nothing anywhere: a single /health call settles every chapter as "not ingested".
  if (health.ok && health.data.corpus_chunks === 0) {
    for (const chapter of subject.chapters) {
      statuses.set(chapter.no, {
        ingested: false,
        chunkCount: 0,
        detail: "The API reports it is holding 0 corpus chunks.",
      });
    }
    return {
      statuses,
      ingestedChapters: 0,
      totalChapters: subject.chapters.length,
      health,
      detail: "The API reports it is holding 0 corpus chunks, so no chapter can be ingested yet.",
    };
  }

  // 3. API down, or holding chunks but not saying which chapters they belong to: ask per chapter.
  if (!health.ok) {
    for (const chapter of subject.chapters) {
      statuses.set(chapter.no, {
        ingested: null,
        chunkCount: null,
        detail: `Could not reach the API (${health.error.message})`,
      });
    }
    return {
      statuses,
      ingestedChapters: null,
      totalChapters: subject.chapters.length,
      health,
      detail: "The API could not be reached, so per-chapter ingest state is unknown.",
    };
  }

  const results = await mapLimit(subject.chapters, 4, async (chapter) => {
    const detail = await getChapter(subject.id, chapter.no);
    if (!detail.ok) {
      return {
        no: chapter.no,
        status: { ingested: null, chunkCount: null, detail: `Request failed: ${detail.error.message}` },
      };
    }
    return {
      no: chapter.no,
      status: {
        ingested: detail.data.ingested,
        chunkCount: detail.data.chunkCount,
        detail:
          detail.data.ingested === null
            ? UNKNOWN_DETAIL
            : "Reported by GET /chapters/{subject}/{no}.",
      },
    };
  });
  for (const result of results) statuses.set(result.no, result.status);
  const known = [...statuses.values()].filter((status) => status.ingested !== null);
  return {
    statuses,
    ingestedChapters: known.length === 0 ? null : known.filter((s) => s.ingested === true).length,
    totalChapters: subject.chapters.length,
    health,
    detail: "Ingest state was checked chapter by chapter.",
  };
}
