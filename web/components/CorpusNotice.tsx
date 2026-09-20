import { API_BASE } from "@/lib/api";
import type { HealthResult } from "@/lib/corpus";

import RetryButton from "./RetryButton";

/**
 * The corpus banner. This is the state that most often makes a page look empty, so it is rendered
 * on the home page, every subject page and every chapter page, and it distinguishes:
 *   - API unreachable            → "we could not ask"
 *   - API up, 0 chunks           → "nothing has been ingested anywhere"
 *   - API up, chunks elsewhere   → "this subject has not been ingested, others have"
 *   - API up, this subject done  → "n of m chapters ingested"
 */
export default function CorpusNotice({
  health,
  syllabusSource,
  syllabusPath,
  subject,
  detail,
}: {
  health: HealthResult;
  syllabusSource: "api" | "file" | null;
  syllabusPath: string;
  subject?: { name: string; ingestedChapters: number | null; totalChapters: number };
  detail?: string;
}) {
  const chunks = health.ok ? health.data.corpus_chunks : null;
  const provider = health.ok ? health.data.provider : null;

  if (!health.ok) {
    return (
      <section className="notice notice--warn" aria-live="polite">
        <p className="notice__title">The samjho API is not answering</p>
        <p>
          Tried <code>{API_BASE}</code> — {health.error.message}
        </p>
        {syllabusSource === "file" ? (
          <p>
            The chapter list on this page is still real: it was read from <code>{syllabusPath}</code>{" "}
            on this machine, which ships with the repo. Asking questions and taking quizzes need the
            API, so those are unavailable until it is running.
          </p>
        ) : (
          <p>
            Neither the API nor the local syllabus file at <code>{syllabusPath}</code> could be read,
            so there is nothing to show yet.
          </p>
        )}
        <p>
          <RetryButton label="Check again" />
        </p>
      </section>
    );
  }

  if (chunks === 0) {
    return (
      <section className="notice notice--warn" aria-live="polite">
        <p className="notice__title">No textbook text has been ingested yet</p>
        <p>
          The API is running and holds <strong>0 corpus chunks</strong>, so there is nothing for
          samjho to answer from. This is expected on a fresh checkout: the book text has to be
          ingested from your own copy of the book, on your own machine.
        </p>
        <p>
          You can still browse every chapter and section, run the concept animations, and read the
          quizzes&apos; structure. Questions asked in the chat will be refused with a reason rather
          than answered from nothing — that is the intended behaviour, not a bug.
        </p>
      </section>
    );
  }

  const providerLine =
    provider === null ? (
      <span> The API did not report which answer provider is running.</span>
    ) : provider === "retrieval-only" ? (
      <span>
        {" "}
        Answer provider: <code>retrieval-only</code> — no LLM key is configured, so answers are
        assembled from retrieved passages and may be terse. Citations are still real.
      </span>
    ) : (
      <span>
        {" "}
        Answer provider: <code>{provider}</code>.
      </span>
    );

  if (subject && subject.ingestedChapters === 0) {
    return (
      <section className="notice notice--warn" aria-live="polite">
        <p className="notice__title">
          Nothing ingested for {subject.name} yet — other material has been
        </p>
        <p>
          The API holds <strong>{chunks ?? "an unreported number of"} corpus chunks</strong>, but
          none of them belong to {subject.name}. Chapter structure and animations below are
          unaffected; questions about these chapters will be refused with{" "}
          <code>not_in_corpus</code>.
          {detail ? ` (${detail})` : null}
        </p>
      </section>
    );
  }

  if (subject && subject.ingestedChapters !== null && subject.ingestedChapters > 0) {
    return (
      <section className="notice notice--ok" aria-live="polite">
        <p className="notice__title">
          {subject.ingestedChapters} of {subject.totalChapters} chapters of {subject.name} are
          ingested
        </p>
        <p>
          The API holds <strong>{chunks ?? "an unreported number of"} corpus chunks</strong> in
          total.{providerLine}
          {detail ? ` (${detail})` : null}
        </p>
      </section>
    );
  }

  if (subject && subject.ingestedChapters === null) {
    return (
      <section className="notice notice--info" aria-live="polite">
        <p className="notice__title">Ingest state for {subject.name} is unknown</p>
        <p>
          The API is up and holds <strong>{chunks ?? "an unreported number of"} corpus chunks</strong>
          , but it did not say which chapters they belong to.{providerLine}
          {detail ? ` (${detail})` : null}
        </p>
      </section>
    );
  }

  return (
    <section className="notice notice--info" aria-live="polite">
      <p className="notice__title">
        {chunks === null
          ? "The API did not report how much corpus it holds"
          : `Corpus: ${chunks} chunks available to answer from`}
      </p>
      <p>
        {chunks === null
          ? "Health answered, but without a chunk count, so nothing here claims how much material is available."
          : null}{" "}
        Ingest state is reported per chapter inside each subject.{providerLine}
      </p>
    </section>
  );
}
