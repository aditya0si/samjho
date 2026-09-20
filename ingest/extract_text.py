#!/usr/bin/env python3
"""PDF -> page-accurate text for the retrieval corpus, with the provenance citations need.

Reuses the duplicate-layer folding in `ingest/extract_structure.py` (`page_lines`): NCERT PDFs
draw the same line several times at sub-point offsets, so a naive read returns every label five
times over. That folding is the part this module does *not* reinvent.

What it adds, because a corpus needs more than a structure extractor does:

* **page numbers on every line of text** — the unit of provenance is (page, line). Chunks are
  assembled from these lines and carry `page_start`/`page_end` back to the book's own pagination.
* **running headers and footers dropped** — 'Science' and 'Reprint 2026-27' repeat on every page;
  left in, they pollute every chunk and every embedding.
* **repeated label artefacts collapsed** — the fold already removes most of the 5x duplication,
  but a label drawn as two copies inside one cluster survives as 'Activity 1.3 Activity 1.3'.
* **`math_heavy` pages flagged** — NCERT positions math glyphs individually, so `3√2` extracts as
  `3 2` (PLAN §3). Pages whose spans are mostly 1-2 character fragments, or that are dense in
  math-font glyphs and not prose, are marked so the answer path can cite the page instead of
  pretending the text layer is faithful.
* **fragmented headings re-joined** — an all-caps heading folded from partial renders comes out as
  'CHEMICAL EQUA AL EQUATIONS'. Every such line is rebuilt with `ingest.repair_titles` and the
  rebuild is accepted only when it matches the chapter's own body vocabulary.

Nothing here writes into the repository: `guard_output_path` refuses any output path that is not
inside a `corpus/` directory, so extracted book text cannot land in a commit by accident.

Usage:
    python -m ingest.extract_text --pdf <chapter.pdf> --out corpus/pages/<chapter>.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pymupdf  # new name
except ImportError:  # pragma: no cover - older wheels
    import fitz as pymupdf  # type: ignore

from ingest.extract_structure import page_lines  # the duplicate-layer folding, reused as-is
from ingest.repair_titles import (
    NUMBERED_HEADING,
    best_heading_render,
    build_chapter_vocabulary,
    looks_fragmented,
    repair_title,
)

# --- math_heavy rule ------------------------------------------------------------------
# Measured over the 27 real chapter PDFs (434 pages): a page whose spans are at least half
# 1-2 character fragments is a page of positioned glyphs (equations, diagrams, exercises); a page
# that is dense in Symbol/Italic math glyphs *and* not prose-dominated carries formulas whose
# operators the text layer drops. Thresholds are the ones this rule was measured with.
SHORT_SPAN_MAX_CHARS = 2
MATH_HEAVY_SHORT_RATIO = 0.50
MATH_HEAVY_MATHFONT_RATIO = 0.08
MATH_HEAVY_MAX_PROSE_RATIO = 0.70
MATH_FONT_MARKERS = ("symbol", "italic", "mtextra", "math")

# --- line hygiene ---------------------------------------------------------------------
MIN_REPEAT_LINES = 3          # a line must recur this often before it counts as a running head
REPEAT_PAGE_SHARE = 3         # ...or on one page in three, whichever is smaller
RUNNING_LINE_MAX_CHARS = 70
LABEL_MAX_CHARS = 60          # only short lines are treated as labels when de-duplicating
LABELISH = re.compile(r"\b(activity|figure|fig\.?|table|box|example|exercise|solution|caution|"
                      r"note|experiment|problem)\b", re.IGNORECASE)
PAGE_NUMBERISH = re.compile(r"^[\d\s.\-–]+$")


def guard_output_path(path: Path, repo_root: Path | None = None) -> Path:
    """Refuse to write extracted book text anywhere in the repo except a gitignored corpus/.

    The licensing boundary (docs/adr/ADR-001-licensing-boundary.md) is only real if it is
    enforced, so the pipeline refuses rather than trusts.
    """
    resolved = Path(path).resolve()
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved  # outside the repo entirely: a tmp dir, a user's own folder
    if "corpus" not in resolved.parts:
        raise ValueError(
            f"refusing to write extracted book text to {resolved}: only corpus/ (gitignored) "
            "may hold it — see docs/PLAN.md §1"
        )
    return resolved


# --------------------------------------------------------------------------------------
# page-level folding and signals
# --------------------------------------------------------------------------------------


@dataclass
class PageText:
    page: int
    text: str
    chars: int
    lines: int
    math_heavy: bool
    signals: dict
    collapsed_labels: list[str] = field(default_factory=list)
    repaired_headings: list[str] = field(default_factory=list)


@dataclass
class DocumentText:
    pdf: str
    pages: list[PageText]
    book_code: str | None = None
    chapter_no: int | None = None

    @property
    def page_texts(self) -> list[str]:
        return [p.text for p in self.pages]

    @property
    def math_heavy_pages(self) -> int:
        return sum(1 for p in self.pages if p.math_heavy)


def page_signals(page) -> dict:
    """Per-page text-layer health, from one dict extraction.

    Returns glyph and span counts plus four ratios: spans that are 1-2 characters (`short_ratio`),
    glyphs in math fonts (`mathfont_ratio`), digits (`digit_ratio`) and glyphs in long multi-word
    spans (`prose_ratio`).
    """
    spans = 0
    glyphs = 0
    short = 0
    mathfont = 0
    digits = 0
    prose = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"]
                count = len(text)
                if not count:
                    continue
                spans += 1
                glyphs += count
                if count <= SHORT_SPAN_MAX_CHARS:
                    short += 1
                if any(marker in span["font"].lower() for marker in MATH_FONT_MARKERS):
                    mathfont += count
                digits += sum(1 for char in text if char.isdigit())
                if count >= 15 and len(text.split()) >= 3:
                    prose += count
    denom = max(glyphs, 1)
    return {
        "glyphs": glyphs,
        "spans": spans,
        "short_ratio": round(short / max(spans, 1), 3),
        "mathfont_ratio": round(mathfont / denom, 3),
        "digit_ratio": round(digits / denom, 3),
        "prose_ratio": round(prose / denom, 3),
    }


def is_math_heavy(signals: dict) -> bool:
    """The rule documented above: fragmented spans, or formula glyphs on a non-prose page."""
    if signals.get("short_ratio", 0) >= MATH_HEAVY_SHORT_RATIO:
        return True
    return (
        signals.get("mathfont_ratio", 0) >= MATH_HEAVY_MATHFONT_RATIO
        and signals.get("prose_ratio", 1) < MATH_HEAVY_MAX_PROSE_RATIO
    )


def repeated_label(line: str) -> str | None:
    """'Activity 1.3 Activity 1.3' -> 'Activity 1.3'; None when the line is not a repeat."""
    tokens = line.split()
    if len(tokens) < 4 or len(line) > LABEL_MAX_CHARS:
        return None
    for period in range(1, len(tokens) // 2 + 1):
        if len(tokens) % period:
            continue
        chunk = tokens[:period]
        if all(tokens[i : i + period] == chunk for i in range(0, len(tokens), period)):
            label = " ".join(chunk)
            if len(label) >= 3:
                return label
    return None


def collapse_repeated_labels(lines: list[str]) -> tuple[list[str], list[str]]:
    """Drop the duplicate-layer label artefacts that survive the fold.

    Two shapes, both narrow on purpose: a line that is k copies of one short label
    ('Activity 1.3 Activity 1.3'), and a *label-like* short line repeated by the next line
    ('Figure 1.2' twice). Ordinary short lines that legitimately recur on a page — a figure's
    molecule counts, two paragraphs both ending in 'equation.' — are left alone.
    """
    kept: list[str] = []
    collapsed: list[str] = []
    for line in lines:
        label = repeated_label(line)
        if label is not None:
            collapsed.append(line)
            line = label
        if LABELISH.search(line) and kept and kept[-1] == line:
            collapsed.append(line)
            continue
        kept.append(line)
    return kept, collapsed


def drop_running_lines(pages: list[list[str]]) -> set[str]:
    """Lines that repeat at the top or bottom of most pages: running heads, footers, folios."""
    counter: collections.Counter = collections.Counter()
    threshold = max(MIN_REPEAT_LINES, len(pages) // REPEAT_PAGE_SHARE)
    for lines in pages:
        for line in lines[:2] + lines[-2:]:
            text = line.strip()
            if 5 < len(text) < RUNNING_LINE_MAX_CHARS and not PAGE_NUMBERISH.match(text):
                counter[text] += 1
    return {text for text, count in counter.items() if count >= threshold}


# --------------------------------------------------------------------------------------
# document level
# --------------------------------------------------------------------------------------


def extract_document(path: Path, *, repair_headings: bool = True) -> DocumentText:
    """Extract one chapter PDF: page text, page numbers, math flags, heading repair."""
    doc = pymupdf.open(path)
    try:
        folded: list[list[str]] = []
        signals: list[dict] = []
        for index in range(doc.page_count):
            page = doc.load_page(index)
            folded.append([text for text, _, _ in page_lines(page)])
            signals.append(page_signals(page))
        running = drop_running_lines(folded)

        pages: list[PageText] = []
        for number, (lines, sig) in enumerate(zip(folded, signals, strict=False), start=1):
            kept = [line for line in lines if line.strip() and line not in running]
            kept, collapsed = collapse_repeated_labels(kept)
            pages.append(PageText(page=number, text="\n".join(kept), chars=sum(len(x) for x in kept),
                                  lines=len(kept), math_heavy=is_math_heavy(sig), signals=sig,
                                  collapsed_labels=collapsed))

        if repair_headings:
            repaired = repair_fragmented_headings(pages, doc)
            for page in pages:
                page.repaired_headings = repaired.get(page.page, [])
        return DocumentText(pdf=str(path), pages=pages)
    finally:
        doc.close()


def repair_fragmented_headings(pages: list[PageText], doc=None) -> dict[int, list[str]]:
    """Rebuild heading lines the fold split mid-word, verified against the chapter's vocabulary.

    Two routes, both of which have to pass a check before a line is rewritten: re-reading the
    heading's own span cluster and keeping a render that covers the full heading without
    duplicated fragments (`ingest.repair_titles.best_heading_render`), or rebuilding the fragments
    by overlap-join. Either way the rebuilt title must be a phrase the chapter itself uses.

    The leading section number is kept: it is the anchor the chunker uses to find where a section
    starts on a page.
    """
    vocab = build_chapter_vocabulary([p.text for p in pages])
    repaired: dict[int, list[str]] = collections.defaultdict(list)
    for page in pages:
        lines = page.text.splitlines()
        pdf_page = doc[page.page - 1] if doc is not None else None
        for index, line in enumerate(lines):
            heading = NUMBERED_HEADING.match(line)
            if not heading or not looks_fragmented(line):
                continue
            render = None
            if pdf_page is not None:
                try:
                    render = best_heading_render(pdf_page, heading.group(1))
                except Exception:  # a page that cannot be re-read must not stop extraction
                    render = None
            outcome = repair_title(line, vocab, render=render)
            if outcome["status"] != "repaired" or outcome["title"] == line:
                continue
            number = heading.group(1)
            rebuilt = outcome["title"]
            if not rebuilt.startswith(number):
                rebuilt = f"{number} {rebuilt}"
            repaired[page.page].append(f"{line!r} -> {rebuilt!r}")
            lines[index] = rebuilt
        page.text = "\n".join(lines)
        page.chars = sum(len(x) for x in lines)
    return repaired


def write_pages(document: DocumentText, out_path: Path) -> Path:
    """Write one JSONL record per page. Contains book text — corpus/ only."""
    target = guard_output_path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for page in document.pages:
            handle.write(json.dumps({
                "pdf": Path(document.pdf).name,
                "page": page.page,
                "chars": page.chars,
                "lines": page.lines,
                "math_heavy": page.math_heavy,
                "signals": page.signals,
                "collapsed_labels": page.collapsed_labels,
                "repaired_headings": page.repaired_headings,
                "text": page.text,
            }, ensure_ascii=False) + "\n")
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF -> page-accurate text (corpus/ output only)")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-heading-repair", action="store_true")
    args = ap.parse_args()

    started = time.perf_counter()
    document = extract_document(Path(args.pdf), repair_headings=not args.no_heading_repair)
    target = write_pages(document, Path(args.out))
    took = time.perf_counter() - started
    print(f"{document.pdf}: {len(document.pages)} pages, "
          f"{sum(p.chars for p in document.pages)} chars, "
          f"{document.math_heavy_pages} math_heavy, wrote {target} in {took:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
