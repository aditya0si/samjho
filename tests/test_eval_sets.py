"""Unit tests for the golden sets and the refusal set themselves.

These run with no database and no model: they check the sets are well formed, that every expected
section and page exists in ``data/syllabus/class10.json`` (so a golden question can never point at a
section the corpus does not have), and — when a corpus happens to be present — that no golden
question is a verbatim slice of the ingested textbook text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.run_eval import (  # noqa: E402
    GOLDEN_FILES,
    REFUSAL_REASONS,
    REFUSALS_PATH,
    load_jsonl,
)

SYLLABUS_PATH = REPO_ROOT / "data" / "syllabus" / "class10.json"
CORPUS_DIR = REPO_ROOT / "corpus" / "chunks"


def syllabus_index() -> dict[tuple[str, int, str], int]:
    data = json.loads(SYLLABUS_PATH.read_text(encoding="utf-8"))
    index: dict[tuple[str, int, str], int] = {}
    for subject in data["subjects"]:
        for chapter in subject["chapters"]:
            for section in chapter.get("sections", []):
                index[(subject["id"], chapter["no"], section["no"])] = section.get("page")
    return index


@pytest.mark.unit
def test_golden_files_have_the_agreed_size():
    science = load_jsonl(GOLDEN_FILES["science"])
    maths = load_jsonl(GOLDEN_FILES["maths"])
    assert len(science) == 20
    assert len(maths) == 15


_QUESTION_MARKERS = (
    "?",
    "why",
    "how",
    "what",
    "which",
    "where",
    "state",
    "define",
    "explain",
    "name",
    "find",
    "solve",
    "justify",
    "prove",
    "write",
    "give",
    "calculate",
    "derive",
    "list",
    "describe",
    "integrate",
    "differentiate",
    "using",
    "as per",
)


def looks_like_a_question(text: str) -> bool:
    """A golden/refusal line must read as a question or a task, not as a stray sentence."""
    stripped = text.strip().lower()
    if len(stripped) < 15:
        return False
    return any(marker in stripped for marker in _QUESTION_MARKERS)


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["science", "maths"])
def test_golden_rows_have_the_contract_shape(subject: str):
    rows = load_jsonl(GOLDEN_FILES[subject])
    for i, row in enumerate(rows, start=1):
        where = f"{subject}.jsonl:{i}"
        assert set(row) == {
            "question",
            "subject",
            "chapter_no",
            "expected_sections",
            "expected_pages",
            "why",
        }, where
        assert row["subject"] == subject, where
        assert isinstance(row["chapter_no"], int), where
        assert looks_like_a_question(row["question"]), where
        assert row["expected_sections"] and row["expected_pages"], where
        assert len(row["expected_sections"]) == len(row["expected_pages"]), where
        assert row["why"].strip() and len(row["why"]) > 20, where


@pytest.mark.unit
@pytest.mark.parametrize("subject", ["science", "maths"])
def test_expected_sections_and_pages_exist_in_the_syllabus(subject: str):
    index = syllabus_index()
    for i, row in enumerate(load_jsonl(GOLDEN_FILES[subject]), start=1):
        for section_no, page in zip(row["expected_sections"], row["expected_pages"], strict=False):
            key = (subject, row["chapter_no"], section_no)
            assert key in index, f"{subject}.jsonl:{i}: section {section_no} not in the syllabus"
            assert index[key] == page, (
                f"{subject}.jsonl:{i}: page {page} for section {section_no} does not match the "
                f"syllabus page {index[key]}"
            )


@pytest.mark.unit
def test_golden_sets_cover_the_chapters_they_claim_to():
    science = {row["chapter_no"] for row in load_jsonl(GOLDEN_FILES["science"])}
    maths = {row["chapter_no"] for row in load_jsonl(GOLDEN_FILES["maths"])}
    assert science == {1, 2, 3, 9, 11}
    assert maths == {1, 2, 8}


@pytest.mark.unit
def test_no_duplicate_questions_anywhere_in_the_sets():
    questions = []
    for subject in ("science", "maths"):
        questions += [row["question"].strip().lower() for row in load_jsonl(GOLDEN_FILES[subject])]
    refusals = [row["question"].strip().lower() for row in load_jsonl(REFUSALS_PATH)]
    assert len(set(questions)) == len(questions)
    assert len(set(refusals)) == len(refusals)
    assert not set(questions) & set(refusals)


@pytest.mark.unit
def test_refusal_set_shape_and_reasons():
    rows = load_jsonl(REFUSALS_PATH)
    assert len(rows) >= 12
    for i, row in enumerate(rows, start=1):
        assert set(row) == {"question", "reason"}, f"refusals.jsonl:{i}"
        assert row["reason"] in REFUSAL_REASONS, f"refusals.jsonl:{i}"
        assert looks_like_a_question(row["question"]), f"refusals.jsonl:{i}"
    # all three refusal categories must actually be exercised
    assert {row["reason"] for row in rows} == REFUSAL_REASONS


@pytest.mark.unit
def test_refusal_set_covers_out_of_class_and_off_topic_questions():
    rows = load_jsonl(REFUSALS_PATH)
    by_reason = {
        reason: [r["question"] for r in rows if r["reason"] == reason] for reason in REFUSAL_REASONS
    }
    assert len(by_reason["out_of_syllabus"]) >= 5  # Class 11/12 material
    assert len(by_reason["other_board"]) >= 3  # ICSE / IGCSE / state board terminology
    assert len(by_reason["not_course_material"]) >= 3  # nothing to do with the corpus


@pytest.mark.unit
def test_golden_questions_are_not_verbatim_textbook_lines():
    """When a corpus is present, no golden question may be copied out of the ingested text.

    The corpus is gitignored and only exists after a student ingests their own book, so this check
    simply has nothing to compare against when it is absent — the test still runs either way.
    """
    if not CORPUS_DIR.is_dir():
        return
    chunk_files = sorted(CORPUS_DIR.glob("*.jsonl"))
    if not chunk_files:
        return
    text = "\n".join(
        line
        for path in chunk_files
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ).lower()
    golden_questions = [
        row["question"]
        for subject in ("science", "maths")
        for row in load_jsonl(GOLDEN_FILES[subject])
    ]
    for question in golden_questions:
        normalised = " ".join(question.lower().split())
        assert (
            normalised not in text
        ), f"golden question appears verbatim in the corpus: {question!r}"
