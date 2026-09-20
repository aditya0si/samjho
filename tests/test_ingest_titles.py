"""Unit tests for ingest/repair_titles.py — the fragment detector, the vocabulary, the repair.

All strings here are written for the test. The shapes they mirror are the ones measured in the real
books: fragments that overlap by a suffix/prefix, and a duplicated leading fragment ('MA MA …').
The last test reads the shipped syllabus and checks the contract's marker rule on it, which is what
guards the 206-section structure against a repair that silently drops a title.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.repair_titles import (
    HeadingRender,
    Vocabulary,
    build_chapter_vocabulary,
    candidates,
    duplicated_leading_word,
    letters,
    looks_fragmented,
    overlap_splits,
    repair_title,
    strip_leading_number,
)

pytestmark = pytest.mark.unit

MANGLED = "THERMAL EQUA AL EQUATIONS"          # true title: THERMAL EQUATIONS
MANGLED_LEADING = "MA MA GNETIC FIELD LINES"   # true title: MAGNETIC FIELD LINES
MANGLED_ACCUM = "ACCUMUL CCUMUL ATION OF V ARIA TION"   # true: ACCUMULATION OF VARIATION
DROPPED_CHAR = "MA MA GNETIC FIELD L NES"      # fragments joined, but 'LINES' lost its 'I'
BODY = "Thermal equations are written here. Magnetic field lines curve around a wire."
SYLLABUS = Path(__file__).resolve().parents[1] / "data" / "syllabus" / "class10.json"


def test_letters_and_words_ignore_punctuation_and_digits():
    assert letters("1.2 THERMAL EQUA, AL EQUATIONS?") == "thermalequaalequations"
    assert duplicated_leading_word("MA MA GNETIC FIELD LINES")
    assert not duplicated_leading_word("MAGNETIC FIELD LINES")


def test_the_overlap_threshold_separates_coincidence_from_the_defect():
    """A two-character suffix/prefix match happens in clean titles; three or more is the defect."""
    assert overlap_splits("ratioalalgebra", min_overlap=2)
    assert not overlap_splits("ratioalalgebra", min_overlap=3)
    assert overlap_splits(letters(MANGLED), min_overlap=3)


def test_detector_flags_the_measured_defect_shapes():
    assert looks_fragmented(MANGLED)
    assert looks_fragmented(MANGLED_LEADING)
    assert looks_fragmented(MANGLED_ACCUM)
    assert looks_fragmented("Impor 2.3.1 Impor tance of pH")
    assert not looks_fragmented("THERMAL EQUATIONS")
    assert not looks_fragmented("Turning Over New Pages")


def test_candidates_include_the_rebuilt_title():
    keys = [key for key, _ in candidates(MANGLED)]
    assert "thermalequations" in keys
    assert [how for key, how in candidates(MANGLED) if key == "thermalequations"] == ["overlap-join:6"]


def test_vocabulary_excludes_heading_lines_so_a_mangled_heading_cannot_validate_itself():
    """The trap this guards: the mangled heading is itself in the extracted page text."""
    vocab = build_chapter_vocabulary(["THERMAL EQUA AL EQUATIONS", BODY])
    assert "thermalequations" in vocab.phrases
    assert "thermalequaalequations" not in vocab.phrases
    assert vocab.phrases["thermalequations"] == "Thermal equations"


def test_segment_spells_a_rebuilt_title_from_the_chapters_own_words():
    vocab = build_chapter_vocabulary([BODY])
    assert vocab.segment("magneticfieldlines") == ["magnetic", "field", "lines"]
    assert vocab.segment("magneticfieldzebras") is None


def test_repair_uses_the_vocabulary_and_keeps_the_book_casing():
    vocab = build_chapter_vocabulary([BODY])
    outcome = repair_title(MANGLED, vocab)
    assert outcome["status"] == "repaired"
    assert outcome["title"] == "THERMAL EQUATIONS"
    assert outcome["method"] == "overlap-join:6"
    assert repair_title("Thermal Equa Al Equations", vocab)["title"] == "Thermal equations"


def test_repair_of_the_duplicated_leading_fragment():
    vocab = build_chapter_vocabulary([BODY])
    assert repair_title(MANGLED_LEADING, vocab)["title"] == "MAGNETIC FIELD LINES"
    assert repair_title(MANGLED_ACCUM, build_chapter_vocabulary(
        ["Accumulation of variation is the topic here."]))["title"] == "ACCUMULATION OF VARIATION"


def test_a_dropped_character_is_repaired_only_from_the_pdf_s_own_render():
    """Some headings lose a character as well as duplicating fragments (the real corpus has
    'O XID TION' where the heading says OXIDATION). Joining the fragments cannot rebuild those, so
    the repair refuses to guess; the PDF's own complete render is what rebuilds them."""
    vocab = build_chapter_vocabulary([BODY])
    outcome = repair_title(DROPPED_CHAR, vocab)
    assert outcome["status"] == "needs_review" and outcome["title"] == DROPPED_CHAR

    render = HeadingRender(text="1.1 MAGNETIC FIELD LINES", completeness=1.0, overlap=0.0)
    rebuilt = repair_title(DROPPED_CHAR, vocab, render=render)
    assert rebuilt["status"] == "repaired"
    assert rebuilt["title"] == "MAGNETIC FIELD LINES"
    assert rebuilt["method"] == "refold"


def test_a_render_is_rejected_when_it_contradicts_the_cluster_spans():
    """Every copy is a partial render, so each span must be a substring of the read."""
    from ingest.repair_titles import _consistent_with_spans

    spans = [{"text": "MAGNETIC FIELD LINES", "bbox": (0, 0, 10, 1)},
             {"text": "NETIC FIELD L", "bbox": (0, 0, 10, 1)}]
    assert _consistent_with_spans("1.1 MAGNETIC FIELD LINES", spans)
    assert not _consistent_with_spans("1.1 MAGNETIC FIELD L NES", spans)


def test_untrusted_renders_are_not_used_as_titles():
    """A partial render, or one that duplicates text instead of tiling it, is never the title."""
    vocab = build_chapter_vocabulary([BODY])
    partial = HeadingRender(text="1.1 MAGNETIC FIELD L", completeness=0.72, overlap=0.0)
    doubled = HeadingRender(text="1.1 MA MA GNETIC FIELD LINES", completeness=1.0, overlap=40.0,
                            consistent=False)
    assert repair_title(DROPPED_CHAR, vocab, render=partial)["status"] == "needs_review"
    assert repair_title(DROPPED_CHAR, vocab, render=doubled)["status"] == "needs_review"
    # where the fragment-join route can rebuild it, that route is used, never the bad render
    assert repair_title(MANGLED_LEADING, vocab, render=partial)["method"] != "refold"


def test_a_wrapped_heading_is_joined_only_when_the_join_is_a_phrase_of_the_chapter():
    """The second line of a wrapped heading is a layout guess, so it needs lexical verification."""
    body = "Thermal equations in practice are the subject here."
    vocab = build_chapter_vocabulary([body])
    render = HeadingRender(text="1.2 THERMAL EQUATIONS", completeness=1.0, overlap=0.0,
                           tail="IN PRACTICE")
    joined = repair_title(MANGLED, vocab, render=render)
    assert joined["method"] == "refold+wrapped"
    assert joined["title"] == "THERMAL EQUATIONS IN PRACTICE"

    thin = build_chapter_vocabulary(["Thermal equations are written here."])
    unjoined = repair_title(MANGLED, thin, render=render)
    assert unjoined["status"] == "repaired"
    assert unjoined["title"] == "THERMAL EQUATIONS"
    assert "IN PRACTICE" in (unjoined["note"] or "")


def test_unrepairable_titles_are_flagged_not_invented():
    vocab = build_chapter_vocabulary(["Nothing relevant is written in this paragraph at all."])
    outcome = repair_title(MANGLED, vocab)
    assert outcome["status"] == "needs_review"
    assert outcome["title"] == MANGLED
    assert "invent" not in (outcome["note"] or "")


def test_clean_titles_are_left_alone():
    vocab = build_chapter_vocabulary([BODY])
    for title in ("THERMAL EQUATIONS", "1.1 Introduction", "Summary"):
        outcome = repair_title(title, vocab)
        assert outcome["status"] == "clean" and outcome["title"] == title


def test_strip_leading_number():
    assert strip_leading_number("1.3 HAVE YOU LOOKED AT THIS") == "HAVE YOU LOOKED AT THIS"
    assert strip_leading_number("HAVE YOU LOOKED AT THIS") == "HAVE YOU LOOKED AT THIS"


def test_vocabulary_is_built_from_phrases_not_just_words():
    vocab = Vocabulary()
    vocab.add_text("Thermal equations are written here.")
    assert vocab.phrases["thermalequations"] == "Thermal equations"
    assert "thermal" in vocab.unigrams and "equations" in vocab.unigrams


def test_shipped_syllabus_obeys_the_marker_rule():
    """Every title that still carries the defect must be marked, and no marked title may be clean.

    This is the contract's rule (CONTRACTS.md §1) applied to the file the pipeline ships.
    """
    syllabus = json.loads(SYLLABUS.read_text(encoding="utf-8"))
    chapters = sections = flagged = fragmented = 0
    for subject in syllabus["subjects"]:
        for chapter in subject["chapters"]:
            chapters += 1
            for section in chapter.get("sections", []):
                sections += 1
                title = section.get("title", "")
                marked = section.get("title_needs_review") is True
                flagged += int(marked)
                if looks_fragmented(title):
                    fragmented += 1
                    assert marked, f"{subject['id']} §{section['no']} still fragmented: {title!r}"
                else:
                    assert not marked, f"{subject['id']} §{section['no']} marked but clean: {title!r}"
    assert (chapters, sections) == (27, 206), "the syllabus structure must survive the repair"
    # The marker must be exact in both directions: every still-fragmented title is flagged, and
    # nothing else is.
    assert flagged == fragmented
    # The shipped file must carry NO fragmented title. All 15 the detector found were repaired: 13
    # by the vocabulary/overlap routes, and the last two (§2.1, §12.2) by re-reading the complete
    # render inside the heading's own span cluster and verifying it against the PDF's glyphs rather
    # than guessing. A re-run that regresses this is a real failure, so the count is asserted at
    # zero — not at whatever the pipeline happened to leave behind.
    assert fragmented == 0, f"{fragmented} shipped title(s) still carry the duplicate-layer defect"
