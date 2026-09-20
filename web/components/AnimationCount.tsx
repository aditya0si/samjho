"use client";

import { getChapterAnimations } from "@/lib/animations";

/**
 * How many concept animations this chapter has. A client component on purpose: the registries are
 * written by the animation builders and may be client modules, so they are only ever read from
 * inside the client boundary.
 */
export default function AnimationCount({
  subject,
  chapterNo,
}: {
  subject: string;
  chapterNo: number;
}) {
  const { entries, total } = getChapterAnimations(subject, chapterNo);
  if (entries.length === 0) {
    return (
      <span className="subtle">
        {total === 0 ? "animation registry empty" : "no animation for this chapter yet"}
      </span>
    );
  }
  return (
    <span className="subtle">
      {entries.length} concept animation{entries.length === 1 ? "" : "s"}
    </span>
  );
}
