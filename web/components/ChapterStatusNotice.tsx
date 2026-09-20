import Link from "next/link";

import type { CorpusStatus } from "@/lib/corpus";

import Notice from "./Notice";
import RetryButton from "./RetryButton";

/**
 * The per-chapter version of the corpus state. Shown on both the chapter page and the study page so
 * that "can samjho answer questions here?" is answered before the student asks one.
 */
export default function ChapterStatusNotice({
  status,
  chapterNo,
  variant,
}: {
  status: CorpusStatus;
  chapterNo: number;
  variant: "chapter" | "study";
}) {
  if (status.ingested === true) {
    return (
      <Notice tone="ok" title={`Chapter ${chapterNo} is ingested`}>
        <p>
          The text of this chapter has been ingested on this machine
          {status.chunkCount !== null ? ` (${status.chunkCount} chunks)` : ""}, so the chat panel can
          answer from it. {status.detail}
        </p>
      </Notice>
    );
  }

  if (status.ingested === false) {
    return (
      <Notice tone="warn" title={`Chapter ${chapterNo} has not been ingested`}>
        <p>
          The structure of this chapter — its sections and page anchors — is real and complete, but
          the text behind it has not been ingested, so there is nothing to answer from yet.{" "}
          {variant === "study"
            ? "Questions asked below will come back refused with no_corpus; the animations, sections and quiz structure are unaffected."
            : "The sections, page anchors, animations and quiz entry point below all work without it."}
        </p>
        <p className="subtle">{status.detail}</p>
        {variant === "chapter" ? (
          <p>
            <Link className="button button--secondary button--small" href="/#licensing">
              What ingestion means here
            </Link>
          </p>
        ) : null}
      </Notice>
    );
  }

  return (
    <Notice tone="info" title={`Ingest state of chapter ${chapterNo} is unknown`}>
      <p>
        samjho could not establish whether this chapter&apos;s text has been ingested, so it will not
        claim either way. {status.detail}
      </p>
      <p>
        <RetryButton label="Check again" />
      </p>
    </Notice>
  );
}
