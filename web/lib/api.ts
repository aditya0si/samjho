/**
 * The only place the browser and the server talk to the FastAPI service.
 *
 * Every call returns a discriminated `ApiResult` instead of throwing, because every screen in this
 * app has to be able to say *why* it has nothing to show. "The API is down" and "the corpus is
 * empty" are different states and the student sees different words for each.
 */

import type {
  AskAnswer,
  ChapterDetail,
  Citation,
  Health,
  ProgressEntry,
  Quiz,
  QuizQuestion,
  QuizSubmission,
  RefusalReason,
  Syllabus,
  SyllabusSection,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type ApiFailure = {
  kind: "unreachable" | "http" | "malformed";
  /** One line a human can read. Never contains a stack trace or a fabricated explanation. */
  message: string;
  status: number | null;
  url: string;
  data?: unknown;
};

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiFailure };

const DEFAULT_TIMEOUT_MS = 6000;

/** `AbortSignal.timeout` is missing on older browsers; absence must not be reported as "unreachable". */
function timeoutSignal(ms: number): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
    ? AbortSignal.timeout(ms)
    : undefined;
}

function fail(kind: ApiFailure["kind"], message: string, url: string, extra?: Partial<ApiFailure>): {
  ok: false;
  error: ApiFailure;
} {
  return { ok: false, error: { kind, message, status: null, url, ...extra } };
}

async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<ApiResult<T>> {
  const url = `${API_BASE}${path}`;
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(url, {
      ...rest,
      cache: "no-store",
      signal: timeoutSignal(timeoutMs),
      headers: { accept: "application/json", ...(rest.headers ?? {}) },
    });
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    return fail(
      "unreachable",
      `Could not reach the samjho API at ${API_BASE}.`,
      url,
      { data: detail },
    );
  }

  if (!response.ok) {
    let data: unknown = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    return fail("http", `The API answered ${response.status} ${response.statusText} for ${path}.`, url, {
      status: response.status,
      data,
    });
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return fail("malformed", `The API answered ${response.status} but the body was not JSON.`, url);
  }
  return { ok: true, data: body as T };
}

// --- small tolerant readers ------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function firstString(row: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const found = asString(row[key]);
    if (found) return found;
  }
  return null;
}

function firstNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const found = asNumber(row[key]);
    if (found !== null) return found;
  }
  return null;
}

// --- /health ----------------------------------------------------------------------------------

export async function getHealth(): Promise<ApiResult<Health>> {
  const result = await request<unknown>("/health", { timeoutMs: 3000 });
  if (!result.ok) return result;
  const row = asRecord(result.data);
  if (!row) return fail("malformed", "/health did not return a JSON object.", `${API_BASE}/health`);
  return {
    ok: true,
    data: {
      status: asString(row.status) ?? "unknown",
      corpus_chunks: firstNumber(row, ["corpus_chunks", "corpusChunks", "chunks"]),
      provider: asString(row.provider),
    },
  };
}

// --- /subjects --------------------------------------------------------------------------------

/**
 * The syllabus, read from the API when it is up. `fallback` is the local copy of
 * data/syllabus/class10.json that lib/syllabus.ts reads off disk.
 */
export async function getSubjects(): Promise<ApiResult<Syllabus>> {
  const result = await request<unknown>("/subjects");
  if (!result.ok) return result;
  const row = asRecord(result.data);
  const subjects = row?.subjects;
  if (!row || !Array.isArray(subjects)) {
    return fail("malformed", "/subjects did not return a { subjects: [...] } object.", `${API_BASE}/subjects`);
  }
  const parsed = subjects.map(parseSubject).filter((s): s is Syllabus["subjects"][number] => s !== null);
  if (parsed.length === 0) {
    return fail("malformed", "/subjects returned no subjects this app can read.", `${API_BASE}/subjects`);
  }
  return {
    ok: true,
    data: {
      board: asString(row.board) ?? "CBSE",
      class: firstNumber(row, ["class"]) ?? 10,
      note: asString(row.note) ?? undefined,
      subjects: parsed,
    },
  };
}

function parseSubject(value: unknown): Syllabus["subjects"][number] | null {
  const row = asRecord(value);
  if (!row) return null;
  const id = firstString(row, ["id", "subject", "subject_id"]);
  const name = firstString(row, ["name", "title"]) ?? id;
  if (!id || !name) return null;
  const chapters = Array.isArray(row.chapters) ? row.chapters : [];
  return {
    id,
    name,
    book_code: asString(row.book_code) ?? undefined,
    chapters: chapters
      .map(parseChapter)
      .filter((c): c is Syllabus["subjects"][number]["chapters"][number] => c !== null),
  };
}

function parseChapter(value: unknown): Syllabus["subjects"][number]["chapters"][number] | null {
  const row = asRecord(value);
  if (!row) return null;
  const no = firstNumber(row, ["no", "chapter_no", "chapterNo", "number"]);
  const title = firstString(row, ["title", "name"]);
  if (no === null || !title) return null;
  const sections = Array.isArray(row.sections) ? row.sections : [];
  const ingestedFlag = row.ingested ?? row.is_ingested ?? row.has_corpus;
  const chunkCount = firstNumber(row, ["chunk_count", "chunks"]);
  const ingested =
    ingestedFlag === true || (chunkCount !== null && chunkCount > 0)
      ? true
      : ingestedFlag === false || chunkCount === 0
        ? false
        : undefined;
  return {
    no,
    title,
    pdf: asString(row.pdf) ?? undefined,
    status: asString(row.status) ?? undefined,
    pages: firstNumber(row, ["pages"]) ?? undefined,
    ingested,
    chunk_count: chunkCount ?? undefined,
    sections: sections.map(parseSection).filter((s): s is SyllabusSection => s !== null),
  };
}

function parseSection(value: unknown): SyllabusSection | null {
  const row = asRecord(value);
  if (!row) return null;
  const no = firstString(row, ["no", "section_no", "sectionNo", "id"]);
  const title = firstString(row, ["title", "name"]);
  if (!no || !title) return null;
  return { no, title, page: firstNumber(row, ["page", "page_start"]) ?? 0 };
}

// --- /chapters/{subject}/{no} -----------------------------------------------------------------

export async function getChapter(subject: string, no: number): Promise<ApiResult<ChapterDetail>> {
  const path = `/chapters/${encodeURIComponent(subject)}/${no}`;
  const result = await request<unknown>(path, { timeoutMs: 4000 });
  if (!result.ok) return result;
  const row = asRecord(result.data);
  if (!row) return fail("malformed", `${path} did not return a JSON object.`, `${API_BASE}${path}`);

  const chunkCount = firstNumber(row, ["chunk_count", "chunks", "corpus_chunks"]);
  const ingestedFlag = row.ingested ?? row.is_ingested ?? row.has_corpus;
  const ingestStatus = asString(row.ingest_status);
  const ingested =
    ingestedFlag === true || (chunkCount !== null && chunkCount > 0) || ingestStatus === "ingested"
      ? true
      : ingestedFlag === false || chunkCount === 0 || ingestStatus === "not_ingested"
        ? false
        : null;

  const rawSections = row.sections;
  const sections = Array.isArray(rawSections)
    ? rawSections.map(parseSection).filter((s): s is SyllabusSection => s !== null)
    : null;

  return {
    ok: true,
    data: {
      subject: firstString(row, ["subject"]) ?? subject,
      chapter_no: firstNumber(row, ["chapter_no", "chapterNo", "no"]) ?? no,
      chapter_title: firstString(row, ["chapter_title", "title"]),
      ingested,
      chunkCount,
      sections: sections && sections.length > 0 ? sections : null,
      raw: row,
    },
  };
}

// --- POST /ask --------------------------------------------------------------------------------

export async function ask(input: {
  subject: string;
  chapterNo: number;
  question: string;
  topK?: number;
}): Promise<ApiResult<AskAnswer>> {
  const result = await request<unknown>("/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      subject: input.subject,
      chapter_no: input.chapterNo,
      question: input.question,
      top_k: input.topK ?? 6,
    }),
    timeoutMs: 45000,
  });
  if (!result.ok) return result;
  const row = asRecord(result.data);
  if (!row) return fail("malformed", "/ask did not return a JSON object.", `${API_BASE}/ask`);
  const refused = row.refused === true;
  const answer = asString(row.answer) ?? "";
  // A refusal with prose is a contract violation (CONTRACTS §3: "no invented prose"), but a
  // response with neither is also useless — flag it instead of rendering an empty bubble.
  if (!refused && answer === "") {
    return fail("malformed", "/ask returned no answer text and did not set refused: true.", `${API_BASE}/ask`);
  }
  return {
    ok: true,
    data: {
      answer,
      citations: parseCitations(row.citations),
      refused,
      refusalReason: parseRefusalReason(row.refusal_reason),
      suggestedChapter: parseSuggestion(row),
      retrieval: parseRetrieval(row.retrieval),
      provider: asString(row.provider),
    },
  };
}

function parseCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) return [];
  const out: Citation[] = [];
  for (const item of value) {
    const row = asRecord(item);
    if (!row) continue;
    const chapterNo = firstNumber(row, ["chapter_no", "chapterNo"]);
    const sectionNo = firstString(row, ["section_no", "sectionNo"]);
    if (chapterNo === null || !sectionNo) continue;
    const pageStart = firstNumber(row, ["page_start", "pageStart", "page"]);
    const pageEnd = firstNumber(row, ["page_end", "pageEnd"]) ?? pageStart;
    out.push({
      chapter_no: chapterNo,
      section_no: sectionNo,
      page_start: pageStart ?? 0,
      page_end: pageEnd ?? pageStart ?? 0,
      chapter_title: firstString(row, ["chapter_title", "chapterTitle"]),
      section_title: firstString(row, ["section_title", "sectionTitle"]),
      score: firstNumber(row, ["score", "rerank_score"]),
    });
  }
  return out;
}

function parseRefusalReason(value: unknown): RefusalReason {
  const reason = asString(value);
  if (reason === "not_in_corpus" || reason === "no_corpus" || reason === "below_threshold") {
    return reason;
  }
  return reason === null ? "unknown" : "unknown";
}

function parseSuggestion(row: Record<string, unknown>): AskAnswer["suggestedChapter"] {
  const nested = asRecord(row.suggested_chapter) ?? asRecord(row.suggestion) ?? asRecord(row.suggested);
  const source = nested ?? row;
  const title =
    asString(nested?.chapter_title) ??
    firstString(row, ["suggested_chapter_title", "suggestion_title", "cover_chapter"]);
  const no = firstNumber(source, ["chapter_no", "chapterNo", "no"]);
  if (!title && no === null) return null;
  return { chapter_no: no, chapter_title: title ?? "" };
}

function parseRetrieval(value: unknown): AskAnswer["retrieval"] {
  const row = asRecord(value);
  if (!row) return null;
  return {
    mode: asString(row.mode),
    candidates: firstNumber(row, ["candidates"]),
    reranked: firstNumber(row, ["reranked"]),
    took_ms: firstNumber(row, ["took_ms", "tookMs"]),
  };
}

// --- POST /quiz -------------------------------------------------------------------------------

export async function postQuiz(input: {
  subject: string;
  chapterNo: number;
  count: number;
}): Promise<ApiResult<Quiz>> {
  const result = await request<unknown>("/quiz", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ subject: input.subject, chapter_no: input.chapterNo, count: input.count }),
    timeoutMs: 60000,
  });
  if (!result.ok) return result;
  const row = asRecord(result.data);
  if (!row) return fail("malformed", "/quiz did not return a JSON object.", `${API_BASE}/quiz`);
  const rawQuestions = Array.isArray(row.questions)
    ? row.questions
    : Array.isArray(row.quiz)
      ? row.quiz
      : Array.isArray(result.data)
        ? (result.data as unknown[])
        : null;
  if (!rawQuestions) {
    return fail("malformed", "/quiz returned no `questions` array.", `${API_BASE}/quiz`);
  }
  if (rawQuestions.length === 0) {
    // An empty quiz is an honest answer ("nothing to draw from"), not a parse failure — the page
    // has a state for it. Only a non-empty list that we cannot read is a shape problem.
    return {
      ok: true,
      data: {
        subject: firstString(row, ["subject"]) ?? input.subject,
        chapterNo: firstNumber(row, ["chapter_no", "chapterNo"]) ?? input.chapterNo,
        questions: [],
      },
    };
  }
  const questions = rawQuestions
    .map((q, index) => parseQuizQuestion(q, index))
    .filter((q): q is QuizQuestion => q !== null);
  if (questions.length === 0) {
    return fail(
      "malformed",
      "/quiz returned questions in a shape this page cannot render (no question text plus options).",
      `${API_BASE}/quiz`,
    );
  }
  return {
    ok: true,
    data: {
      subject: firstString(row, ["subject"]) ?? input.subject,
      chapterNo: firstNumber(row, ["chapter_no", "chapterNo"]) ?? input.chapterNo,
      questions,
    },
  };
}

function parseQuizQuestion(value: unknown, index: number): QuizQuestion | null {
  const row = asRecord(value);
  if (!row) return null;
  const question = firstString(row, ["question", "prompt", "text", "stem"]);
  if (!question) return null;

  const rawOptions = row.options ?? row.choices ?? row.answers;
  const options: string[] = [];
  if (Array.isArray(rawOptions)) {
    for (const option of rawOptions) {
      if (typeof option === "string") options.push(option);
      else {
        const optionRow = asRecord(option);
        const text = optionRow ? firstString(optionRow, ["text", "label", "value", "option"]) : null;
        if (text) options.push(text);
      }
    }
  }
  if (options.length < 2) return null;

  const explicitIndex = firstNumber(row, [
    "answer_index",
    "answerIndex",
    "correct_index",
    "correctIndex",
    "correct_option",
    "answer",
  ]);
  const answerIndex =
    explicitIndex !== null && explicitIndex >= 0 && explicitIndex < options.length ? explicitIndex : null;

  const sectionRow = asRecord(row.section);
  const sectionNo =
    firstString(row, ["section_no", "sectionNo", "section_id"]) ?? (sectionRow ? firstString(sectionRow, ["no", "section_no"]) : null);
  const sectionTitle =
    firstString(row, ["section_title", "sectionTitle"]) ?? (sectionRow ? firstString(sectionRow, ["title"]) : null);

  return {
    id: firstString(row, ["id", "question_id"]) ?? `q-${index + 1}`,
    question,
    options,
    answerIndex,
    sectionNo,
    sectionTitle,
    explanation: firstString(row, ["explanation", "rationale", "marking_key", "reason"]),
  };
}

// --- /progress --------------------------------------------------------------------------------

export async function getProgress(studentId: string): Promise<ApiResult<ProgressEntry[]>> {
  const path = `/progress/${encodeURIComponent(studentId)}`;
  const result = await request<unknown>(path, { timeoutMs: 5000 });
  if (!result.ok) return result;
  const body = result.data;
  const list = Array.isArray(body)
    ? body
    : Array.isArray(asRecord(body)?.entries)
      ? (asRecord(body)!.entries as unknown[])
      : Array.isArray(asRecord(body)?.history)
        ? (asRecord(body)!.history as unknown[])
        : null;
  if (!list) {
    return fail("malformed", `${path} did not return a list of attempts.`, `${API_BASE}${path}`);
  }
  return { ok: true, data: list.map(parseProgressEntry) };
}

function parseProgressEntry(value: unknown): ProgressEntry {
  const row = asRecord(value) ?? {};
  const missed = row.missed_sections ?? row.missedSections;
  return {
    chapterNo: firstNumber(row, ["chapter_no", "chapterNo", "no"]),
    chapterTitle: firstString(row, ["chapter_title", "chapterTitle", "title"]),
    subject: firstString(row, ["subject"]),
    score: firstNumber(row, ["score", "correct"]),
    total: firstNumber(row, ["total", "count", "out_of"]),
    takenAt: firstString(row, ["taken_at", "takenAt", "created_at", "timestamp"]),
    missedSections: Array.isArray(missed) ? missed.filter((s): s is string => typeof s === "string") : [],
  };
}

/**
 * Persisting an attempt needs a write endpoint. The contract only names
 * `GET /progress/{student_id}`; the obvious counterpart is `POST /progress`. If the API does not
 * implement it the quiz result screen says so rather than pretending the attempt was saved.
 */
export async function saveProgress(submission: QuizSubmission): Promise<ApiResult<unknown>> {
  return request<unknown>("/progress", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      student_id: submission.studentId,
      subject: submission.subject,
      chapter_no: submission.chapterNo,
      score: submission.score,
      total: submission.total,
      missed_sections: submission.missedSections,
      taken_at: submission.takenAt,
    }),
    timeoutMs: 8000,
  });
}
