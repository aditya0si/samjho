"""Unit tests for ingest/extract_text.py — the duplicate-layer folding, dedupe and page numbers.

The fixture is a synthetic PDF built in the test (see test_ingest_support.py). Every assertion here
can fail: if the fold stops de-duplicating, the counts change; if page numbers stop being tracked,
the page assertions fail; if the heading rebuild regresses, the repaired-line assertion fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_ingest_support import (
    HEADING,
    LABEL,
    MANGLED,
    TITLE,
    complete_render_pdf,
    synthetic_pdf,
)

from ingest import extract_text
from ingest.repair_titles import best_heading_render, build_chapter_vocabulary, strip_leading_number

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def document(tmp_path_factory):
    path = tmp_path_factory.mktemp("pdf") / "synthetic.pdf"
    synthetic_pdf(path)
    return extract_text.extract_document(path)


def test_fold_removes_the_duplicate_text_layer(document):
    """The heading is drawn five times; the extracted page text must carry it once."""
    first = document.pages[0]
    assert first.text.count(HEADING) == 1
    assert first.text.count(LABEL) == 1
    assert f"{HEADING} {HEADING}" not in first.text


def test_page_numbers_are_tracked(document):
    assert [page.page for page in document.pages] == [1, 2]
    assert HEADING in document.pages[0].text
    assert HEADING not in document.pages[1].text
    assert document.pages[1].lines > 0 and document.pages[1].chars > 0


def test_prose_survives_intact(document):
    assert "Thermal equations are written on this line." in document.pages[0].text
    assert "A third sentence keeps the paragraph long enough to be useful." in document.pages[0].text


def test_math_heavy_flags_the_glyph_page_only(document):
    """Page 2 is positioned single-character glyphs; page 1 is prose."""
    assert document.pages[1].math_heavy is True
    assert document.pages[0].math_heavy is False
    assert document.pages[1].signals["short_ratio"] >= extract_text.MATH_HEAVY_SHORT_RATIO
    assert document.pages[0].signals["short_ratio"] < extract_text.MATH_HEAVY_SHORT_RATIO


def test_fragmented_heading_is_rebuilt_and_verified(document):
    """The overlapping partial renders are rebuilt, and the rebuild is recorded with its source."""
    second = document.pages[1]
    assert TITLE in second.text
    assert MANGLED not in second.text
    assert second.repaired_headings and MANGLED in second.repaired_headings[0]
    assert TITLE in second.repaired_headings[0]


def test_fold_without_repair_leaves_the_fragments_visible(tmp_path):
    """With the repair switched off the fold's output is the mangled line — the defect is real."""
    path = tmp_path / "raw.pdf"
    synthetic_pdf(path)
    raw = extract_text.extract_document(path, repair_headings=False)
    assert MANGLED in raw.pages[1].text
    assert raw.pages[1].repaired_headings == []


def test_rebuild_is_verified_against_the_chapter_vocabulary():
    """The rebuild is only accepted because 'thermal equations' is a phrase of the chapter's own
    prose. With a vocabulary that lacks it, the line is left exactly as the fold produced it."""
    vocab = build_chapter_vocabulary(["A paragraph about nothing in particular."])
    outcome = extract_text.repair_title(MANGLED, vocab)
    assert outcome["status"] == "needs_review"
    assert outcome["title"] == MANGLED
    good = build_chapter_vocabulary(["Thermal equations are written on this line."])
    assert extract_text.repair_title(MANGLED, good)["title"] == strip_leading_number(TITLE)


def test_repeated_labels_collapse_but_ordinary_repeats_do_not():
    kept, collapsed = extract_text.collapse_repeated_labels(
        ["Activity 1.3 Activity 1.3", "equation.", "equation.", "2 3", "2 3", "Figure 1.2"]
    )
    assert kept == ["Activity 1.3", "equation.", "equation.", "2 3", "2 3", "Figure 1.2"]
    assert collapsed == ["Activity 1.3 Activity 1.3"]


def test_adjacent_duplicate_label_collapses():
    kept, collapsed = extract_text.collapse_repeated_labels(["Figure 1.2", "Figure 1.2", "prose line"])
    assert kept == ["Figure 1.2", "prose line"]
    assert collapsed == ["Figure 1.2"]


def test_running_lines_are_dropped():
    pages = [["Chapter One", "body text of page one"], ["Chapter One", "body text two"],
             ["Chapter One", "body text three"], ["Chapter One", "body text four"]]
    assert extract_text.drop_running_lines(pages) == {"Chapter One"}


def test_complete_render_wins_over_partial_copies(tmp_path):
    """A page that holds both a partial render and a complete one yields the complete text."""
    path = tmp_path / "render.pdf"
    doc = complete_render_pdf(path)
    render = best_heading_render(doc[0], "1.2")
    doc.close()
    assert render is not None
    assert render.text == TITLE
    assert render.completeness >= 0.98
    assert render.overlap <= 1.0


def test_page_jsonl_round_trip(document, tmp_path):
    target = extract_text.write_pages(document, tmp_path / "pages.jsonl")
    rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
    assert [row["page"] for row in rows] == [1, 2]
    assert rows[0]["text"].count(HEADING) == 1
    assert rows[1]["math_heavy"] is True
    assert rows[0]["signals"]["spans"] > 0


def test_guard_refuses_to_write_book_text_into_the_repo(tmp_path):
    """The licensing boundary is enforced, not documented: extracted text goes to corpus/ only."""
    repo_root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError):
        extract_text.guard_output_path(repo_root / "data" / "leak.jsonl")
    assert extract_text.guard_output_path(repo_root / "corpus" / "ok.jsonl").name == "ok.jsonl"
    assert extract_text.guard_output_path(tmp_path / "anywhere.jsonl").name == "anywhere.jsonl"
