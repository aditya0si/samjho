#!/usr/bin/env python3
"""End-to-end ingestion driver: PDFs and/or plain text -> page text -> chunks, with counts.

    # the real books (the student's own copies; output stays in the gitignored corpus/)
    python -m ingest.cli --pdf-dir C:/path/to/ncert-books --repair-titles

    # the demo corpus
    python -m ingest.cli --text-dir data/demo-corpus

Every number it prints is measured in that run: pages read, chunks written, the share of pages and
chunks flagged math_heavy, chunk length spread, and how many fragmented titles the repair pass
fixed. Nothing is estimated, and nothing is written outside `corpus/` (see `guard_output_path`).
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from ingest import chunk as chunking
from ingest.extract_text import DocumentText, extract_document, write_pages
from ingest.repair_titles import repair_syllabus

DEFAULT_SYLLABUS = "data/syllabus/class10.json"
DEFAULT_OUT = "corpus"


def _spread(values: list[int]) -> str:
    if not values:
        return "n/a"
    ordered = sorted(values)
    return f"min={ordered[0]} median={ordered[len(ordered) // 2]} max={ordered[-1]}"


def _share(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.1f}%)" if whole else "0/0"


def ingest_pdfs(pdf_dir: Path, syllabus: dict, out_dir: Path, *, repair: bool,
                repair_headings: bool, limit: int | None = None) -> dict:
    """Extract, (optionally) repair titles, and chunk every chapter PDF named by the syllabus."""
    started = time.perf_counter()
    documents: dict[tuple[str, int], DocumentText] = {}
    missing: list[str] = []
    per_subject: dict[str, dict] = {}
    page_texts: dict[tuple[str, int], list[str]] = {}

    for subject in syllabus["subjects"]:
        code = subject["book_code"]
        chunks: list[dict] = []
        pages = heavy_pages = 0
        processed = 0
        for chapter in subject["chapters"]:
            if limit is not None and processed >= limit:
                break
            pdf_path = pdf_dir / f"{code}{chapter['no']:02d}.pdf"
            if not pdf_path.exists():
                missing.append(pdf_path.name)
                continue
            document = extract_document(pdf_path, repair_headings=repair_headings)
            documents[(code, chapter["no"])] = document
            page_texts[(code, chapter["no"])] = document.page_texts
            write_pages(document, out_dir / "pages" / f"{code}{chapter['no']:02d}.jsonl")
            pages += len(document.pages)
            heavy_pages += document.math_heavy_pages
            chunks.extend(chunking.build_chapter_chunks(subject["id"], chapter, document))
            processed += 1
        if chunks:
            chunking.write_jsonl(chunks, out_dir / "chunks" / f"{subject['id']}.jsonl")
        per_subject[subject["id"]] = {"chapters": processed, "pages": pages,
                                      "math_heavy_pages": heavy_pages, "chunks": chunks,
                                      "chapter_total": len(subject["chapters"])}

    title_report: list[dict] = []
    if repair:
        syllabus, title_report = repair_syllabus(syllabus, pdf_dir, page_texts)

    took = time.perf_counter() - started
    return {"per_subject": per_subject, "title_report": title_report, "missing": missing,
            "took_s": round(took, 1), "documents": len(documents)}


def ingest_text(text_dir: Path, out_dir: Path) -> dict:
    started = time.perf_counter()
    records = chunking.build_demo_chunks(text_dir)
    target = chunking.write_jsonl(records, out_dir / "chunks" / f"{chunking.DEMO_SUBJECT}.jsonl")
    sources = {record["source"] for record in records}
    return {"chunks": records, "target": str(target), "sources": len(sources),
            "took_s": round(time.perf_counter() - started, 1)}


def report_pdf(summary: dict) -> None:
    total_chunks: list[dict] = []
    for subject_id, data in summary["per_subject"].items():
        print(f"{subject_id:8s} chapters {data['chapters']}/{data['chapter_total']}  "
              f"pages {data['pages']}  math_heavy pages {_share(data['math_heavy_pages'], data['pages'])}  "
              f"chunks {len(data['chunks'])}")
        total_chunks.extend(data["chunks"])
    if summary["missing"]:
        print(f"missing PDFs ({len(summary['missing'])}): {', '.join(sorted(summary['missing']))}")
    heavy_chunks = sum(1 for record in total_chunks if record["math_heavy"])
    lengths = [len(record["text"]) for record in total_chunks]
    in_band = sum(1 for length in lengths if chunking.CHUNK_MIN <= length <= chunking.CHUNK_MAX)
    print(f"total    chapters {sum(d['chapters'] for d in summary['per_subject'].values())}  "
          f"pages {sum(d['pages'] for d in summary['per_subject'].values())}  "
          f"chunks {len(total_chunks)}")
    print(f"chunks   math_heavy {_share(heavy_chunks, len(total_chunks))}  "
          f"length {_spread(lengths)}  within {chunking.CHUNK_MIN}-{chunking.CHUNK_MAX}: "
          f"{_share(in_band, len(lengths))}")
    sections = {(record["subject"], record["chapter_no"], record["section_no"])
                for record in total_chunks}
    chapters = {(record["subject"], record["chapter_no"]) for record in total_chunks}
    print(f"coverage {len(chapters)} chapters, {len(sections)} sections, "
          f"{len({r['id'] for r in total_chunks})} unique chunk ids  ({summary['took_s']}s)")
    if summary["title_report"]:
        statuses = Counter(row["status"] for row in summary["title_report"])
        print(f"titles   fragmented {len(summary['title_report'])}  "
              f"repaired {statuses.get('repaired', 0)}  needs_review {statuses.get('needs_review', 0)}")
        for row in summary["title_report"]:
            print(f"  [{row['status']:12s}] {row['subject']} §{row['section_no']:7s} "
                  f"{row['extracted']!r} -> {row['title']!r} ({row['method']})")


def report_text(summary: dict) -> None:
    records = summary["chunks"]
    lengths = [len(record["text"]) for record in records]
    print(f"demo     documents {len({r['chapter_title'] for r in records})}  "
          f"chunks {len(records)}  sources attributed {summary['sources']}  "
          f"length {_spread(lengths)}  -> {summary['target']}")
    print("demo     page_start/page_end are 1: plain text has no pages, and none are invented "
          "(the source URL in `source` is the citation target)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf-dir", help="directory holding the chapter PDFs")
    ap.add_argument("--text-dir", help="directory of plain-text documents (demo corpus)")
    ap.add_argument("--syllabus", default=DEFAULT_SYLLABUS)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--repair-titles", action="store_true",
                    help="rebuild fragmented section titles and rewrite the syllabus file")
    ap.add_argument("--no-heading-repair", action="store_true",
                    help="leave fragmented headings as extracted in the page text")
    ap.add_argument("--limit", type=int, help="process at most N chapters per subject (smoke test)")
    ap.add_argument("--summary-json", help="write the run summary as JSON here")
    args = ap.parse_args()

    if not args.pdf_dir and not args.text_dir:
        ap.error("give --pdf-dir, --text-dir or both")

    out_dir = Path(args.out_dir)
    summary: dict = {}
    if args.pdf_dir:
        syllabus_path = Path(args.syllabus)
        syllabus = json.loads(syllabus_path.read_text(encoding="utf-8"))
        summary["pdf"] = ingest_pdfs(Path(args.pdf_dir), syllabus, out_dir,
                                     repair=args.repair_titles,
                                     repair_headings=not args.no_heading_repair,
                                     limit=args.limit)
        report_pdf(summary["pdf"])
        if args.repair_titles:
            syllabus_path.write_text(json.dumps(syllabus, indent=1, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
            print(f"wrote {syllabus_path} (repaired titles)")
    if args.text_dir:
        summary["text"] = ingest_text(Path(args.text_dir), out_dir)
        report_text(summary["text"])
    if args.summary_json:
        target = Path(args.summary_json)
        target.write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
