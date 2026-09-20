"use client";

import { useState } from "react";

import { ask, type ApiFailure } from "@/lib/api";
import type { AskAnswer } from "@/lib/types";

import AnswerResult from "./AnswerResult";
import Notice from "./Notice";

type Turn =
  | { id: number; question: string; state: "pending" }
  | { id: number; question: string; state: "answered"; answer: AskAnswer }
  | { id: number; question: string; state: "failed"; error: ApiFailure };

let turnSeq = 0;
const nextTurnId = () => ++turnSeq;

export default function ChatPanel({
  subject,
  subjectName,
  chapterNo,
  chapterTitle,
  suggestedQuestions,
  corpusKnownEmpty,
}: {
  subject: string;
  subjectName: string;
  chapterNo: number;
  chapterTitle: string;
  suggestedQuestions: string[];
  corpusKnownEmpty: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  async function submit(rawQuestion: string) {
    const trimmed = rawQuestion.trim();
    if (trimmed === "" || busy) return;
    const id = nextTurnId();
    setTurns((previous) => [...previous, { id, question: trimmed, state: "pending" }]);
    setQuestion("");
    setBusy(true);
    const result = await ask({ subject, chapterNo, question: trimmed });
    setTurns((previous) =>
      previous.map((turn) =>
        turn.id === id
          ? result.ok
            ? { id, question: trimmed, state: "answered", answer: result.data }
            : { id, question: trimmed, state: "failed", error: result.error }
          : turn,
      ),
    );
    setBusy(false);
  }

  return (
    <section className="chat" aria-labelledby="ask-heading">
      <h2 id="ask-heading">Ask about this chapter</h2>
      <p className="lede">
        Answers are built only from the passages retrieved from the ingested copy of your book for
        this chapter. If they do not cover your question, samjho says so instead of guessing.
      </p>

      {corpusKnownEmpty ? (
        <Notice tone="warn" title="Nothing is ingested for this subject yet">
          <p>
            Asking is still available, but every question will come back refused with{" "}
            <code>no_corpus</code> until the book text is ingested on this machine. The sections,
            animations and quiz structure below do not depend on the corpus.
          </p>
        </Notice>
      ) : null}

      <form
        className="chat__form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <label className="chat__label" htmlFor="chat-question">
          Your question about {chapterTitle}
        </label>
        <input
          id="chat-question"
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="e.g. why does the silver chloride turn grey in sunlight?"
          autoComplete="off"
        />
        <p className="chat__hint">
          Press Enter to ask. The question is sent to the samjho API with this chapter&apos;s
          context; it is not sent anywhere else.
        </p>
        <p>
          <button type="submit" className="button" disabled={busy || question.trim() === ""}>
            {busy ? "Searching your material…" : "Ask"}
          </button>
        </p>
      </form>

      {suggestedQuestions.length > 0 ? (
        <div>
          <h3>Questions this chapter&apos;s sections suggest</h3>
          <p className="subtle">
            Built from the section headings of this chapter, so they are always about something the
            chapter actually contains.
          </p>
          <ul className="chat__suggestions">
            {suggestedQuestions.map((suggestion) => (
              <li key={suggestion}>
                <button
                  type="button"
                  className="button button--secondary button--small"
                  disabled={busy}
                  onClick={() => void submit(suggestion)}
                >
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div aria-live="polite" aria-busy={busy}>
        {turns.length === 0 ? (
          <p className="muted">No questions asked in this session yet.</p>
        ) : (
          turns.map((turn) => (
            <article className="chat__turn" key={turn.id}>
              <p className="chat__question">
                <span className="visually-hidden">Question: </span>
                {turn.question}
              </p>
              {turn.state === "pending" ? (
                <p className="chat__status">
                  <span className="spinner" aria-hidden="true" />
                  Searching your material for this chapter…
                </p>
              ) : null}
              {turn.state === "failed" ? (
                <Notice tone="error" title="That request did not complete">
                  <p>{turn.error.message}</p>
                  <p className="subtle">
                    The request went to <code>{turn.error.url}</code>. Nothing was answered, so
                    nothing is shown — this is not a refusal, it is a failure to ask.
                  </p>
                  <p>
                    <button
                      type="button"
                      className="button button--secondary button--small"
                      disabled={busy}
                      onClick={() => {
                        setTurns((previous) => previous.filter((item) => item.id !== turn.id));
                        void submit(turn.question);
                      }}
                    >
                      Ask again
                    </button>
                  </p>
                </Notice>
              ) : null}
              {turn.state === "answered" ? (
                <AnswerResult
                  answer={turn.answer}
                  subject={subject}
                  subjectName={subjectName}
                  chapterNo={chapterNo}
                />
              ) : null}
            </article>
          ))
        )}
      </div>
    </section>
  );
}
