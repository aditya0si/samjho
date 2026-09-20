#!/usr/bin/env python3
"""Extract the chapter/section skeleton of a textbook without copying its prose.

Why this exists: the syllabus structure (chapter numbers, section headings, which page a section
starts on) is factual metadata we are allowed to ship. The prose is not ours to redistribute, so
this tool deliberately emits *structure only* — headings with page anchors, never paragraphs. The
retrieval corpus is built separately, on the machine that owns a copy of the book.

How headings are found: by font metrics, not by text patterns. The first attempt matched lines with
a regular expression, which found 17 sections across the Class 10 Science book; the real book has
roughly eighty. NCERT lays headings out at a larger point size than body text, so a heading is a
*line whose median span size exceeds the body size*, or a bold line that looks like a numbered
heading. Running headers and footers are dropped by frequency, because they repeat on every page.

Usage:
    python ingest/extract_structure.py --pdf-dir /path/to/chapter-pdfs --out data/syllabus/class10.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

try:
    import pymupdf  # new name
except ImportError:  # pragma: no cover - older wheels
    import fitz as pymupdf  # type: ignore

# The chapter catalogue is factual metadata published by NCERT/CBSE (book contents listing).
SYLLABUS = {
    "science": {
        "code": "jesc1",
        "title": "Science",
        "chapters": [
            "Chemical Reactions and Equations",
            "Acids, Bases and Salts",
            "Metals and Non-metals",
            "Carbon and its Compounds",
            "Life Processes",
            "Control and Coordination",
            "How do Organisms Reproduce?",
            "Heredity and Evolution",
            "Light - Reflection and Refraction",
            "The Human Eye and the Colourful World",
            "Electricity",
            "Magnetic Effects of Electric Current",
            "Our Environment",
        ],
    },
    "maths": {
        "code": "jemh1",
        "title": "Mathematics",
        "chapters": [
            "Real Numbers",
            "Polynomials",
            "Pair of Linear Equations in Two Variables",
            "Quadratic Equations",
            "Arithmetic Progressions",
            "Triangles",
            "Coordinate Geometry",
            "Introduction to Trigonometry",
            "Some Applications of Trigonometry",
            "Circles",
            "Areas Related to Circles",
            "Surface Areas and Volumes",
            "Statistics",
            "Probability",
        ],
    },
}

# A heading candidate: "1.2 Something" / "1.2.1 Something", or a short unnumbered Title Case line
# that the font metrics already promoted above body size.
NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+){1,2})\s+(\S.{2,70})$")
TITLEISH = re.compile(r"^\s*([A-Z][A-Za-z0-9 ,\-&()'/]{4,60})\s*$")


def page_lines(page) -> list[tuple[str, float, bool]]:
    """Return (text, size, is_bold) per visual line, folding the PDF's duplicate text layers.

    Two defects in NCERT PDFs are handled here, both found by inspecting real spans:

    * headings are drawn several times at sub-point offsets ("1.1 CHEMIC" x4 alongside the real
      "1.1 CHEMICAL EQUA"), and PyMuPDF reports each as a separate line because their y differs by
      0.4pt. Spans are therefore clustered by vertical proximity (3pt tolerance).
    * within a cluster the duplicates are contained in a wider span, so the widest span is kept and
      any span whose x-range sits inside it is dropped before the remainder is read in x-order.
    """
    spans: list[dict] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span["text"].strip():
                    spans.append(span)

    # cluster by vertical centre
    spans.sort(key=lambda s: ((s["bbox"][1] + s["bbox"][3]) / 2, s["bbox"][0]))
    clusters: list[list[dict]] = []
    for span in spans:
        centre = (span["bbox"][1] + span["bbox"][3]) / 2
        for cluster in clusters:
            ref = (cluster[0]["bbox"][1] + cluster[0]["bbox"][3]) / 2
            if abs(centre - ref) <= 3.0:
                cluster.append(span)
                break
        else:
            clusters.append([span])

    out = []
    for cluster in clusters:
        # The same heading exists as several copies a fraction of a point apart. Split them, then
        # prefer the copy with the greatest non-overlapping horizontal coverage: the overlapping
        # copies are the ones that duplicate text when their spans are concatenated.
        copies: dict[float, list[dict]] = collections.defaultdict(list)
        for span in cluster:
            copies[round((span["bbox"][1] + span["bbox"][3]) / 2, 1)].append(span)

        def score(copy: list[dict]) -> float:
            spans_sorted = sorted(copy, key=lambda s: s["bbox"][0])
            coverage = sum(s["bbox"][2] - s["bbox"][0] for s in spans_sorted)
            overlap = 0.0
            for a, b in zip(spans_sorted, spans_sorted[1:], strict=False):
                overlap += max(0.0, a["bbox"][2] - b["bbox"][0])
            return coverage - 2 * overlap

        best = max(copies.values(), key=score)
        best.sort(key=lambda s: s["bbox"][0])
        text = " ".join(s["text"].strip() for s in best).strip()
        text = re.sub(r"\s{2,}", " ", text)
        size = max(s["size"] for s in best)
        bold = any("bold" in s["font"].lower() or (s["flags"] & 2 ** 4) for s in best)
        if text:
            out.append((text, size, bold))
    return out


def body_size(all_lines: list[list[tuple[str, float, bool]]]) -> float:
    """The most common line size in the document is the body text size."""
    counter: collections.Counter[float] = collections.Counter()
    for page in all_lines:
        for text, size, _ in page:
            if len(text) > 40:  # long lines are prose, not headings
                counter[round(size, 1)] += 1
    return counter.most_common(1)[0][0] if counter else 10.0


def extract_chapter(path: Path) -> dict:
    doc = pymupdf.open(path)
    # Explicit index rather than `for p in doc`: the stubs do not declare Document as iterable,
    # and load_page is the documented accessor.
    pages = [page_lines(doc.load_page(i)) for i in range(doc.page_count)]
    body = body_size(pages)

    # Running headers/footers repeat near the top or bottom of most pages: drop those lines.
    repeat: collections.Counter[str] = collections.Counter()
    for page in pages:
        for text, _, _ in page[:2] + page[-2:]:
            if 5 < len(text) < 70 and not re.fullmatch(r"[\d\s.]+", text):
                repeat[text] += 1
    repeated = {text for text, n in repeat.items() if n >= max(3, len(pages) // 3)}

    sections: list[dict] = []
    seen: set[str] = set()
    for pno, page in enumerate(pages, start=1):
        for text, size, bold in page:
            if text in repeated or len(text) < 3:
                continue
            if pno > 6 and not re.match(r"^\s*\d+\.\d+", text):
                continue  # later pages: only numbered headings, to avoid figure captions
            numbered = NUMBERED.match(text)
            # Numbered headings only, AND promoted above body text: figure numbers, exercise
            # question numbers and axis labels ("5.00", "15.0 25.0") otherwise match the pattern.
            if not numbered:
                continue
            promoted = size >= body + 1.2 or bold
            if not promoted:
                continue
            label = numbered.group(2).strip()
            # Drop a duplicated section number inside the label ("1.1 1.1 TYPES OF REACTIONS").
            label = re.sub(rf"^{re.escape(numbered.group(1))}\s*", "", label).strip()
            key = numbered.group(1)
            if key in seen or len(label) < 3:
                continue
            seen.add(key)
            sections.append({"no": key, "title": label, "page": pno})

    return {"pages": doc.page_count, "sections": sections}


def build(pdf_dir: Path, book: str, meta: dict) -> dict:
    chapters = []
    for i, title in enumerate(meta["chapters"], start=1):
        pdf = pdf_dir / f"{meta['code']}{i:02d}.pdf"
        if not pdf.exists():
            chapters.append({"no": i, "title": title, "pdf": pdf.name, "status": "missing"})
            continue
        try:
            got = extract_chapter(pdf)
            chapters.append({"no": i, "title": title, "pdf": pdf.name, "status": "ok", **got})
        except Exception as exc:  # a corrupt download must be visible, not silently skipped
            chapters.append({"no": i, "title": title, "pdf": pdf.name,
                             "status": f"unreadable: {type(exc).__name__}"})
    return {"id": book, "name": meta["title"], "book_code": meta["code"], "chapters": chapters}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--board", default="CBSE")
    ap.add_argument("--class", dest="klass", type=int, default=10)
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    doc = {
        "board": args.board,
        "class": args.klass,
        "note": (
            "Syllabus structure only: chapter and section headings with page anchors, taken from "
            "the book's own layout. No textbook prose is stored here. Textbook text is ingested "
            "locally by whoever owns a copy; see docs/adr/ADR-001-licensing-boundary.md."
        ),
        "subjects": [build(pdf_dir, book, meta) for book, meta in SYLLABUS.items()],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    total = ok = 0
    for subject in doc["subjects"]:
        s_ok = sum(1 for c in subject["chapters"] if c["status"] == "ok")
        s_sec = sum(len(c.get("sections", [])) for c in subject["chapters"])
        print(f"{subject['name']:12} chapters ok {s_ok}/{len(subject['chapters'])}  sections {s_sec}")
        total += len(subject["chapters"])
        ok += s_ok
    print(f"wrote {out} — {ok}/{total} chapters parsed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
