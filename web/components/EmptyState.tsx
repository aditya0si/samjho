import type { ReactNode } from "react";

import Notice, { type NoticeTone } from "./Notice";

/**
 * An honest empty state. Used everywhere something could have been shown and was not: no corpus
 * ingested, no animations mapped to a chapter, no quiz generated yet, API unreachable.
 * A student must never meet a blank page with no explanation.
 */
export default function EmptyState({
  title,
  tone = "info",
  children,
  action,
}: {
  title: string;
  tone?: NoticeTone;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Notice tone={tone} title={title}>
      {children}
      {action ? <p style={{ marginTop: "0.75rem" }}>{action}</p> : null}
    </Notice>
  );
}
