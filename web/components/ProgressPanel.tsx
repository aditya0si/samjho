"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getProgress, type ApiFailure } from "@/lib/api";
import { ensureStudentId, getStudentId } from "@/lib/student";
import { quizHref } from "@/lib/links";
import type { ProgressEntry } from "@/lib/types";
import { formatRelativeTime } from "@/lib/util";

import EmptyState from "./EmptyState";
import Notice from "./Notice";

type State =
  | { status: "loading" }
  | { status: "no-id" }
  | { status: "error"; error: ApiFailure }
  | { status: "ready"; entries: ProgressEntry[] };

/**
 * Quiz history for this chapter, from `GET /progress/{student_id}` (CONTRACTS §4).
 *
 * There is no login in v1: the student id is generated in this browser and kept in localStorage.
 * The panel says so, because a progress screen that looks like an account but is not would be a lie.
 */
export default function ProgressPanel({
  subject,
  chapterNo,
  chapterTitle,
}: {
  subject: string;
  chapterNo: number;
  chapterTitle: string;
}) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [studentId, setStudentId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = getStudentId() ?? ensureStudentId();
    setStudentId(id);
    if (!id) {
      setState({ status: "no-id" });
      return;
    }
    void getProgress(id).then((result) => {
      if (cancelled) return;
      if (result.ok) setState({ status: "ready", entries: result.data });
      else setState({ status: "error", error: result.error });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const forChapter =
    state.status === "ready"
      ? state.entries.filter((entry) => entry.chapterNo === chapterNo || entry.chapterNo === null)
      : [];
  const gradable = forChapter.filter((entry) => entry.score !== null && entry.total !== null);
  const best = gradable.reduce<number | null>((acc, entry) => {
    const ratio = entry.score! / entry.total!;
    return acc === null || ratio > acc ? ratio : acc;
  }, null);

  return (
    <section aria-labelledby="progress-heading">
      <h2 id="progress-heading">Your attempts on this chapter</h2>

      {state.status === "loading" ? <p className="muted">Checking your saved attempts…</p> : null}

      {state.status === "no-id" ? (
        <EmptyState title="This browser will not store a student id" tone="warn">
          <p>
            Progress is keyed on an id kept in this browser&apos;s local storage, and it is not
            available (private mode, or storage blocked). Quizzes still work and are still marked —
            only the record of them cannot be kept.
          </p>
        </EmptyState>
      ) : null}

      {state.status === "error" ? (
        <Notice tone="warn" title="Your progress could not be loaded">
          <p>{state.error.message}</p>
          <p className="subtle">
            Request went to <code>{state.error.url}</code>. Quiz results on this page are computed
            from the questions themselves and do not depend on this.
          </p>
        </Notice>
      ) : null}

      {state.status === "ready" && forChapter.length === 0 ? (
        <EmptyState title={`No attempt recorded yet for chapter ${chapterNo}`}>
          <p>
            Nothing has been saved against <code>{studentId ?? "this device"}</code> for this
            chapter. {state.entries.length > 0 ? `${state.entries.length} attempt(s) exist for other chapters.` : null}
          </p>
          <p>
            <Link className="button button--secondary button--small" href={quizHref(subject, chapterNo)}>
              Take a quiz on {chapterTitle}
            </Link>
          </p>
        </EmptyState>
      ) : null}

      {state.status === "ready" && forChapter.length > 0 ? (
        <>
          <p>
            {forChapter.length} attempt{forChapter.length === 1 ? "" : "s"} recorded
            {best !== null ? ` · best ${Math.round(best * 100)}%` : ""}.
          </p>
          <table className="table">
            <caption>Quiz attempts for chapter {chapterNo}, newest first as returned by the API</caption>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Score</th>
                <th scope="col">Sections missed</th>
              </tr>
            </thead>
            <tbody>
              {forChapter.map((entry, index) => (
                <tr key={index}>
                  <td>{formatRelativeTime(entry.takenAt) ?? "time not reported"}</td>
                  <td>
                    {entry.score !== null && entry.total !== null
                      ? `${entry.score} / ${entry.total}`
                      : "not reported"}
                  </td>
                  <td>
                    {entry.missedSections.length === 0 ? (
                      <span className="subtle">none</span>
                    ) : (
                      entry.missedSections.join(", ")
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      <p className="subtle">
        Keyed on <code>{studentId ?? "no id"}</code> — an id created in this browser, not an account.
        Clearing site data clears this history.
      </p>
    </section>
  );
}
