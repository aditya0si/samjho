/**
 * URL and label builders for the syllabus routes.
 *
 * Deliberately separate from `lib/syllabus.ts`: that module reads the filesystem, so importing it
 * from a client component drags `node:fs` into the browser bundle. Everything here is pure.
 */

export function subjectHref(subjectId: string): string {
  return `/${subjectId}`;
}

export function chapterHref(subjectId: string, chapterNo: number): string {
  return `/${subjectId}/${chapterNo}`;
}

export function studyHref(subjectId: string, chapterNo: number): string {
  return `/subject/${subjectId}/chapter/${chapterNo}`;
}

export function quizHref(subjectId: string, chapterNo: number): string {
  return `/subject/${subjectId}/chapter/${chapterNo}/quiz`;
}

/** `[Ch 1 §1.1 p.2]` — the citation format the answer prompt is told to use (PLAN §3). */
export function citationLabel(input: {
  chapter_no: number;
  section_no: string;
  page_start: number;
  page_end?: number;
}): string {
  const pages =
    input.page_end !== undefined && input.page_end !== input.page_start
      ? `pp.${input.page_start}–${input.page_end}`
      : `p.${input.page_start}`;
  return `Ch ${input.chapter_no} §${input.section_no} ${pages}`;
}

/** The deep link a citation chip points at (CONTRACTS §5). */
export function citationHref(input: {
  subject: string;
  chapter_no: number;
  section_no: string;
}): string {
  const base = `/subject/${encodeURIComponent(input.subject)}/chapter/${input.chapter_no}`;
  return `${base}#section-${encodeURIComponent(input.section_no)}`;
}
