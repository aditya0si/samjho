import { citationHref, citationLabel } from "@/lib/links";
import type { Citation } from "@/lib/types";

/**
 * The passages an answer was built from. These come straight from the API's `citations` array
 * (CONTRACTS §3) — every field is shown as received, including the retrieval score when the API
 * sends one, so the student can see how strong the match was.
 */
export default function CitationList({
  citations,
  subject,
  heading = "Passages this answer was built from",
}: {
  citations: Citation[];
  subject: string;
  heading?: string;
}) {
  if (citations.length === 0) return null;

  return (
    <section aria-label={heading}>
      <h4>{heading}</h4>
      <ul className="chip-list">
        {citations.map((citation, index) => {
          const pageLabel =
            citation.page_end !== citation.page_start
              ? `pages ${citation.page_start}–${citation.page_end}`
              : `page ${citation.page_start}`;
          const title = citation.section_title ?? citation.chapter_title ?? null;
          return (
            <li key={`${citation.section_no}-${citation.page_start}-${index}`}>
              <a
                className="chip"
                href={citationHref({
                  subject,
                  chapter_no: citation.chapter_no,
                  section_no: citation.section_no,
                })}
              >
                {citationLabel(citation)}
              </a>
              {title ? <span className="subtle"> {title}</span> : null}
              <span className="subtle"> · {pageLabel}</span>
              {citation.score !== null ? (
                <span className="subtle"> · match {citation.score.toFixed(2)}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
