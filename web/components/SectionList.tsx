import type { SyllabusSection } from "@/lib/types";
import { sectionAnchor } from "@/lib/util";

/**
 * The section list of a chapter. Each row is anchored with `id="section-<no>"`, which is exactly
 * what citation chips deep-link to (`/subject/[subject]/chapter/[no]#section-[section_no]`,
 * CONTRACTS §5).
 */
export default function SectionList({
  sections,
  emptyNote,
}: {
  sections: SyllabusSection[];
  emptyNote?: string;
}) {
  if (sections.length === 0) {
    return (
      <p className="muted">
        {emptyNote ??
          "No sections are recorded for this chapter in the syllabus structure — the chapter heading exists, but its sub-headings were not extracted."}
      </p>
    );
  }

  return (
    <ul className="section-list">
      {sections.map((section) => (
        <li key={section.no} id={sectionAnchor(section.no)}>
          <a href={`#${sectionAnchor(section.no)}`} className="section-list__no">
            §{section.no}
          </a>
          <span>{section.title}</span>
          {section.page > 0 ? <span className="section-list__page"> — book page {section.page}</span> : null}
        </li>
      ))}
    </ul>
  );
}
