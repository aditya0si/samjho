"""The syllabus structure — factual metadata only (chapter/section headings and page anchors).

Owned by the ingest builder (`data/syllabus/class10.json`, CONTRACTS section 1). This module only
*reads* it, and deliberately never serves a field that could contain book prose: /subjects must be
safe to expose on a public site (docs/PLAN.md section 1).

The file is read once and cached, but a missing or malformed file is not fatal — `/subjects`
returns an empty subject list with a note, because the API has to serve /health and /subjects on a
machine where the syllabus has not been generated yet.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings

# Fields that are structure, not text. Anything else in the file is dropped before it is served.
SECTION_FIELDS = ("no", "title", "page")
CHAPTER_FIELDS = ("no", "title", "pages", "status")
SUBJECT_FIELDS = ("id", "name", "book_code")


class SyllabusError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _load(path_str: str, mtime_ns: int) -> dict[str, Any]:
    path = Path(path_str)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyllabusError(f"syllabus file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SyllabusError(f"syllabus file is not valid JSON: {path} — {exc}") from exc
    return raw


def load_syllabus() -> dict[str, Any]:
    settings = get_settings()
    path = Path(settings.syllabus_path)
    mtime = path.stat().st_mtime_ns if path.exists() else 0
    return _load(str(path), mtime)


def syllabus_available() -> bool:
    try:
        load_syllabus()
        return True
    except SyllabusError:
        return False


def _clean_subject(subject: dict[str, Any]) -> dict[str, Any]:
    out = {k: subject[k] for k in SUBJECT_FIELDS if k in subject}
    out["chapters"] = []
    for chapter in subject.get("chapters", []):
        clean = {k: chapter[k] for k in CHAPTER_FIELDS if k in chapter}
        clean["sections"] = [
            {k: section[k] for k in SECTION_FIELDS if k in section}
            for section in chapter.get("sections", [])
        ]
        out["chapters"].append(clean)
    return out


def subjects() -> list[dict[str, Any]]:
    """The syllabus minus anything that is not structure."""
    try:
        data = load_syllabus()
    except SyllabusError:
        return []
    return [_clean_subject(s) for s in data.get("subjects", [])]


def get_subject(subject_id: str) -> dict[str, Any] | None:
    for subject in subjects():
        if str(subject.get("id")) == subject_id:
            return subject
    return None


def get_chapter(subject_id: str, chapter_no: int) -> dict[str, Any] | None:
    subject = get_subject(subject_id)
    if not subject:
        return None
    for chapter in subject.get("chapters", []):
        if int(chapter.get("no", -1)) == int(chapter_no):
            return chapter
    return None


def suggest_chapter(subject_id: str, question: str) -> dict[str, Any] | None:
    """Best-matching syllabus chapter for a refused question, or None.

    Used only to make a refusal more useful ("the syllabus lists Chapter 5 …"), and only when a
    chapter title genuinely shares a content word with the question — a guess with nothing behind
    it would be a fabricated citation, which is exactly what this project refuses to do.
    """
    from .retriever import content_terms

    terms = set(content_terms(question))
    if not terms:
        return None
    best: tuple[float, dict[str, Any]] | None = None
    for chapter in (get_subject(subject_id) or {}).get("chapters", []):
        title_terms = set(content_terms(str(chapter.get("title", ""))))
        if not title_terms:
            continue
        overlap = len(terms & title_terms) / len(title_terms)
        if overlap > 0 and (best is None or overlap > best[0]):
            best = (overlap, chapter)
    if best is None:
        return None
    return {"no": best[1].get("no"), "title": best[1].get("title"), "match": round(best[0], 3)}
