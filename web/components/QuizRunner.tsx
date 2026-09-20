"use client";

import { useState } from "react";

import { postQuiz, saveProgress, type ApiFailure } from "@/lib/api";
import { ensureStudentId } from "@/lib/student";
import type { Quiz, QuizQuestion } from "@/lib/types";
import { sectionAnchor } from "@/lib/util";

import EmptyState from "./EmptyState";
import Notice from "./Notice";

type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved" }
  | { status: "failed"; message: string };

export default function QuizRunner({
  subject,
  chapterNo,
  chapterTitle,
  sections,
  corpusKnownEmpty,
}: {
  subject: string;
  chapterNo: number;
  chapterTitle: string;
  sections: { no: string; title: string }[];
  corpusKnownEmpty: boolean;
}) {
  const [count, setCount] = useState(5);
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [submitted, setSubmitted] = useState(false);
  const [save, setSave] = useState<SaveState>({ status: "idle" });

  const gradable = quiz ? quiz.questions.filter((question) => question.answerIndex !== null) : [];
  const ungradable = quiz ? quiz.questions.length - gradable.length : 0;
  const missed = gradable.filter((question) => answers[question.id] !== question.answerIndex);
  const score = gradable.length - missed.length;
  const missedSections = [
    ...new Set(missed.map((question) => question.sectionNo).filter((no): no is string => no !== null)),
  ];
  const allAnswered = quiz ? quiz.questions.every((question) => answers[question.id] !== undefined) : false;

  async function generate() {
    setLoading(true);
    setError(null);
    setSubmitted(false);
    setSave({ status: "idle" });
    setAnswers({});
    const result = await postQuiz({ subject, chapterNo, count });
    if (result.ok) {
      setQuiz(result.data);
    } else {
      setQuiz(null);
      setError(result.error);
    }
    setLoading(false);
  }

  async function submit() {
    if (!quiz || submitted) return;
    setSubmitted(true);
    if (gradable.length === 0) {
      setSave({
        status: "failed",
        message:
          "Nothing to record: none of these questions came back with a marking key, so no score exists to save.",
      });
      return;
    }
    const studentId = ensureStudentId();
    if (!studentId) {
      setSave({
        status: "failed",
        message:
          "This browser refused to store a student id (localStorage is unavailable), so the attempt could not be attributed to you.",
      });
      return;
    }
    setSave({ status: "saving" });
    const result = await saveProgress({
      studentId,
      subject,
      chapterNo,
      score,
      total: gradable.length,
      missedSections,
      takenAt: new Date().toISOString(),
    });
    setSave(result.ok ? { status: "saved" } : { status: "failed", message: result.error.message });
  }

  return (
    <section aria-labelledby="quiz-heading">
      <h2 id="quiz-heading">Quiz: {chapterTitle}</h2>

      {corpusKnownEmpty ? (
        <Notice tone="warn" title="No corpus ingested, so there is nothing to build questions from">
          <p>
            Quiz questions are generated only from this chapter&apos;s ingested passages. With an
            empty corpus the API will refuse; you can still try, and the refusal will say so.
          </p>
        </Notice>
      ) : null}

      {!quiz ? (
        <div className="card card--quiet">
          <p>
            Questions are generated from the passages ingested for chapter {chapterNo} only, and each
            one carries the section it came from. Nothing is drawn from other chapters or from
            general knowledge.
          </p>
          <p className="row">
            <label htmlFor="quiz-count">Number of questions: </label>
            <select
              id="quiz-count"
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
              disabled={loading}
            >
              {[3, 5, 8].map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <button type="button" className="button" onClick={() => void generate()} disabled={loading}>
              {loading ? "Generating…" : "Generate quiz"}
            </button>
          </p>
          <p className="subtle" aria-live="polite">
            {loading ? "Reading this chapter's ingested passages and writing questions…" : null}
          </p>
        </div>
      ) : null}

      {error ? (
        <Notice tone="error" title="No quiz could be generated">
          <p>{error.message}</p>
          <p className="subtle">
            Request went to <code>{error.url}</code>. If this chapter has not been ingested, the API
            has nothing to draw questions from — that is a corpus problem, not a broken page.
          </p>
        </Notice>
      ) : null}

      {quiz && quiz.questions.length === 0 ? (
        <EmptyState title="The API returned an empty quiz">
          <p>
            No questions came back for this chapter. Nothing is invented to fill the gap.
          </p>
        </EmptyState>
      ) : null}

      {quiz && quiz.questions.length > 0 ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {ungradable > 0 ? (
            <Notice tone="warn" title={`${ungradable} question(s) cannot be graded`}>
              <p>
                The API sent no marking key for {ungradable === 1 ? "one question" : `${ungradable} questions`},
                so {ungradable === 1 ? "it is" : "they are"} shown with the answer you picked and the
                section to check in the book, but left out of the score.{" "}
                {gradable.length === 0
                  ? "With no marking keys at all, no score can be computed."
                  : `The score covers the ${gradable.length} gradable question${gradable.length === 1 ? "" : "s"}.`}
              </p>
            </Notice>
          ) : null}

          <ol className="link-list" style={{ listStyle: "decimal", paddingLeft: "1.25rem" }}>
            {quiz.questions.map((question, index) => (
              <li key={question.id} style={{ borderBottom: 0, paddingTop: "0.75rem" }}>
                <QuizQuestionField
                  question={question}
                  index={index}
                  total={quiz.questions.length}
                  selected={answers[question.id]}
                  submitted={submitted}
                  onSelect={(optionIndex) =>
                    setAnswers((previous) => ({ ...previous, [question.id]: optionIndex }))
                  }
                />
              </li>
            ))}
          </ol>

          {!submitted ? (
            <p>
              <button type="submit" className="button" disabled={!allAnswered}>
                Check answers
              </button>{" "}
              {!allAnswered ? (
                <span className="subtle">Answer every question to check your answers.</span>
              ) : null}
            </p>
          ) : null}
        </form>
      ) : null}

      {submitted && quiz ? (
        <section aria-labelledby="quiz-result-heading" aria-live="polite">
          <h3 id="quiz-result-heading">Result</h3>
          {gradable.length === 0 ? (
            <Notice tone="warn" title="No score could be computed">
              <p>
                None of these questions came with a marking key, so samjho will not invent a score.
                Use the section references below to check your answers against the book.
              </p>
            </Notice>
          ) : (
            <p className="quiz__score">
              {score} / {gradable.length} correct
              <span className="subtle">
                {" "}
                ({Math.round((score / gradable.length) * 100)}%)
                {ungradable > 0 ? ` · ${ungradable} question(s) not graded` : ""}
              </span>
            </p>
          )}

          {missedSections.length > 0 ? (
            <div>
              <h4>Sections to revisit</h4>
              <ul className="chip-list">
                {missedSections.map((no) => {
                  const known = sections.find((section) => section.no === no);
                  return (
                    <li key={no}>
                      <a className="chip" href={`#${sectionAnchor(no)}`}>
                        §{no}
                      </a>
                      <span className="subtle">
                        {" "}
                        {known ? known.title : "not in this chapter's section list"}
                      </span>
                    </li>
                  );
                })}
              </ul>
              <p className="subtle">
                These are the sections the questions you missed came from. Read them, then ask the
                chat panel about anything still unclear.
              </p>
            </div>
          ) : gradable.length > 0 ? (
            <p>Every gradable question was answered correctly.</p>
          ) : null}

          <ul className="quiz__review">
            {quiz.questions.map((question, index) => {
              const chosen = answers[question.id];
              const correct = question.answerIndex !== null && chosen === question.answerIndex;
              return (
                <li key={question.id} className={correct ? "is-right" : "is-wrong"}>
                  <p>
                    <strong>
                      {index + 1}. {question.question}
                    </strong>
                  </p>
                  <p>
                    Your answer:{" "}
                    {chosen === undefined ? <em>not answered</em> : question.options[chosen] ?? "—"}
                    {correct ? " ✓" : null}
                  </p>
                  {question.answerIndex !== null ? (
                    <p>
                      Correct answer: {question.options[question.answerIndex] ?? "—"}
                    </p>
                  ) : (
                    <p className="subtle">
                      No marking key was sent for this question, so samjho cannot say which option is
                      right. Check it in the book.
                    </p>
                  )}
                  {question.explanation ? <p>{question.explanation}</p> : null}
                  {question.sectionNo ? (
                    <p className="subtle">
                      From{" "}
                      <a href={`#${sectionAnchor(question.sectionNo)}`}>
                        §{question.sectionNo}
                        {question.sectionTitle ? ` ${question.sectionTitle}` : ""}
                      </a>
                    </p>
                  ) : (
                    <p className="subtle">The API did not say which section this came from.</p>
                  )}
                </li>
              );
            })}
          </ul>

          <p aria-live="polite">
            {save.status === "saving" ? "Saving this attempt to your progress…" : null}
            {save.status === "saved" ? "Attempt saved to your progress." : null}
          </p>
          {save.status === "failed" ? (
            <Notice tone="error" title="This attempt was not saved">
              <p>{save.message}</p>
              <p className="subtle">
                The result above is still yours to read and act on — what is missing is only the
                record of it in the progress store.
              </p>
            </Notice>
          ) : null}

          <p className="row">
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setQuiz(null);
                setSubmitted(false);
                setAnswers({});
                setSave({ status: "idle" });
                setError(null);
              }}
            >
              Generate a different quiz
            </button>
          </p>
        </section>
      ) : null}
    </section>
  );
}

function QuizQuestionField({
  question,
  index,
  total,
  selected,
  submitted,
  onSelect,
}: {
  question: QuizQuestion;
  index: number;
  total: number;
  selected: number | undefined;
  submitted: boolean;
  onSelect: (optionIndex: number) => void;
}) {
  return (
    <fieldset className="quiz__question">
      <legend>
        Question {index + 1} of {total}
      </legend>
      <p>{question.question}</p>
      <ul className="quiz__options">
        {question.options.map((option, optionIndex) => (
          <li key={`${question.id}-${optionIndex}`}>
            <label>
              <input
                type="radio"
                name={`q-${question.id}`}
                value={optionIndex}
                checked={selected === optionIndex}
                disabled={submitted}
                onChange={() => onSelect(optionIndex)}
              />
              <span>{option}</span>
            </label>
          </li>
        ))}
      </ul>
    </fieldset>
  );
}
