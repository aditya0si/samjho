import type { ReactNode } from "react";

export type NoticeTone = "info" | "warn" | "ok" | "refusal" | "error";

/**
 * The one place a tone-coloured panel is rendered. Every degraded state in the app goes through
 * here so that "we have nothing to show you" always looks deliberate and always says why.
 */
export default function Notice({
  tone = "info",
  title,
  children,
  live = false,
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children: ReactNode;
  live?: boolean;
}) {
  return (
    <section
      className={`notice notice--${tone}`}
      aria-live={live ? "polite" : undefined}
    >
      {title ? <p className="notice__title">{title}</p> : null}
      {children}
    </section>
  );
}
