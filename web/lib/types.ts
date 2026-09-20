/**
 * Types shared across the web app.
 *
 * Two kinds of types live here:
 *  1. `Syllabus*` — the factual chapter/section structure from data/syllabus/class10.json
 *     (CONTRACTS §1). No textbook text, ever.
 *  2. The API wire types from CONTRACTS §3/§4. Where the contract freezes a field name we use it
 *     verbatim; where it does not (quiz questions, progress entries) the parser in lib/api.ts is
 *     deliberately tolerant and these types describe what the UI actually needs.
 */

// --- syllabus -------------------------------------------------------------------------------

export type SyllabusSection = {
  no: string;
  title: string;
  page: number;
};

export type SyllabusChapter = {
  no: number;
  title: string;
  pdf?: string;
  status?: string;
  pages?: number;
  /** Only present when the API reports ingest state on the syllabus itself. */
  ingested?: boolean;
  chunk_count?: number;
  sections: SyllabusSection[];
};

export type SyllabusSubject = {
  id: string;
  name: string;
  book_code?: string;
  chapters: SyllabusChapter[];
};

export type Syllabus = {
  board: string;
  class: number;
  note?: string;
  subjects: SyllabusSubject[];
};

// --- /health --------------------------------------------------------------------------------

export type Health = {
  status: string;
  corpus_chunks: number | null;
  provider: string | null;
};

// --- /chapters/{subject}/{no} ---------------------------------------------------------------

export type ChapterDetail = {
  subject: string;
  chapter_no: number;
  chapter_title: string | null;
  /**
   * `true`/`false` only when the API actually said so; `null` when it did not report ingest state.
   * Never guessed from the absence of a field.
   */
  ingested: boolean | null;
  chunkCount: number | null;
  sections: SyllabusSection[] | null;
  raw: unknown;
};

// --- /ask (CONTRACTS §3) --------------------------------------------------------------------

export type Citation = {
  chapter_no: number;
  section_no: string;
  page_start: number;
  page_end: number;
  chapter_title: string | null;
  section_title: string | null;
  score: number | null;
};

export type RefusalReason = "not_in_corpus" | "no_corpus" | "below_threshold" | "unknown";

export type RetrievalInfo = {
  mode: string | null;
  candidates: number | null;
  reranked: number | null;
  took_ms: number | null;
};

export type AskAnswer = {
  answer: string;
  citations: Citation[];
  refused: boolean;
  refusalReason: RefusalReason;
  /** Some APIs name a chapter that does cover the question. Only shown when the API sends one. */
  suggestedChapter: { chapter_no: number | null; chapter_title: string } | null;
  retrieval: RetrievalInfo | null;
  provider: string | null;
};

// --- /quiz ----------------------------------------------------------------------------------

export type QuizQuestion = {
  id: string;
  question: string;
  options: string[];
  /** Index into `options`, or null when the API did not send a usable marking key. */
  answerIndex: number | null;
  sectionNo: string | null;
  sectionTitle: string | null;
  explanation: string | null;
};

export type Quiz = {
  subject: string;
  chapterNo: number;
  questions: QuizQuestion[];
};

// --- /progress ------------------------------------------------------------------------------

export type ProgressEntry = {
  chapterNo: number | null;
  chapterTitle: string | null;
  subject: string | null;
  score: number | null;
  total: number | null;
  takenAt: string | null;
  missedSections: string[];
};

export type QuizSubmission = {
  studentId: string;
  subject: string;
  chapterNo: number;
  score: number;
  total: number;
  missedSections: string[];
  takenAt: string;
};
