#!/usr/bin/env python3
"""Section-anchored chunking with page provenance (CONTRACTS.md §2).

A chunk is built from one section's own lines, so it can never span chapters, and it carries the
page range those lines came from. Section boundaries come from `data/syllabus/class10.json` (the
book's own page anchors); the text comes from `ingest.extract_text`, which keeps a page number on
every line.

Sizing: target 700-1000 characters, 15% overlap, split on sentence boundaries where the text
allows it. A sentence longer than the maximum is split at a word boundary — NCERT maths pages
produce runs of formula fragments with no full stop for pages at a time.

The `id` is `subject-chapter-section-page_start` as the contract specifies. When a section is long
enough that two chunks begin on the same page (which happens on any two-page section), the later
one gets a `-2`, `-3` suffix so ids stay unique in the database.

Plain-text ingestion (`--text-dir`) covers the demo corpus: one document per file, no pages to
cite, so `page_start`/`page_end` are 1 and the source URL travels in `source` — the licence
(CC BY-SA 4.0) requires attribution to survive ingestion.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ingest.extract_text import DocumentText, guard_output_path

CHUNK_MIN = 700
CHUNK_MAX = 1000
CHUNK_OVERLAP = 0.15
# A unit (sentence) is capped so that the overlap tail it may be prefixed with cannot push a chunk
# past CHUNK_MAX: worst case is one full unit plus a 15% tail.
UNIT_MAX = CHUNK_MAX - int(CHUNK_MAX * CHUNK_OVERLAP)
MIN_CHUNK_CHARS = 120          # below this a section is a stub; still emitted, never padded
ABBREVIATIONS = {"fig", "figs", "eq", "eqs", "no", "nos", "dr", "mr", "mrs", "ms", "vs", "etc",
                 "cf", "al", "approx", "st", "pp", "p", "ch", "sec", "cm", "mm", "km", "kg", "g"}
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\u2018\u201c])")
DEMO_SUBJECT = "demo"
DEMO_HEADER = re.compile(r"^#\s*([a-z0-9 _-]+):\s*(.*)$", re.IGNORECASE)


@dataclass
class SectionSpan:
    """One section's lines, each tagged with the page it came from."""

    section_no: str
    section_title: str
    lines: list[tuple[int, str]] = field(default_factory=list)
    heading_found: bool = True

    @property
    def pages(self) -> list[int]:
        return sorted({page for page, _ in self.lines})

    @property
    def text(self) -> str:
        return " ".join(line for _, line in self.lines)


def split_sentences(text: str) -> list[str]:
    """Sentence-ish units. Abbreviations ('Fig. 1.2', 'Eq. (1.2)') are glued back on."""
    parts = SENTENCE_SPLIT.split(text)
    merged: list[str] = []
    for part in parts:
        if merged:
            tail = merged[-1].rstrip(".").split()[-1].lower() if merged[-1].rstrip(".") else ""
            if tail in ABBREVIATIONS:
                merged[-1] = f"{merged[-1]} {part}"
                continue
        merged.append(part)
    return [part for part in merged if part.strip()]


def _hard_split(unit: str, limit: int) -> list[str]:
    """Break a unit with no sentence boundary in it, at word boundaries."""
    pieces: list[str] = []
    current = ""
    for word in unit.split():
        if current and len(current) + len(word) + 1 > limit:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def units_with_pages(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """(page, sentence) units, in reading order, splitting sentences that span two lines."""
    units: list[tuple[int, str]] = []
    for page, line in lines:
        for sentence in split_sentences(line):
            for piece in _hard_split(sentence, UNIT_MAX):
                units.append((page, piece))
    return units


def chunk_units(units: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Greedy 700-1000 char chunks with 15% overlap. Returns (page_start, page_end, text).

    Each pass consumes at least one new unit, so the walk always terminates; the overlap tail is
    bounded by 15% of the closed chunk, which is why a chunk never starts on text it already ended
    with more than a sentence or two of.
    """
    chunks: list[tuple[int, int, str]] = []
    index = 0
    carry: list[tuple[int, str]] = []          # overlapping tail from the previous chunk
    while index < len(units):
        window: list[tuple[int, str]] = list(carry)
        size = sum(len(text) + 1 for _, text in window)
        consumed = 0
        while index < len(units):
            page, text = units[index]
            # The size cap is only enforced once this pass has taken something: a chunk must always
            # make progress, or the walk would close the same window forever.
            if consumed and size + len(text) + 1 > CHUNK_MAX:
                break
            window.append((page, text))
            size += len(text) + 1
            index += 1
            consumed += 1
            if size >= CHUNK_MIN:
                break
        body = " ".join(text for _, text in window).strip()
        if not body:
            break
        pages = [page for page, _ in window]
        chunks.append((min(pages), max(pages), body))
        # 15% overlap: the trailing units that fit the budget, or a word-boundary slice of the last
        # unit when a single unit is longer than the whole budget (a page of formula fragments).
        budget = max(int(len(body) * CHUNK_OVERLAP), 1)
        tail: list[tuple[int, str]] = []
        total = 0
        for page, text in reversed(window):
            if total + len(text) + 1 > budget:
                break
            tail.insert(0, (page, text))
            total += len(text) + 1
        if not tail:
            page, text = window[-1]
            cut = text[-budget:]
            if " " in cut:
                cut = cut.split(" ", 1)[1]
            tail = [(page, cut)]
        carry = tail
    return chunks


def section_spans(document: DocumentText, sections: list[dict]) -> list[SectionSpan]:
    """Slice a chapter's pages into per-section line lists, using the syllabus page anchors.

    A section owns the pages from its own start page up to — but not including — the page the next
    section starts on; the last section owns the rest of the chapter. When two sections begin on the
    same page, the first one stops at the second's heading line.
    """
    pages = {page.page: page.text.splitlines() for page in document.pages}
    ordered = sorted(sections, key=lambda s: s.get("page") or 0)
    spans: list[SectionSpan] = []
    for position, section in enumerate(ordered):
        start = section.get("page") or 1
        following = ordered[position + 1] if position + 1 < len(ordered) else None
        if following is None:
            last = max(pages, default=start)
            own = list(range(start, last + 1))
        else:
            end = following.get("page") or start
            own = [start] if end <= start else list(range(start, end))
        span = SectionSpan(section_no=section["no"], section_title=section.get("title", ""))
        for page_no in own:
            lines = pages.get(page_no, [])
            if page_no == start:
                lines, found = _from_heading(lines, section["no"])
                span.heading_found = found
            if following is not None and page_no == own[-1] == start:
                lines = _until_heading(lines, following["no"])
            span.lines.extend((page_no, line) for line in lines if line.strip())
        spans.append(span)
    return spans


def _from_heading(lines: list[str], section_no: str) -> tuple[list[str], bool]:
    """Drop the previous section's tail: start at this section's own heading line."""
    pattern = re.compile(rf"^\s*{re.escape(section_no)}(?![\d.])")
    for index, line in enumerate(lines):
        if pattern.match(line):
            return lines[index:], True
    return lines, False


def _until_heading(lines: list[str], section_no: str) -> list[str]:
    pattern = re.compile(rf"^\s*{re.escape(section_no)}(?![\d.])")
    for index, line in enumerate(lines):
        if pattern.match(line):
            return lines[:index]
    return lines


# --------------------------------------------------------------------------------------
# chunk records (CONTRACTS.md §2)
# --------------------------------------------------------------------------------------


def _record(subject: str, chapter_no: int, chapter_title: str, span: SectionSpan,
            page_start: int, page_end: int, text: str, math_heavy: bool,
            source: str | None = None) -> dict:
    return {
        "id": f"{subject}-{chapter_no}-{span.section_no}-{page_start}",
        "subject": subject,
        "chapter_no": chapter_no,
        "chapter_title": chapter_title,
        "section_no": span.section_no,
        "section_title": span.section_title,
        "page_start": page_start,
        "page_end": page_end,
        "math_heavy": math_heavy,
        "text": text,
        "source": source,          # demo corpus attribution; None for a student's own PDF
    }


def build_chapter_chunks(subject: str, chapter: dict, document: DocumentText,
                         section_titles: dict | None = None) -> list[dict]:
    """All chunks for one chapter, in reading order, with unique ids."""
    sections = chapter.get("sections") or []
    if not sections:
        return []
    if section_titles:
        sections = [dict(s, title=section_titles.get(s["no"], s.get("title", ""))) for s in sections]
    heavy = {page.page for page in document.pages if page.math_heavy}
    records: list[dict] = []
    for span in section_spans(document, sections):
        for page_start, page_end, text in chunk_units(units_with_pages(span.lines)):
            covered = [page for page in range(page_start, page_end + 1)]
            chunk_heavy = sum(1 for page in covered if page in heavy) * 2 >= len(covered)
            records.append(_record(subject, chapter["no"], chapter.get("title", ""), span,
                                   page_start, page_end, text, chunk_heavy))
    return _unique_ids(records)


def _unique_ids(records: list[dict]) -> list[dict]:
    """Two chunks can start on the same page; the contract's id pattern then needs a suffix."""
    seen: dict[str, int] = {}
    for record in records:
        base = record["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            record["id"] = f"{base}-{seen[base]}"
    return records


# --------------------------------------------------------------------------------------
# plain-text ingestion (the demo corpus)
# --------------------------------------------------------------------------------------


def read_text_document(path: Path) -> dict:
    """One demo file -> its header metadata and body text.

    The header is the leading block of '#' lines (source URL, licence, retrieval date, the class 10
    hook). It is stripped from the body — a licence header is not study material — but the source
    URL is kept in `source` so a citation can point at the original article.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header: dict[str, str] = {}
    body_start = 0
    for index, line in enumerate(lines):
        if line.startswith("#"):
            match = DEMO_HEADER.match(line)
            if match:
                header[match.group(1).strip().lower()] = match.group(2).strip()
            body_start = index + 1
            continue
        if line.strip():
            break
        body_start = index + 1
    hook = header.get("class10 hook") or path.stem.replace("-", " ").title()
    section_title = hook.rsplit(":", 1)[-1].strip() if ":" in hook else hook
    return {
        "chapter_title": hook,
        "section_title": section_title,
        "source": header.get("source"),
        "licence": header.get("licence"),
        "body": "\n".join(lines[body_start:]).strip(),
    }


def build_demo_chunks(text_dir: Path) -> list[dict]:
    """Every *.txt in `text_dir` as one document: subject 'demo', chapter 0, section '0.1'.

    Plain text has no pages, so `page_start`/`page_end` are 1 by the contract and no page number is
    invented anywhere else. `math_heavy` is False: the flag describes a PDF page's text layer, and
    there is no page here to measure.
    """
    records: list[dict] = []
    for path in sorted(text_dir.glob("*.txt")):
        document = read_text_document(path)
        if not document["body"]:
            continue
        span = SectionSpan(section_no="0.1", section_title=document["section_title"])
        span.lines = [(1, line) for line in document["body"].splitlines()]
        for page_start, page_end, text in chunk_units(units_with_pages(span.lines)):
            records.append(_record(DEMO_SUBJECT, 0, document["chapter_title"], span,
                                   page_start, page_end, text, False, source=document["source"]))
    return _unique_ids(records)


def write_jsonl(records: list[dict], out_path: Path) -> Path:
    """Write chunk records, one JSON object per line. Contains book text: corpus/ only."""
    target = guard_output_path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text-dir", required=True, help="directory of demo *.txt documents")
    ap.add_argument("--out", default="corpus/chunks/demo.jsonl")
    args = ap.parse_args()
    records = build_demo_chunks(Path(args.text_dir))
    target = write_jsonl(records, Path(args.out))
    lengths = sorted(len(r["text"]) for r in records)
    print(f"{len(records)} chunks from {args.text_dir} -> {target}; "
          f"chars min={lengths[0]} median={lengths[len(lengths) // 2]} max={lengths[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

