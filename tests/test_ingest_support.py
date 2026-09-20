"""Shared fixtures for the ingest tests: a synthetic PDF that carries the source defects.

Nothing here comes from a textbook. The strings are written for the test and the PDF is generated
at test time with PyMuPDF. What it reproduces is the *shape* of the NCERT PDFs' defects, which is
what the ingest code has to survive:

* a heading drawn five times at sub-point offsets (the duplicate text layer),
* a label drawn five times the same way,
* a heading drawn as two partial renders, each placed at its true x position, overlapping where
  they duplicate each other — this is what produces '… EQUA AL EQUATIONS' in the real books,
* a page of positioned single-character glyphs (what a formula looks like after extraction).

The two fragments are derived from TITLE below: 'AL EQUATIONS' is the tail of TITLE from character
9, which is why the pair overlaps by six letters ('AL EQUA') exactly as the real defect does.
"""

from __future__ import annotations

import pymupdf

TITLE = "1.2 THERMAL EQUATIONS"
FRAGMENT_A = "1.2 THERMAL EQUA"          # TITLE truncated after 'EQUA'
FRAGMENT_B = "AL EQUATIONS"              # TITLE[9:] — begins inside 'THERMAL'
FRAGMENT_B_AT = 9                        # where FRAGMENT_B starts inside TITLE
MANGLED = f"{FRAGMENT_A} {FRAGMENT_B}"
HEADING = "1.1 Thermal Equations"
LABEL = "Activity 1.1"
PROSE = (
    "Thermal equations are written on this line. "
    "A second sentence follows it so the chunker has a boundary to split on. "
    "A third sentence keeps the paragraph long enough to be useful."
)
PROSE_2 = (
    "This paragraph belongs to the second section of the synthetic chapter. "
    "It exists so that a page can hold more than one section's worth of text. "
    "Another sentence follows for the chunker to find."
)
DENSE_GLYPHS = "x2+3y=7"
FONTSIZE = 14


def _offsets() -> tuple[float, ...]:
    return (0.0, 0.2, 0.4, 0.6, 0.8)


def _fragments(page, y: float) -> None:
    """Two partial renders of TITLE, each at the x where its text really sits."""
    page.insert_text((72, y), FRAGMENT_A, fontsize=FONTSIZE, fontname="helv")
    x = 72 + pymupdf.get_text_length(TITLE[:FRAGMENT_B_AT], fontname="helv", fontsize=FONTSIZE)
    page.insert_text((x, y), FRAGMENT_B, fontsize=FONTSIZE, fontname="helv")


def synthetic_pdf(path) -> pymupdf.Document:
    """Write the two-page fixture PDF and return the open document."""
    doc = pymupdf.open()
    page = doc.new_page()
    for offset in _offsets():                       # the heading, drawn five times
        page.insert_text((72, 100 + offset), HEADING, fontsize=FONTSIZE, fontname="helv")
    for offset in _offsets():                       # a label, drawn five times
        page.insert_text((72, 130 + offset), LABEL, fontsize=12, fontname="helv")
    page.insert_textbox(pymupdf.Rect(72, 150, 520, 260), PROSE, fontsize=10, fontname="helv")
    page.insert_textbox(pymupdf.Rect(72, 300, 520, 380), PROSE_2, fontsize=10, fontname="helv")

    second = doc.new_page()
    _fragments(second, 100)
    second.insert_textbox(pymupdf.Rect(72, 130, 520, 240), PROSE_2, fontsize=10, fontname="helv")
    for index, char in enumerate(DENSE_GLYPHS):     # positioned glyphs, as a formula extracts
        second.insert_text((72 + 12 * index, 300), char, fontsize=10, fontname="helv")

    doc.save(str(path))
    return doc


def complete_render_pdf(path) -> pymupdf.Document:
    """A page carrying both the partial renders and one complete render of the same heading.

    The fold has to pick one copy; `best_heading_render` has to find the complete render.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    _fragments(page, 200.0)
    page.insert_text((72, 200.4), TITLE, fontsize=FONTSIZE, fontname="helv")
    page.insert_textbox(pymupdf.Rect(72, 220, 520, 300), PROSE, fontsize=10, fontname="helv")
    doc.save(str(path))
    return doc
