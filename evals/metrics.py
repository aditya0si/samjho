"""Pure metric functions for the samjho eval harness.

No I/O, no imports from ``api/`` — everything here is a function of plain Python values so the
metrics themselves can be unit-tested against hand-computed numbers (tests/test_eval_metrics.py).

Vocabulary used throughout:

``ranked``   a ranked list of retrieved items, best first. Each item is a dict or an object with
             ``section_no`` and ``page_start`` / ``page_end`` attributes.
``expected`` a list of section numbers (or pages) any one of which counts as correct.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

__all__ = [
    "accuracy",
    "hit_at_k",
    "mean",
    "page_hit",
    "page_overlap_hit",
    "rank_of_first_hit",
    "ranked_sections",
    "reciprocal_rank",
]


def _field(item: Any, name: str) -> Any:
    """Read ``name`` off a dict or an arbitrary object."""
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _as_section(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ranked_sections(ranked: Iterable[Any]) -> list[str | None]:
    """Section numbers of a ranked retrieval list, best first (``None`` when an item has none)."""
    return [_as_section(_field(item, "section_no")) for item in ranked]


def rank_of_first_hit(ranked: Sequence[Any], expected: Sequence[str]) -> int | None:
    """1-based rank of the first item whose section is in ``expected``; ``None`` if there is none.

    Matching is an exact string comparison on ``section_no`` (``"1.2.2"`` does not match ``"1.2"``),
    which keeps the metric honest: a question that names a subsection must retrieve that subsection.
    """
    wanted = {_as_section(e) for e in expected}
    wanted.discard(None)
    if not wanted:
        raise ValueError("expected sections must not be empty")
    for rank, item in enumerate(ranked, start=1):
        if _as_section(_field(item, "section_no")) in wanted:
            return rank
    return None


def hit_at_k(ranked: Sequence[Any], expected: Sequence[str], k: int = 4) -> bool:
    """True when one of the first ``k`` retrieved items comes from an expected section."""
    if k < 1:
        raise ValueError("k must be >= 1")
    rank = rank_of_first_hit(ranked[:k], expected)
    return rank is not None


def reciprocal_rank(ranked: Sequence[Any], expected: Sequence[str]) -> float:
    """1/rank of the first correct item over the whole returned list; 0.0 when nothing matches."""
    rank = rank_of_first_hit(ranked, expected)
    return 0.0 if rank is None else 1.0 / rank


def page_hit(ranked: Sequence[Any], expected_pages: Sequence[int], k: int = 4) -> bool:
    """True when one of the first ``k`` items covers an expected page.

    An item covers page ``p`` when ``page_start <= p <= page_end`` (``page_end`` defaults to
    ``page_start``). This is the *strict* page check: the expected pages are the pages recorded in
    the golden line, which for most questions is the page the section starts on. Use
    :func:`page_overlap_hit` when what you want to know is whether the citation lands anywhere
    inside the section's own pages.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    pages = [p for p in (_as_int(p) for p in expected_pages) if p is not None]
    if not pages:
        raise ValueError("expected pages must not be empty")
    for item in ranked[:k]:
        start = _as_int(_field(item, "page_start"))
        end = _as_int(_field(item, "page_end"))
        if start is None:
            continue
        if end is None:
            end = start
        if start > end:
            start, end = end, start
        if any(start <= p <= end for p in pages):
            return True
    return False


def page_overlap_hit(ranked: Sequence[Any], spans: Sequence[tuple[int, int]], k: int = 4) -> bool:
    """True when one of the first ``k`` items' page range overlaps any of ``spans``.

    ``spans`` are ``(first_page, last_page)`` of the expected section(s) — the pages the section
    actually occupies in the book, not just the page it starts on. A citation that lands in the
    middle of the right section is correct, so this is what the gate measures.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    clean: list[tuple[int, int]] = []
    for span in spans:
        start, end = _as_int(span[0]), _as_int(span[1])
        if start is None or end is None:
            continue
        clean.append((start, end) if start <= end else (end, start))
    if not clean:
        raise ValueError("spans must not be empty")

    for item in ranked[:k]:
        start = _as_int(_field(item, "page_start"))
        end = _as_int(_field(item, "page_end"))
        if start is None:
            continue
        if end is None:
            end = start
        if start > end:
            start, end = end, start
        if any(start <= span_end and end >= span_start for span_start, span_end in clean):
            return True
    return False


def mean(values: Iterable[float]) -> float:
    """Arithmetic mean; 0.0 for an empty sequence (so an empty set can never look like a pass)."""
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def accuracy(flags: Iterable[bool]) -> float:
    """Fraction of true flags; 0.0 for an empty sequence."""
    return mean(1.0 if flag else 0.0 for flag in flags)
