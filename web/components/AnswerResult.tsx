import Link from "next/link";

import { quizHref, studyHref } from "@/lib/links";
import type { AskAnswer } from "@/lib/types";

import AnswerBody from "./AnswerBody";
import CitationList from "./CitationList";
import Notice from "./Notice";

/**
 * Renders one answered turn: either the cited answer, or — when the API refused — the refusal
 * panel, which is a first-class state here and not an error toast.
 *
 * Split out of ChatPanel so it can be rendered directly (no state, no hooks) by the web builder's
 * render harness, and so the refusal copy lives in one place.
 */
export default function AnswerResult({
  answer,
  subject,
  subjectName,
  chapterNo,
}: {
  answer: AskAnswer;
  subject: string;
  subjectName: string;
  chapterNo: number;
}) {
  if (answer.refused) {
    return (
      <Notice tone="refusal" title="Not covered by your material" live>
        <p>{refusalExplanation(answer.refusalReason)}</p>
        {answer.suggestedChapter ? (
          <p>
            The chapter that would cover it:{" "}
            {answer.suggestedChapter.chapter_no !== null ? (
              <Link href={studyHref(subject, answer.suggestedChapter.chapter_no)}>
                {answer.suggestedChapter.chapter_title ||
                  `Chapter ${answer.suggestedChapter.chapter_no}`}
              </Link>
            ) : (
              <strong>{answer.suggestedChapter.chapter_title}</strong>
            )}
          </p>
        ) : (
          <p>
            The API did not name a chapter that covers it, so samjho will not guess one.{" "}
            <Link href={`/${subject}`}>Browse every {subjectName} chapter</Link> and look for the
            topic yourself — or ingest the chapter if it is missing from your copy.
          </p>
        )}
        <CitationList
          citations={answer.citations}
          subject={subject}
          heading="Passages that were retrieved but did not support an answer"
        />
        <p className="subtle mono">
          refused: true · refusal_reason: {answer.refusalReason}
          {answer.retrieval?.mode ? ` · retrieval: ${answer.retrieval.mode}` : ""}
          {answer.retrieval?.candidates !== null && answer.retrieval?.candidates !== undefined
            ? ` · ${answer.retrieval.candidates} candidates`
            : ""}
          {answer.provider ? ` · provider: ${answer.provider}` : ""}
        </p>
        <p>
          <Link href={quizHref(subject, chapterNo)} className="button button--secondary button--small">
            Try a quiz on this chapter instead
          </Link>
        </p>
      </Notice>
    );
  }

  return (
    <div>
      <AnswerBody text={answer.answer} subject={subject} chapterNo={chapterNo} />
      <CitationList citations={answer.citations} subject={subject} />
      <p className="chat__meta">
        {answer.citations.length === 0
          ? "No citations came back with this answer — treat it with suspicion and check the chapter yourself. "
          : `${answer.citations.length} passage${answer.citations.length === 1 ? "" : "s"} cited. `}
        {answer.provider ? (
          <>
            Provider: <code>{answer.provider}</code>.{" "}
          </>
        ) : null}
        {answer.provider === "retrieval-only"
          ? "No LLM key is configured, so this was assembled from the retrieved passages themselves. "
          : null}
        {answer.retrieval
          ? `Retrieval: ${answer.retrieval.mode ?? "unknown mode"}, ${answer.retrieval.candidates ?? "?"} candidates → ${answer.retrieval.reranked ?? "?"} kept, ${answer.retrieval.took_ms ?? "?"} ms.`
          : null}
      </p>
    </div>
  );
}

export function refusalExplanation(reason: AskAnswer["refusalReason"]): string {
  switch (reason) {
    case "no_corpus":
      return "Nothing has been ingested for this subject on this machine yet, so there is no material to answer from. Ingest your own copy of the book first — until then every question here will be refused like this.";
    case "not_in_corpus":
      return "The passages retrieved from your copy of the book do not cover this question. samjho will not answer it from general knowledge, because a confident wrong answer teaches you something wrong.";
    case "below_threshold":
      return "Some related passages were found, but none matched well enough to answer from confidently. They are listed below so you can judge them yourself.";
    default:
      return "The API refused to answer but did not say why: the response carried no recognised refusal_reason. Treat the question as unanswered.";
  }
}
