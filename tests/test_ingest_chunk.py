"""Unit tests for ingest/chunk.py — provenance, sizing, overlap, and the chapter boundary.

Documents here are constructed in-process from synthetic prose, so no PDF and no book text is
involved. Each section gets its own marker token, which is what makes the boundary assertions
checkable: if a chunk ever carried two sections' or two chapters' markers, these tests fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.chunk import (
    CHUNK_MAX,
    CHUNK_MIN,
    build_chapter_chunks,
    build_demo_chunks,
    chunk_units,
    read_text_document,
    split_sentences,
    units_with_pages,
    write_jsonl,
)
from ingest.extract_text import DocumentText, PageText

pytestmark = pytest.mark.unit

CONTRACT_KEYS = {"id", "subject", "chapter_no", "chapter_title", "section_no", "section_title",
                 "page_start", "page_end", "math_heavy", "text", "source"}


def prose(marker: str, sentences: int = 12) -> str:
    """Sentence-cased prose: the splitter needs a capital after the full stop to see a boundary."""
    return " ".join(f"{marker.capitalize()} sentence number {index} carries enough words to be a "
                    f"real unit of study material for the chunker to measure."
                    for index in range(sentences))


def page(number: int, text: str, math_heavy: bool = False) -> PageText:
    return PageText(page=number, text=text, chars=len(text), lines=len(text.splitlines()),
                    math_heavy=math_heavy, signals={"short_ratio": 0.0})


def document(pages: list[PageText]) -> DocumentText:
    return DocumentText(pdf="synthetic.pdf", pages=pages)


def chapter(no: int, title: str, sections: list[tuple[str, str, int]]) -> dict:
    return {"no": no, "title": title,
            "sections": [{"no": no_, "title": title_, "page": page_} for no_, title_, page_ in sections]}


CHAPTER_ONE = chapter(1, "Alpha Chapter", [("1.1", "Alpha Section", 1), ("1.2", "Beta Section", 2)])
CHAPTER_TWO = chapter(2, "Gamma Chapter", [("2.1", "Gamma Section", 1)])


def alpha_document() -> DocumentText:
    return document([
        page(1, "1.1 Alpha Section\n" + prose("alpha")),
        page(2, "1.2 Beta Section\n" + prose("beta")),
    ])


def test_chunks_stay_inside_their_section():
    records = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    assert records
    for record in records:
        assert ("Alpha" in record["text"]) != ("Beta" in record["text"])
        assert record["section_no"] in {"1.1", "1.2"}
        if record["section_no"] == "1.1":
            assert "Beta" not in record["text"]
        else:
            assert "Alpha" not in record["text"]


def test_chunks_never_cross_chapters():
    one = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    two = build_chapter_chunks("science", CHAPTER_TWO,
                               document([page(1, "2.1 Gamma Section\n" + prose("gamma"))]))
    assert one and two
    for record in one + two:
        markers = {m for m in ("Alpha", "Beta", "Gamma") if m in record["text"]}
        assert len(markers) == 1
        assert record["chapter_no"] in {1, 2}
        assert (record["chapter_no"] == 2) == (markers == {"Gamma"})


def test_page_provenance_matches_the_text():
    records = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    for record in records:
        assert record["page_start"] <= record["page_end"]
        if "Beta" in record["text"]:
            assert record["page_start"] == 2 and record["page_end"] == 2
        else:
            assert record["page_start"] == 1 and record["page_end"] == 1


def test_page_provenance_spans_pages_when_the_text_does():
    long_section = chapter(3, "Delta Chapter", [("3.1", "Delta Section", 1)])
    doc = document([page(1, "3.1 Delta Section\n" + prose("delta", 30)), page(2, prose("delta", 30))])
    records = build_chapter_chunks("science", long_section, doc)
    assert len(records) >= 3
    assert any(record["page_start"] == 1 and record["page_end"] == 2 for record in records)


def test_chunk_sizes_and_overlap():
    records = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    long_records = [r for r in records if r["section_no"] == "1.1"]
    assert len(long_records) >= 2
    for record in long_records:
        assert len(record["text"]) <= CHUNK_MAX
    for record in long_records[:-1]:
        assert len(record["text"]) >= CHUNK_MIN
    first, second = long_records[0]["text"], long_records[1]["text"]
    tail = split_sentences(first)[-1]
    assert tail in second, "the 15% overlap must carry the previous chunk's tail"
    assert len(tail) <= 0.25 * len(first), "overlap must stay near 15%, not grow into a copy"


def test_chunk_ids_are_unique_and_match_the_contract():
    records = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    ids = [record["id"] for record in records]
    assert len(ids) == len(set(ids))
    for record in records:
        assert set(record) == CONTRACT_KEYS
        assert record["id"].startswith(f"science-1-{record['section_no']}-{record['page_start']}")
        assert record["subject"] == "science"
        assert record["chapter_title"] == "Alpha Chapter"
        assert record["source"] is None


def test_math_heavy_follows_the_majority_of_the_chunk_pages():
    doc = document([page(1, "1.1 Alpha Section\n" + prose("alpha"), math_heavy=True)])
    records = build_chapter_chunks("science", CHAPTER_ONE, doc)
    assert records and all(record["math_heavy"] for record in records)
    prose_doc = document([page(1, "1.1 Alpha Section\n" + prose("alpha"))])
    assert not any(record["math_heavy"]
                   for record in build_chapter_chunks("science", CHAPTER_ONE, prose_doc))


def test_missing_heading_falls_back_to_the_whole_page():
    doc = document([page(1, "prose without the expected heading line\n" + prose("alpha"))])
    records = build_chapter_chunks("science", CHAPTER_ONE, doc)
    assert records
    assert "prose without the expected heading line" in records[0]["text"]


def test_chunk_units_terminates_on_a_single_giant_sentence():
    """A page of formula fragments has no full stop for pages: the walk must still terminate."""
    units = [(1, "x " * 400)]
    chunks = chunk_units(units_with_pages(units))
    assert chunks and chunks[0][2]
    assert all(len(body) <= CHUNK_MAX for _, _, body in chunks)


def test_abbreviations_do_not_split_sentences():
    parts = split_sentences("See Fig. 1.2 for the ray diagram. The next sentence is separate.")
    assert parts == ["See Fig. 1.2 for the ray diagram.", "The next sentence is separate."]


def test_write_jsonl_round_trip_and_repo_guard(tmp_path):
    records = build_chapter_chunks("science", CHAPTER_ONE, alpha_document())
    target = write_jsonl(records, tmp_path / "corpus" / "chunks" / "science.jsonl")
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(records)
    assert set(rows[0]) == CONTRACT_KEYS
    repo_root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError):
        write_jsonl(records, repo_root / "data" / "chunks.jsonl")


DEMO_TEXT = """# source: https://example.invalid/thermal-equations
# licence: CC BY-SA 4.0
# retrieved: 2026-09-20
# note: synthetic file written for the test suite
# class10 hook: Science Ch 1 — Alpha Chapter: thermal equations

Thermal equations describe how heat moves through a body of matter. The licence header above is
not study material and must not reach the chunk text.
"""


def test_demo_text_ingestion_keeps_attribution_and_drops_the_header(tmp_path):
    text_dir = tmp_path / "demo"
    text_dir.mkdir()
    (text_dir / "thermal.txt").write_text(DEMO_TEXT, encoding="utf-8")
    parsed = read_text_document(text_dir / "thermal.txt")
    assert parsed["source"] == "https://example.invalid/thermal-equations"
    assert parsed["chapter_title"] == "Science Ch 1 — Alpha Chapter: thermal equations"
    assert parsed["section_title"] == "thermal equations"
    assert not parsed["body"].startswith("#")
    assert "CC BY-SA" not in parsed["body"]
    assert parsed["licence"] == "CC BY-SA 4.0"

    records = build_demo_chunks(text_dir)
    assert len(records) == 1
    record = records[0]
    assert record["subject"] == "demo" and record["chapter_no"] == 0
    assert record["section_no"] == "0.1"
    assert (record["page_start"], record["page_end"]) == (1, 1)
    assert record["source"] == "https://example.invalid/thermal-equations"
    assert record["math_heavy"] is False
    assert "CC BY-SA" not in record["text"]
    assert "thermal equations" in record["text"].lower()
