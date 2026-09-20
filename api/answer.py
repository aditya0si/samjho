"""Answer building with citations, and refusal as a first-class result.

Three answer paths, and the response always says which one ran (`provider`) — it never lies about
it:

| path | when | `provider` |
|---|---|---|
| written answer | `ANSWER_PROVIDER` + `LLM_BASE_URL` + `LLM_MODEL` are all set | the provider name |
| retrieval-only | no provider configured, **or** the provider call failed (`degraded: true`) | `"retrieval-only"` |
| refusal | the evidence check failed, or the model itself reported `insufficient` | `"retrieval-only"` |

The refusal decision is made *before* any model is called. A question whose retrieved context does
not support an answer never reaches an LLM, so there is no path by which invented prose can leak
into a refusal. The retrieval-only path quotes the student's own corpus verbatim and cites it —
it never paraphrases, because a paraphrase with no model behind it is a fabrication with extra
steps.

Evidence check (`assess_evidence`) — two bands, both calibrated on measured true-positive and
true-negative distributions (the numbers and margins are in `api/config.py`):

* **confident** (score >= `REFUSAL_CONFIDENT_SCORE`) — the reranker is sure; answer. No lexical
  requirement, because a student's paraphrase may share few words with the book's wording and
  refusing it is the failure a study companion must not have.
* **weak** (>= `REFUSAL_MIN_SCORE`, below the confident band) — the reranker is unsure, so the
  question's own words must appear in the retrieved text (`REFUSAL_MIN_OVERLAP`). This is the
  guard against a plausible-looking passage that does not actually answer the question.
* **below the floor** — `below_threshold`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from . import retriever, syllabus
from .config import get_settings
from .retriever import (
    CITATION_RE,
    RetrievalOutcome,
    RetrievedChunk,
    citation_label,
    content_terms,
    term_overlap_fraction,
)

REFUSAL_REASONS = ("not_in_corpus", "no_corpus", "below_threshold")

MAX_QUOTES = 3
MAX_QUOTE_CHARS = 900
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")


# --------------------------------------------------------------------------------------
# response models (CONTRACTS section 3)
# --------------------------------------------------------------------------------------


class Citation(BaseModel):
    chapter_no: int
    section_no: str
    page_start: int
    page_end: int
    chapter_title: str
    section_title: str
    score: float = Field(description="Retrieval score of the chunk this citation points at, 0..1.")
    chunk_id: str = Field(description="Corpus chunk id, for tracing a citation back to ingest.")


class ClosestSection(BaseModel):
    """A passage the corpus *does* hold near the question — shown on a refusal, never as an answer.

    Refusing a question whose answer sits one rank away is worse than pointing at the section and
    letting the student decide. The score travels with it so the student can see how weak the match
    is; nothing here is claimed to answer the question.
    """

    chapter_no: int
    section_no: str
    section_title: str
    page_start: int
    page_end: int
    score: float
    chunk_id: str


class RetrievalInfo(BaseModel):
    mode: str
    candidates: int
    reranked: int
    took_ms: int
    vector_candidates: int = 0
    fts_candidates: int = 0
    corpus_chunks: int = 0
    cold_start: bool = Field(
        default=False,
        description="True when this request had to load the local models, so took_ms includes it.",
    )


class AnswerResult(BaseModel):
    answer: str = Field(description="Prose citing [Ch n §s p.p]; empty only if the corpus is empty.")
    citations: list[Citation] = Field(default_factory=list)
    refused: bool
    refusal_reason: str | None = Field(
        default=None, description="'not_in_corpus' | 'no_corpus' | 'below_threshold' | null"
    )
    retrieval: RetrievalInfo
    provider: str = Field(description="Which answer path ran. Never reports a model that did not.")
    refusal_detail: str | None = None
    closest: list[ClosestSection] = Field(
        default_factory=list,
        description="On a refusal: the nearest passages the corpus does hold, with their scores.",
    )
    provider_configured: bool = False
    degraded: bool = Field(
        default=False, description="True when a configured provider failed and retrieval-only ran."
    )
    provider_error: str | None = None
    notes: list[str] = Field(default_factory=list)
    stripped_citations: int = Field(
        default=0, description="Citation markers the model produced that are not in the context."
    )


@dataclass
class EvidenceVerdict:
    ok: bool
    reason: str | None
    top_score: float
    overlap: float


# --------------------------------------------------------------------------------------
# evidence check
# --------------------------------------------------------------------------------------


def assess_evidence(
    question: str,
    chunks: list[RetrievedChunk],
    *,
    min_score: float | None = None,
    confident: float | None = None,
    min_overlap: float | None = None,
) -> EvidenceVerdict:
    """Decide whether the retrieved context supports an answer.

    Two bands, both calibrated on measured true-positive and true-negative distributions (see
    `api/config.py` for the numbers and margins):

    * **confident** — the reranker is sure (>= REFUSAL_CONFIDENT_SCORE). Answer. No lexical
      requirement: a student's paraphrase of a passage that matches it perfectly may share few
      words with the book's wording, and refusing that is the failure mode a study companion must
      not have.
    * **weak** — between REFUSAL_MIN_SCORE and the confident band. The reranker is unsure, so the
      answer must additionally be supported by the question's own words appearing in the retrieved
      text (>= REFUSAL_MIN_OVERLAP). This is the guard against a plausible-looking passage that
      does not actually answer the question.
    * **below the floor** — refused as `below_threshold`.
    """
    settings = get_settings()
    min_score = settings.refusal_min_score if min_score is None else min_score
    confident = settings.refusal_confident_score if confident is None else confident
    min_overlap = settings.refusal_min_overlap if min_overlap is None else min_overlap
    if not chunks:
        return EvidenceVerdict(False, "no_corpus", 0.0, 0.0)
    top_score = float(chunks[0].score)
    overlap = term_overlap_fraction(question, chunks)
    if top_score < min_score:
        return EvidenceVerdict(False, "below_threshold", top_score, overlap)
    if top_score < confident and overlap < min_overlap:
        return EvidenceVerdict(False, "not_in_corpus", top_score, overlap)
    return EvidenceVerdict(True, None, top_score, overlap)


def _refusal_detail(
    subject: str, question: str, verdict: EvidenceVerdict, chunks: list[RetrievedChunk]
) -> str:
    settings = get_settings()
    if verdict.reason == "no_corpus":
        return (
            f"The ingested corpus has no chunks for subject '{subject}', so there is nothing to "
            "answer from. Ingest your copy of the book with "
            "`python -m api.db load corpus/chunks/<subject>.jsonl` and ask again."
        )
    if verdict.reason == "below_threshold":
        detail = (
            f"The closest passage in your corpus scores {verdict.top_score:.3f}, below the "
            f"REFUSAL_MIN_SCORE floor of {settings.refusal_min_score:g}. Samjho will not guess at "
            "an answer from a passage that weak."
        )
    else:
        detail = (
            f"The best passage scores {verdict.top_score:.3f}, which is not confident enough "
            f"(REFUSAL_CONFIDENT_SCORE is {settings.refusal_confident_score:g}) and only "
            f"{verdict.overlap:.0%} of the question's key words appear in the retrieved text "
            f"(REFUSAL_MIN_OVERLAP is {settings.refusal_min_overlap:.0%}), so the material does "
            "not cover this."
        )
    suggestion = syllabus.suggest_chapter(subject, question)
    if suggestion:
        detail += (
            f" The syllabus lists Chapter {suggestion['no']} “{suggestion['title']}”; that chapter "
            "is not part of the ingested text."
        )
    return detail


# --------------------------------------------------------------------------------------
# retrieval-only answers (no provider configured)
# --------------------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.replace("\n", " "))]
    return [p for p in parts if len(p) > 25]


def select_quotes(question: str, chunks: list[RetrievedChunk], max_quotes: int = MAX_QUOTES) -> list[
    tuple[RetrievedChunk, str]
]:
    """Pick the passages that actually answer the question: highest content-term overlap first,
    verbatim, never reworded.

    Only passages whose score is close to the best one are eligible. On the real corpus the
    cross-encoder puts the right chunk at 0.9999 and the next at 0.0045; quoting that runner-up as
    "what your own copy of the book says" would be misleading, even though it shares a word.
    """
    settings = get_settings()
    floor = settings.quote_min_ratio * float(chunks[0].score) if chunks else 0.0
    eligible = [chunk for chunk in chunks if float(chunk.score) >= floor and float(chunk.score) > 0.0]
    terms = set(content_terms(question))
    scored: list[tuple[float, int, RetrievedChunk, str]] = []
    for chunk_index, chunk in enumerate(eligible):
        for sentence in _sentences(chunk.text):
            words = set(content_terms(sentence))
            hits = len(terms & words)
            if hits == 0:
                continue
            scored.append((hits / max(len(terms), 1), -chunk_index, chunk, sentence))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)

    picked: list[tuple[RetrievedChunk, str]] = []
    used_ids: set[str] = set()
    chars = 0
    for _, _, chunk, sentence in scored:
        if len(picked) >= max_quotes or chars + len(sentence) > MAX_QUOTE_CHARS:
            continue
        if chunk.id in used_ids:
            continue
        picked.append((chunk, sentence))
        used_ids.add(chunk.id)
        chars += len(sentence)
    return picked


def retrieval_only_answer(
    subject: str, question: str, chunks: list[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk], list[str]]:
    """Quote the corpus verbatim, with citations. Returns (text, cited_chunks, notes)."""
    quotes = select_quotes(question, chunks)
    notes: list[str] = []
    if not quotes:
        # Nothing in the retrieved text shares a word with the question. That is a refusal, and
        # the caller checks the evidence verdict first, so this is a safety net rather than a path.
        return "", [], notes
    lines = [
        "No language model is configured, so here is what your own copy of the book says — "
        "quoted word for word, not summarised:",
        "",
    ]
    for chunk, sentence in quotes:
        lines.append(f'{citation_label(chunk)} "{sentence}"')
        lines.append("")
    lines.append(
        "Set ANSWER_PROVIDER (and LLM_BASE_URL / LLM_MODEL) for a written answer; this "
        "retrieval-only path is what runs with no key configured."
    )
    cited = [chunk for chunk, _ in quotes]
    if any(chunk.math_heavy for chunk in cited):
        notes.append(
            "One of these pages is equation-heavy, and the PDF text layer can garble symbols; "
            "read the formulas from the printed page rather than from the quoted text."
        )
    return "\n".join(lines).strip(), cited, notes


# --------------------------------------------------------------------------------------
# provider answers
# --------------------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are Samjho, a study companion for a CBSE Class 10 student in India.

Answer the student's question using ONLY the numbered passages below, which come from the \
student's own copy of their textbook.

Rules:
1. Every sentence that makes a claim must end with a citation copied exactly from the passage \
header, e.g. [Ch 1 §1.1 p.2]. Never invent a citation, a page number or a quotation.
2. If the passages do not answer the question, do not use outside knowledge: reply with \
"insufficient": true.
3. Answer in 2-5 sentences of plain prose, at the level of a Class 10 student.
4. Reply with JSON only, no markdown fence: \
{{"answer": "...", "citation_ids": ["..."], "insufficient": false}}

Passages:
{context}

Student question: {question}
"""


def _build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for chunk in chunks:
        blocks.append(
            f"[{chunk.id}] {citation_label(chunk)} {chunk.chapter_title} — {chunk.section_title}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(blocks)


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
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


def _call_llm(prompt: str) -> str:
    settings = get_settings()
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": settings.llm_max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    with httpx.Client(timeout=settings.llm_timeout_s) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected provider response shape: {data!r:.200}") from exc


def _canonical_label(match: re.Match[str]) -> str:
    """`[Ch 1 §1.1 p. 2]` and `[Ch 1 §1.1 pp.2-3]` both normalise to the label `citation_label`
    produces, so a model's spacing cannot smuggle in an unrecognised citation."""
    start = int(match.group(3))
    end = int(match.group(4) or start)
    pages = f"p.{start}" if end <= start else f"pp.{start}-{end}"
    return f"[Ch {int(match.group(1))} §{match.group(2)} {pages}]"


def sanitize_citation_labels(text: str, allowed: set[str]) -> tuple[str, int]:
    """Strip any `[Ch …]` marker the model produced that is not one of the retrieved labels.

    This is the mechanical guarantee behind "no invented citation": the model can only point at
    passages that were actually retrieved, because every other marker is removed here.
    """
    stripped = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal stripped
        label = _canonical_label(match)
        if label in allowed:
            return label
        stripped += 1
        return ""

    cleaned = CITATION_RE.sub(repl, text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned, stripped


def _citations_from(chunks: list[RetrievedChunk]) -> list[Citation]:
    return [
        Citation(
            chapter_no=chunk.chapter_no,
            section_no=chunk.section_no,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            chapter_title=chunk.chapter_title,
            section_title=chunk.section_title,
            score=round(float(chunk.score), 4),
            chunk_id=chunk.id,
        )
        for chunk in chunks
    ]


def provider_answer(
    subject: str, question: str, chunks: list[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk], int, str | None]:
    """One provider call. Returns (answer, cited_chunks, stripped_citations, error).

    An error is returned rather than raised: the caller degrades to retrieval-only and says so.
    """
    allowed = {citation_label(chunk) for chunk in chunks}
    prompt = PROMPT_TEMPLATE.format(context=_build_context(chunks), question=question.strip())
    try:
        raw = _call_llm(prompt)
    except Exception as exc:  # network, auth, HTTP, timeout — all the same to the student
        return "", [], 0, f"{type(exc).__name__}: {exc}"

    parsed = _parse_llm_json(raw)
    if parsed is None:
        return "", [], 0, f"provider returned non-JSON output: {raw.strip()[:160]!r}"
    if parsed.get("insufficient") is True:
        return "", [], 0, None  # signals "model itself refused"; caller turns this into a refusal

    answer_text, stripped = sanitize_citation_labels(str(parsed.get("answer") or ""), allowed)
    if not answer_text.strip():
        return "", [], stripped, "provider returned an empty answer"

    claimed = [str(cid) for cid in parsed.get("citation_ids") or [] if str(cid)]
    by_id = {chunk.id: chunk for chunk in chunks}
    cited = [by_id[cid] for cid in claimed if cid in by_id]

    # Any label the model actually used in the prose is a citation too, even if it forgot to list
    # the id. Never the reverse: a claimed id with no marker does not become a citation.
    used_labels = {_canonical_label(m) for m in CITATION_RE.finditer(answer_text)}
    for chunk in chunks:
        if citation_label(chunk) in used_labels and chunk not in cited:
            cited.append(chunk)
    if not cited:
        return "", [], stripped, "provider answer cited no retrieved passage"
    if not used_labels:
        answer_text = answer_text.rstrip() + " Sources: " + " ".join(
            citation_label(chunk) for chunk in cited
        )
    return answer_text, cited, stripped, None


# --------------------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------------------


def _closest_sections(chunks: list[RetrievedChunk], limit: int = 3) -> list[ClosestSection]:
    """Up to `limit` distinct sections nearest the question, with their honest scores.

    Distinct sections, not distinct chunks: three chunks of one section tell the student nothing
    more than one does. Only passages the reranker scored above zero are listed, so a question in a
    completely different domain (score ~0) produces no misleading pointer.
    """
    out: list[ClosestSection] = []
    seen: set[tuple[int, str]] = set()
    for chunk in chunks:
        key = (chunk.chapter_no, chunk.section_no)
        if key in seen or float(chunk.score) <= 0.0:
            continue
        seen.add(key)
        out.append(
            ClosestSection(
                chapter_no=chunk.chapter_no,
                section_no=chunk.section_no,
                section_title=chunk.section_title,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=round(float(chunk.score), 6),
                chunk_id=chunk.id,
            )
        )
        if len(out) >= limit:
            break
    return out


def _refusal(
    reason: str,
    detail: str,
    outcome: RetrievalOutcome,
    *,
    provider_error: str | None = None,
    degraded: bool = False,
    notes: list[str] | None = None,
    stripped: int = 0,
) -> AnswerResult:
    settings = get_settings()
    assert reason in REFUSAL_REASONS, reason
    closest = _closest_sections(outcome.chunks)
    if closest:
        listed = ", ".join(
            f"§{c.section_no} {c.section_title} (p.{c.page_start}, score {c.score:.2f})" for c in closest
        )
        detail = f"{detail} Closest passages in your material: {listed}."
    return AnswerResult(
        answer="Not in your material: nothing in the ingested corpus supports an answer to this question.",
        citations=[],
        refused=True,
        refusal_reason=reason,
        refusal_detail=detail,
        closest=closest,
        retrieval=_retrieval_info(outcome),
        provider="retrieval-only",
        provider_configured=settings.provider_configured,
        degraded=degraded,
        provider_error=provider_error,
        notes=notes or [],
        stripped_citations=stripped,
    )


def _retrieval_info(outcome: RetrievalOutcome) -> RetrievalInfo:
    return RetrievalInfo(
        mode=outcome.mode,
        candidates=outcome.candidates,
        reranked=outcome.reranked,
        took_ms=outcome.took_ms,
        vector_candidates=outcome.vector_candidates,
        fts_candidates=outcome.fts_candidates,
        corpus_chunks=outcome.corpus_chunks,
        cold_start=bool(outcome.extra.get("cold_start", False)),
    )


def _cold_start_note(outcome: RetrievalOutcome) -> list[str]:
    if not outcome.extra.get("cold_start"):
        return []
    return [
        f"This request had to load the local models, so retrieval took {outcome.took_ms} ms; "
        "subsequent questions skip that startup cost."
    ]


def build_from_chunks(
    subject: str, question: str, outcome: RetrievalOutcome
) -> AnswerResult:
    """The whole answer policy, given an already-retrieved context. Unit-testable with no DB."""
    settings = get_settings()
    verdict = assess_evidence(question, outcome.chunks)
    if not verdict.ok:
        assert verdict.reason is not None
        return _refusal(verdict.reason, _refusal_detail(subject, question, verdict, outcome.chunks), outcome)

    provider_error: str | None = None
    stripped = 0
    if settings.provider_configured:
        answer_text, cited, stripped, provider_error = provider_answer(subject, question, outcome.chunks)
        if provider_error is None and answer_text and cited:
            return AnswerResult(
                answer=answer_text,
                citations=_citations_from(cited),
                refused=False,
                refusal_reason=None,
                retrieval=_retrieval_info(outcome),
                provider=settings.answer_provider.strip(),
                provider_configured=True,
                stripped_citations=stripped,
                notes=_cold_start_note(outcome),
            )
        if provider_error is None:
            # The model itself said the passages do not answer the question.
            detail = (
                f"The configured provider ({settings.answer_provider}) reported that the "
                "retrieved passages do not answer this question."
            )
            return _refusal("not_in_corpus", detail, outcome, stripped=stripped)

    answer_text, cited, notes = retrieval_only_answer(subject, question, outcome.chunks)
    if not answer_text or not cited:
        # Safety net: the evidence check passed but no quotable sentence matched. Refuse rather
        # than emit prose that is not backed by the corpus.
        return _refusal(
            "not_in_corpus",
            "No sentence in the retrieved passages shares a key word with the question.",
            outcome,
        )
    return AnswerResult(
        answer=answer_text,
        citations=_citations_from(cited),
        refused=False,
        refusal_reason=None,
        retrieval=_retrieval_info(outcome),
        provider="retrieval-only",
        provider_configured=settings.provider_configured,
        degraded=provider_error is not None,
        provider_error=provider_error,
        notes=notes + _cold_start_note(outcome),
    )


def answer_question(
    subject: str,
    question: str,
    chapter_no: int | None = None,
    top_k: int | None = None,
) -> AnswerResult:
    """Retrieve, then answer or refuse. Raises `RetrievalUnavailable` if Postgres is down."""
    outcome = retriever.search_detailed(subject, question, chapter_no, top_k)
    return build_from_chunks(subject, question, outcome)
