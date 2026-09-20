/**
 * Turning the answer prose into something a student can click.
 *
 * The answering prompt is told to cite as `[Ch 4 §4.2 p.57]` (PLAN §3), but a model will drift, so
 * this parser accepts the shapes that mean the same thing — `[Ch 4 §4.2 pp.57–58]`,
 * `[Chapter 4 Section 4.2 p.57]`, `[§4.2 p.57]` with the chapter implied — and leaves everything
 * else as plain text. It never invents a citation: a bracket that does not parse stays text.
 *
 * Pure functions, no JSX, so the parsing is testable on its own.
 */

export type CitationToken =
  | { kind: "text"; text: string }
  | {
      kind: "citation";
      chapterNo: number | null;
      sectionNo: string;
      pageStart: number | null;
      pageEnd: number | null;
      label: string;
      raw: string;
    };

const CITATION = new RegExp(
  [
    "\\[\\s*",
    "(?:ch(?:apter)?\\.?\\s*(\\d+)\\s*,?\\s*)?", // optional "Ch 4"
    "(?:§|sec(?:tion)?\\.?\\s*)(\\d+(?:\\.\\d+)*)", // "§4.2" / "Section 4.2"
    "\\s*,?\\s*",
    "(?:pp?\\.?\\s*(\\d+)(?:\\s*[–—-]\\s*(\\d+))?)?", // optional "p.57" / "pp.57–58"
    "\\s*\\]",
  ].join(""),
  "gi",
);

export function tokenizeAnswer(text: string): CitationToken[] {
  const tokens: CitationToken[] = [];
  let cursor = 0;
  CITATION.lastIndex = 0;
  for (;;) {
    const match = CITATION.exec(text);
    if (!match) break;
    if (match.index > cursor) {
      tokens.push({ kind: "text", text: text.slice(cursor, match.index) });
    }
    const chapterNo = match[1] ? Number(match[1]) : null;
    const sectionNo = match[2] ?? "";
    const pageStart = match[3] ? Number(match[3]) : null;
    const pageEnd = match[4] ? Number(match[4]) : pageStart;
    const pageLabel =
      pageStart === null
        ? ""
        : pageEnd !== null && pageEnd !== pageStart
          ? ` pp.${pageStart}–${pageEnd}`
          : ` p.${pageStart}`;
    tokens.push({
      kind: "citation",
      chapterNo,
      sectionNo,
      pageStart,
      pageEnd,
      label: `${chapterNo === null ? "" : `Ch ${chapterNo} `}§${sectionNo}${pageLabel}`,
      raw: match[0],
    });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) tokens.push({ kind: "text", text: text.slice(cursor) });
  return tokens;
}

/** Blank-line separated paragraphs, with single newlines kept as line breaks inside a paragraph. */
export function splitParagraphs(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

export function hasInlineCitations(text: string): boolean {
  return tokenizeAnswer(text).some((token) => token.kind === "citation");
}
