import Link from "next/link";

import CorpusNotice from "@/components/CorpusNotice";
import EmptyState from "@/components/EmptyState";
import LicensingBoundary from "@/components/LicensingBoundary";
import RetryButton from "@/components/RetryButton";
import { getHealthResult } from "@/lib/corpus";
import { loadSyllabus } from "@/lib/syllabus";

// Every page reads live corpus state, so nothing here is prerendered at build time.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [syllabusLoad, health] = await Promise.all([loadSyllabus(), getHealthResult()]);

  return (
    <>
      <h1>samjho — understand it, don&apos;t memorise it</h1>
      <p className="lede">
        A study companion for CBSE Class 10 Science and Mathematics. Pick a subject, a chapter and a
        section; ask questions and get answers cited back to chapter, section and page in{" "}
        <strong>your own copy</strong> of the book; work through the concept animations; then take a
        quiz and find out which sections you actually missed.
      </p>

      <CorpusNotice
        health={health}
        syllabusSource={syllabusLoad.source}
        syllabusPath={syllabusLoad.filePath}
      />

      {syllabusLoad.syllabus === null ? (
        <EmptyState
          title="The syllabus could not be read"
          tone="warn"
          action={<RetryButton label="Check again" />}
        >
          <p>
            Neither the API nor the local syllabus file could be read, so there is no chapter list to
            show. This is a setup problem, not a missing feature:
          </p>
          <ul>
            <li>API: {syllabusLoad.apiError?.message ?? "no attempt recorded"}</li>
            <li>
              Local file: {syllabusLoad.fileError ?? "read"} (<code>{syllabusLoad.filePath}</code>)
            </li>
          </ul>
          <p>
            The chapter structure ships with the repo at <code>data/syllabus/class10.json</code>; the
            API serves the same structure from <code>GET /subjects</code>.
          </p>
        </EmptyState>
      ) : (
        <section aria-labelledby="subjects-heading">
          <h2 id="subjects-heading">Subjects</h2>
          <p className="subtle">
            {syllabusLoad.syllabus.board} Class {syllabusLoad.syllabus.class} ·{" "}
            {syllabusLoad.syllabus.subjects.length} subjects ·{" "}
            {syllabusLoad.syllabus.subjects.reduce(
              (total, subject) => total + subject.chapters.length,
              0,
            )}{" "}
            chapters
            {syllabusLoad.source === "file" ? (
              <>
                {" "}
                · read from <code>{syllabusLoad.filePath}</code> because the API did not answer
              </>
            ) : (
              <> · read from the API</>
            )}
          </p>
          <ul className="grid">
            {syllabusLoad.syllabus.subjects.map((subject) => (
              <li key={subject.id} className="card">
                <h3>
                  <Link href={`/${subject.id}`}>{subject.name}</Link>
                </h3>
                <p>
                  {subject.chapters.length} chapters
                  {subject.book_code ? (
                    <>
                      {" "}
                      · book <code>{subject.book_code}</code>
                    </>
                  ) : null}
                </p>
                <p>
                  <Link className="button button--secondary button--small" href={`/${subject.id}`}>
                    Open {subject.name}
                  </Link>
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card" id="what-this-is" aria-labelledby="what-this-is-heading">
        <h2 id="what-this-is-heading">What this is</h2>
        <ul>
          <li>
            <strong>Syllabus first.</strong> Every chapter and section of the Class 10 Science and
            Mathematics books, with the page each section starts on, taken from the book&apos;s own
            layout — not from prose.
          </li>
          <li>
            <strong>Cited answers only.</strong> Ask about a chapter and the answer is built from the
            passages retrieved from your ingested copy, with a chip per citation that jumps to{" "}
            <code>/subject/&lt;subject&gt;/chapter/&lt;no&gt;#section-&lt;section&gt;</code>.{" "}
            <strong>Refusal is a feature:</strong> if your material does not cover the question,
            samjho says so, names the chapter that would, and shows nothing invented.
          </li>
          <li>
            <strong>Concept animations.</strong> Interactive, keyboard-operable, drawn in the page:
            ray diagrams, circuits, field lines, unit-circle trigonometry, quadratic sliders and
            more, each mapped to the chapter it explains.
          </li>
          <li>
            <strong>Quizzes that tell you where you went wrong.</strong> Questions are generated only
            from that chapter&apos;s passages; after marking, the sections you missed are listed as
            links back to the chapter.
          </li>
          <li>
            <strong>Honest states.</strong> No corpus ingested, API down, or a subject ingested while
            another is not: each of those says what it is on the page, instead of showing an empty
            screen.
          </li>
        </ul>
      </section>

      <LicensingBoundary />
    </>
  );
}
