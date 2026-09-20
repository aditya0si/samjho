"use client";

import { Component, useState, type ReactNode } from "react";

import { getChapterAnimations } from "@/lib/animations";

import EmptyState from "./EmptyState";

/**
 * Renders the concept animations mapped to this chapter.
 *
 * The registry files are written by the two animation builders (CONTRACTS §6) and may be empty or
 * absent while they work: this host reports that plainly instead of showing a broken frame. A
 * component that throws is caught here so one bad animation cannot take the chapter page down.
 */
export default function AnimationHost({
  subject,
  subjectName,
  chapterNo,
  chapterTitle,
}: {
  subject: string;
  subjectName: string;
  chapterNo: number;
  chapterTitle: string;
}) {
  const { entries, unplaceable, total } = getChapterAnimations(subject, chapterNo);
  const [selected, setSelected] = useState(0);
  const current = entries[selected] ?? entries[0];

  return (
    <section aria-labelledby="animations-heading">
      <h2 id="animations-heading">Concept animations for this chapter</h2>
      <p className="lede">
        Interactive explanations, drawn in the page — no video, no external scripts. Each one is
        keyboard operable, has a &ldquo;what to notice&rdquo; caption, and a &ldquo;try this&rdquo;
        prompt that changes what it shows.
      </p>

      {entries.length === 0 ? (
        <EmptyState title="No concept animation is mapped to this chapter yet">
          <p>
            The animation set covers specific concepts rather than every chapter.{" "}
            {total === 0
              ? "The animation registries are currently empty, so no chapter has one yet."
              : "This chapter's concepts are not among the ones built so far."}{" "}
            Nothing is faked in the meantime: an honest blank beats a placeholder that teaches
            nothing.
          </p>
          <p>
            Sections, page anchors, the chat panel and the quiz for this chapter all work without
            it.
          </p>
        </EmptyState>
      ) : (
        <>
          {entries.length > 1 ? (
            <p>
              <label htmlFor="animation-picker">Animation to show: </label>
              <select
                id="animation-picker"
                value={selected}
                onChange={(event) => setSelected(Number(event.target.value))}
              >
                {entries.map((entry, index) => (
                  <option key={entry.conceptId} value={index}>
                    {entry.title}
                  </option>
                ))}
              </select>
            </p>
          ) : null}

          {current ? (
            <div className="anim__frame">
              <h3>{current.title}</h3>
              <p className="subtle mono">conceptId: {current.conceptId}</p>
              <AnimationErrorBoundary title={current.title}>
                <current.Component />
              </AnimationErrorBoundary>
            </div>
          ) : null}
        </>
      )}

      {unplaceable.length > 0 ? (
        <p className="subtle">
          {unplaceable.length} animation{unplaceable.length === 1 ? "" : "s"} in the registry
          {unplaceable.length === 1 ? " has" : " have"} no chapter reference, so{" "}
          {unplaceable.length === 1 ? "it is" : "they are"} not shown on any chapter page:{" "}
          {unplaceable.join(", ")}.
        </p>
      ) : null}

      {entries.length > 0 && total > entries.length ? (
        <p className="subtle">
          {total - entries.length} further animation{total - entries.length === 1 ? "" : "s"} in the
          registries belong to other chapters.
        </p>
      ) : null}
    </section>
  );
}

class AnimationErrorBoundary extends Component<
  { title: string; children: ReactNode },
  { failed: boolean }
> {
  constructor(props: { title: string; children: ReactNode }) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="notice notice--error" role="alert">
          <p className="notice__title">
            The animation &ldquo;{this.props.title}&rdquo; failed to render
          </p>
          <p>
            It threw while drawing, so it was stopped. The rest of this page — sections, chat and
            quiz — is unaffected. This is a bug in the animation, not a missing feature.
          </p>
          <p>
            <button
              type="button"
              className="button button--secondary button--small"
              onClick={() => this.setState({ failed: false })}
            >
              Try rendering it again
            </button>
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}
