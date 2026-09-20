"""Quiz generation from one chapter's chunks only.

Two hard constraints from CONTRACTS section 4 and docs/PLAN.md:

* a question may only come from a chunk of the requested chapter — never from another chapter,
  never from model general knowledge. Every question carries `source` (chapter, section, pages,
  chunk id) so it can be traced back to ingest;
* every question carries a marking key. In the retrieval-only path the key is the corpus sentence
  itself, quoted, because a marking key invented from nothing would grade a student against a
  fact that does not exist in their book.

With a provider configured the questions are written by the model, but they are still *validated*
here: a question whose `source_chunk_id` is not in the chapter's retrieved chunk set is dropped,
not repaired. If too few survive, the retrieval-only generator tops the quiz up and the response
says so.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field

from . import db
from .config import get_settings
from .retriever import RetrievalUnavailable, RetrievedChunk, content_terms

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


class QuizSource(BaseModel):
    chapter_no: int
    section_no: str
    section_title: str
    page_start: int
    page_end: int
    chunk_id: str


class MarkingKey(BaseModel):
    expected_points: list[str] = Field(
        description="What a correct answer must contain. Quoted from the corpus in retrieval-only mode."
    )
    guidance: str = Field(description="How to mark it: what is required, what is acceptable.")


class QuizQuestion(BaseModel):
    id: str
    question: str
    type: str = Field(description="'fill_in_the_blank' | 'short_answer'")
    marks: int
    source: QuizSource
    marking_key: MarkingKey


class QuizResult(BaseModel):
    subject: str
    chapter_no: int
    provider: str
    questions: list[QuizQuestion] = Field(default_factory=list)
    note: str | None = None
    degraded: bool = False
    provider_error: str | None = None
    took_ms: int = 0


QUIZ_PROMPT = """You write quiz questions for a CBSE Class 10 student in India.

Write exactly {count} questions using ONLY the numbered passages below, which come from the \
student's own copy of their textbook. Rules:
1. Every question must be answerable from a single passage, and must name the passage id it came \
from in "source_chunk_id".
2. Never invent facts, numbers, page references or quotations that are not in the passages.
3. Mix types: "short_answer" (2-3 marks) and "fill_in_the_blank" (1-2 marks).
4. The marking key must list the points a correct answer needs, drawn from the passage.
5. Reply with JSON only, no markdown fence:
{{"questions": [{{"question": "...", "type": "short_answer", "marks": 3, \
"source_chunk_id": "...", "marking_key": {{"expected_points": ["..."], "guidance": "..."}}}}]}}

Passages:
{context}
"""


def _usable_sentences(text: str, min_words: int = 8) -> list[str]:
    out = []
    for part in _SENTENCE_SPLIT_RE.split(text.replace("\n", " ")):
        part = " ".join(part.split())
        if len(part.split()) >= min_words and part not in out:
            out.append(part)
    return out


def _salient_terms(sentence: str, limit: int = 4) -> list[str]:
    """Terms to name in a question stem. Verbatim words from the corpus sentence — no invention."""
    seen: list[str] = []
    for term in content_terms(sentence):
        if term not in seen:
            seen.append(term)
    return seen[:limit]


def _chunk_to_question(chunk: RetrievedChunk, index: int) -> QuizQuestion | None:
    sentences = _usable_sentences(chunk.text)
    if not sentences:
        return None
    # Longest sentence is usually the one carrying the definition or the reaction.
    sentence = max(sentences, key=len)
    words = sentence.split()
    kind = "short_answer" if index % 2 == 0 else "fill_in_the_blank"

    if kind == "fill_in_the_blank":
        keep = max(4, int(len(words) * 0.6))
        stem = " ".join(words[:keep])
        question = (
            f"Complete the statement from §{chunk.section_no} (page {chunk.page_start}) in your "
            f"own words: “{stem} …”"
        )
        marks = 2
    else:
        terms = _salient_terms(sentence)
        topic = ", ".join(terms) if terms else chunk.section_title
        question = (
            f"Explain what your book says about {topic} "
            f"(§{chunk.section_no}, page {chunk.page_start}). Cite the section in your answer."
        )
        marks = 3

    guidance = (
        "Any answer conveying the same meaning as the source sentence earns full marks; the "
        "wording below is the book's own and is what the key is checked against."
    )
    if chunk.math_heavy:
        guidance += (
            " This page is equation-heavy and the PDF text layer can garble symbols — check the "
            "printed page before marking a formula."
        )
    return QuizQuestion(
        id=f"quiz-{chunk.subject}-{chunk.chapter_no}-{chunk.section_no}-{index}".replace(" ", ""),
        question=question,
        type=kind,
        marks=marks,
        source=QuizSource(
            chapter_no=chunk.chapter_no,
            section_no=chunk.section_no,
            section_title=chunk.section_title,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            chunk_id=chunk.id,
        ),
        marking_key=MarkingKey(expected_points=[sentence], guidance=guidance),
    )


def retrieval_only_quiz(
    chunks: list[RetrievedChunk], count: int, *, start_index: int = 0
) -> list[QuizQuestion]:
    """Deterministic questions built from the chapter's own sentences."""
    questions: list[QuizQuestion] = []
    seen_sentences: set[str] = set()
    for chunk in chunks:
        if len(questions) >= count:
            break
        question = _chunk_to_question(chunk, start_index + len(questions))
        if question is None:
            continue
        key = question.marking_key.expected_points[0].lower()
        if key in seen_sentences:
            continue
        seen_sentences.add(key)
        questions.append(question)
    return questions


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _provider_quiz(
    chunks: list[RetrievedChunk], count: int
) -> tuple[list[QuizQuestion], str | None]:
    """Ask the provider for questions, then validate every one against the chapter's chunks."""
    from .answer import _call_llm  # one HTTP client implementation, not two

    by_id = {chunk.id: chunk for chunk in chunks}
    context = "\n\n".join(
        f"[{chunk.id}] Ch {chunk.chapter_no} §{chunk.section_no} p.{chunk.page_start} — "
        f"{chunk.section_title}\n{chunk.text}"
        for chunk in chunks
    )
    prompt = QUIZ_PROMPT.format(count=count, context=context)
    try:
        raw = _call_llm(prompt)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    parsed = _parse_json_object(raw)
    if parsed is None:
        return [], f"provider returned non-JSON output: {raw.strip()[:160]!r}"

    questions: list[QuizQuestion] = []
    for item in parsed.get("questions") or []:
        if not isinstance(item, dict):
            continue
        chunk = by_id.get(str(item.get("source_chunk_id") or ""))
        if chunk is None:
            continue  # fabricated source: dropped, never repaired
        text = str(item.get("question") or "").strip()
        key = item.get("marking_key") or {}
        points = [str(p) for p in (key.get("expected_points") or []) if str(p).strip()]
        if not text or not points:
            continue
        questions.append(
            QuizQuestion(
                id=f"quiz-{chunk.subject}-{chunk.chapter_no}-{chunk.section_no}-p{len(questions)}",
                question=text,
                type=str(item.get("type") or "short_answer"),
                marks=int(item.get("marks") or 2),
                source=QuizSource(
                    chapter_no=chunk.chapter_no,
                    section_no=chunk.section_no,
                    section_title=chunk.section_title,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    chunk_id=chunk.id,
                ),
                marking_key=MarkingKey(
                    expected_points=points,
                    guidance=str(
                        key.get("guidance")
                        or "Full marks for an answer that contains the expected points."
                    ),
                ),
            )
        )
        if len(questions) >= count:
            break
    return questions, None


def generate_quiz(subject: str, chapter_no: int, count: int = 5) -> QuizResult:
    """Quiz for one chapter. `questions: []` with a note when the chapter is not ingested."""
    settings = get_settings()
    started = time.perf_counter()
    if count < 1:
        raise ValueError("count must be at least 1")
    count = min(count, 20)  # a 20-question cap keeps the provider call bounded

    try:
        rows = db.chapter_chunks(subject, chapter_no, limit=200)
    except Exception as exc:
        raise RetrievalUnavailable(f"corpus database is not reachable: {exc}") from exc

    if not rows:
        return QuizResult(
            subject=subject,
            chapter_no=chapter_no,
            provider="retrieval-only",
            questions=[],
            note=(
                f"Chapter {chapter_no} of '{subject}' has no ingested chunks, so there is nothing "
                "to quiz on yet. Ingest the chapter and try again."
            ),
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    chunks = [RetrievedChunk.model_validate(row) for row in rows]

    if settings.provider_configured:
        questions, error = _provider_quiz(chunks, count)
        if questions and error is None:
            note = None
            if len(questions) < count:
                note = (
                    f"{count - len(questions)} of the requested questions were dropped because "
                    "their source chunk was not in this chapter's retrieved chunks."
                )
            return QuizResult(
                subject=subject,
                chapter_no=chapter_no,
                provider=settings.answer_provider.strip(),
                questions=questions,
                note=note,
                took_ms=int((time.perf_counter() - started) * 1000),
            )
        fallback = retrieval_only_quiz(chunks, count)
        return QuizResult(
            subject=subject,
            chapter_no=chapter_no,
            provider="retrieval-only",
            questions=fallback,
            note=(
                "The configured provider did not return usable questions, so these were built "
                "from the chapter's own sentences instead."
            ),
            degraded=True,
            provider_error=error,
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    questions = retrieval_only_quiz(chunks, count)
    note = None
    if len(questions) < count:
        note = (
            f"Only {len(questions)} of the requested {count} questions could be built from this "
            "chapter's chunks; the chapter may be short or its text heavily garbled."
        )
    return QuizResult(
        subject=subject,
        chapter_no=chapter_no,
        provider="retrieval-only",
        questions=questions,
        note=note,
        took_ms=int((time.perf_counter() - started) * 1000),
    )
