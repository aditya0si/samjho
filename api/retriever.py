"""Hybrid retrieval: pgvector cosine + Postgres full-text, fused with reciprocal-rank fusion,
then a local cross-encoder rerank.

    from api.retriever import search
    chunks = search("science", "why does the silver chloride turn grey in sunlight", 1, 6)

`search` is the frozen public entry point (CONTRACTS section 3) — the eval builder imports it by
name, so the signature and the `RetrievedChunk` fields are stable. `search_detailed` is the same
call with the retrieval telemetry the /ask response needs (candidate counts, timings).

Why RRF and not a weighted score sum: the two arms produce scores on incomparable scales
(`1 - cosine distance` is bounded, `ts_rank_cd` is not), and RRF only uses ranks, so the
`FTS_WEIGHT` knob stays meaningful instead of needing re-tuning whenever the corpus changes.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from . import db
from .config import get_settings

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been before
    being below between both but by can cannot could couldn't did didn't do does doesn't doing
    don't down during each few for from further had hadn't has hasn't have haven't having he her
    here hers herself him himself his how i if in into is isn't it its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our ours ourselves out over
    own same shan't she should shouldn't so some such than that the their theirs them themselves
    then there these they this those through to too under until up very was wasn't we were weren't
    what when where which while who whom why with won't would wouldn't you your yours yourself
    yourselves explain describe tell give state write why how what which does do
    """.split()
)

_WORD_RE = re.compile(r"[a-z0-9]+")

# Markers the student sees. Kept in one place so the answer builder, the refusal path and the
# tests all agree on what a citation looks like.
CITATION_RE = re.compile(r"\[Ch\s+(\d+)\s+§\s*([0-9.]+)\s+pp?\.\s*(\d+)(?:\s*[-–]\s*(\d+))?\]")


class RetrievedChunk(BaseModel):
    """One retrieved chunk. `score` is the number the refusal decision uses (0..1)."""

    id: str
    subject: str
    chapter_no: int
    chapter_title: str
    section_no: str
    section_title: str
    page_start: int
    page_end: int
    math_heavy: bool = False
    text: str
    score: float = Field(
        default=0.0, description="Final ranking score in 0..1 (reranker probability)."
    )
    vector_rank: int | None = None
    fts_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None

    @property
    def citation_label(self) -> str:
        return citation_label(self)


class RetrievalUnavailable(RuntimeError):
    """The corpus could not be read at all (database down). Not a refusal — an outage."""


@dataclass
class RetrievalOutcome:
    chunks: list[RetrievedChunk]
    mode: str
    candidates: int
    reranked: int
    took_ms: int
    vector_candidates: int = 0
    fts_candidates: int = 0
    corpus_chunks: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# pure helpers (unit-testable without a database)
# --------------------------------------------------------------------------------------


def citation_label(chunk: Any) -> str:
    """`[Ch 1 §1.1 p.2]`, or `pp.2-3` when the chunk spans pages."""
    start = int(chunk.page_start)
    end = int(chunk.page_end)
    pages = f"p.{start}" if end <= start else f"pp.{start}-{end}"
    return f"[Ch {int(chunk.chapter_no)} §{chunk.section_no} {pages}]"


def content_terms(text: str) -> list[str]:
    """Question words that carry meaning: lowercased, stopwords and 1-2 char noise dropped."""
    return [t for t in _WORD_RE.findall(text.lower()) if len(t) > 2 and t not in STOPWORDS]


def term_overlap_fraction(question: str, chunks: list[Any], top_n: int = 3) -> float:
    """Fraction of the question's content terms that appear in the top chunks' text.

    This is the lexical half of the refusal decision. The cross-encoder is the semantic half;
    it can score a plausible-looking passage highly for a question the passage does not answer,
    and this catches exactly that case. 0.0 means "none of the question's words are here".
    """
    terms = content_terms(question)
    if not terms:
        return 1.0  # nothing to check — do not refuse on a lexical technicality
    haystack = " ".join(str(c.text).lower() for c in chunks[:top_n])
    hits = sum(1 for t in terms if t in haystack)
    return hits / len(terms)


def rrf_fuse(
    vector_ids: list[str],
    fts_ids: list[str],
    fts_weight: float,
    k: int = 60,
) -> dict[str, dict[str, Any]]:
    """Reciprocal-rank fusion of two ranked id lists.

    score = (1 - fts_weight) * 1/(k + vector_rank) + fts_weight * 1/(k + fts_rank)

    A chunk found by only one arm keeps that arm's contribution. Weights come from
    `FTS_WEIGHT`; the vector arm gets the complement so the two always sum to 1.
    """
    if not 0.0 <= fts_weight <= 1.0:
        raise ValueError(f"fts_weight must be in [0, 1], got {fts_weight}")
    vector_weight = 1.0 - fts_weight
    fused: dict[str, dict[str, Any]] = {}
    for rank, chunk_id in enumerate(vector_ids):
        entry = fused.setdefault(chunk_id, {"rrf_score": 0.0, "vector_rank": None, "fts_rank": None})
        entry["vector_rank"] = rank
        entry["rrf_score"] += vector_weight * (1.0 / (k + rank + 1))
    for rank, chunk_id in enumerate(fts_ids):
        entry = fused.setdefault(chunk_id, {"rrf_score": 0.0, "vector_rank": None, "fts_rank": None})
        entry["fts_rank"] = rank
        entry["rrf_score"] += fts_weight * (1.0 / (k + rank + 1))
    return fused


def sigmoid(x: float) -> float:
    """Cross-encoder logits -> 0..1 so `REFUSAL_MIN_SCORE` means something fixed."""
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# --------------------------------------------------------------------------------------
# search
# --------------------------------------------------------------------------------------


def _row_to_chunk(row: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        id=str(row["id"]),
        subject=str(row["subject"]),
        chapter_no=int(row["chapter_no"]),
        chapter_title=str(row["chapter_title"]),
        section_no=str(row["section_no"]),
        section_title=str(row["section_title"]),
        page_start=int(row["page_start"]),
        page_end=int(row["page_end"]),
        math_heavy=bool(row["math_heavy"]),
        text=str(row["text"]),
    )


def build_fts_query(question: str, max_terms: int = 12) -> str:
    """Build the full-text arm's tsquery from a natural-language question.

    Why not `websearch_to_tsquery`/`plainto_tsquery`: both AND every term, which is exactly wrong
    for a question. Measured on the fixture corpus, "what colour does turmeric paste turn in a
    soapy liquid" becomes

        'colour' & 'turmer' & 'past' & 'turn' & 'soapi' & 'liquid'

    and the one chunk that does mention turmeric matches five of those six terms and is therefore
    *not returned at all* — the arm silently contributes nothing while the response still says
    `mode: "hybrid"`. OR-ing the terms is the correct shape here: this arm is a recall-oriented
    candidate generator, and precision is the reranker's job further down the pipeline.

    The terms are `content_terms` output, so they are `[a-z0-9]+` and cannot inject tsquery
    operators (`&`, `|`, `!`, `:`, parentheses) or break the syntax.
    """
    terms: list[str] = []
    for term in content_terms(question):
        if term not in terms:
            terms.append(term)
    return " | ".join(terms[:max_terms])


def search(
    subject: str,
    question: str,
    chapter_no: int | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Frozen entry point: hybrid retrieval, best chunks first, `top_k` of them.

    Returns `[]` when the corpus holds no chunks for the subject (or chapter) — an empty corpus
    is a supported state, not an error. Raises `RetrievalUnavailable` only when Postgres itself
    cannot be read.
    """
    return search_detailed(subject, question, chapter_no, top_k).chunks


def search_detailed(
    subject: str,
    question: str,
    chapter_no: int | None = None,
    top_k: int | None = None,
    *,
    candidates: int | None = None,
    rerank: bool | None = None,
) -> RetrievalOutcome:
    settings = get_settings()
    if not subject or not str(subject).strip():
        raise ValueError("subject is required")
    if not question or not str(question).strip():
        raise ValueError("question is required")
    top_k = int(top_k if top_k is not None else settings.retrieval_top_k)
    candidates = int(candidates if candidates is not None else settings.retrieval_candidates)
    use_rerank = settings.reranker_enabled if rerank is None else rerank
    started = time.perf_counter()

    try:
        corpus_chunks = db.count_chunks(subject, chapter_no)
    except Exception as exc:  # psycopg errors, pool timeouts — an outage, not a refusal
        raise RetrievalUnavailable(f"corpus database is not reachable: {exc}") from exc

    if corpus_chunks == 0:
        # Nothing to search. Do not even load the embedding model: this is the state the web app
        # runs in before a student ingests their book.
        return RetrievalOutcome(
            chunks=[],
            mode="hybrid",
            candidates=0,
            reranked=0,
            took_ms=int((time.perf_counter() - started) * 1000),
            corpus_chunks=0,
        )

    from . import embed as embed_mod

    cold_start = not embed_mod.model_loaded()
    query_vector = embed_mod.embed_query(question)
    tsquery = build_fts_query(question)
    vector_rows = db.vector_search(subject, query_vector, chapter_no, candidates)
    fts_rows = db.fts_search(subject, tsquery, chapter_no, candidates)

    vector_ids = [str(r["id"]) for r in vector_rows]
    fts_ids = [str(r["id"]) for r in fts_rows]
    fused = rrf_fuse(vector_ids, fts_ids, settings.fts_weight, settings.rrf_k)

    by_id = {str(r["id"]): r for r in vector_rows}
    for r in fts_rows:
        by_id.setdefault(str(r["id"]), r)
    missing = [cid for cid in fused if cid not in by_id]
    if missing:
        by_id.update(db.chunks_by_ids(missing))

    ordered = sorted(fused.items(), key=lambda kv: kv[1]["rrf_score"], reverse=True)
    if settings.rerank_candidates > 0:
        # Bound the cross-encoder's work to the best of the fusion. Truncating *before* reranking
        # (rather than reranking some and not others) keeps every returned score on one scale.
        ordered = ordered[: settings.rerank_candidates]
    chunks: list[RetrievedChunk] = []
    for chunk_id, ranks in ordered:
        row = by_id.get(chunk_id)
        if row is None:  # deleted between the two queries
            continue
        chunk = _row_to_chunk(row)
        chunk.rrf_score = float(ranks["rrf_score"])
        chunk.vector_rank = ranks["vector_rank"]
        chunk.fts_rank = ranks["fts_rank"]
        chunks.append(chunk)

    reranked = 0
    if use_rerank and chunks:
        reranked = _rerank(question, chunks)

    if not reranked:
        # Honest degradation: without a reranker the fused score is the only signal we have, so
        # it is rescaled into 0..1 and `reranked` reports 0 rather than pretending otherwise.
        top = chunks[0].rrf_score if chunks else 0.0
        for chunk in chunks:
            chunk.score = round(chunk.rrf_score / top, 6) if top else 0.0
    chunks = chunks[: max(top_k, 0)]

    return RetrievalOutcome(
        chunks=chunks,
        mode="hybrid" if settings.fts_weight > 0 else "vector-only",
        candidates=len(fused),
        reranked=reranked,
        took_ms=int((time.perf_counter() - started) * 1000),
        vector_candidates=len(vector_ids),
        fts_candidates=len(fts_ids),
        corpus_chunks=corpus_chunks,
        extra={
            "fts_query": tsquery,
            "reranker": settings.reranker_model if reranked else "",
            "cold_start": cold_start,
        },
    )


def _rerank(question: str, chunks: list[RetrievedChunk]) -> int:
    from . import embed as embed_mod

    try:
        logits = embed_mod.rerank_scores(question, [c.text for c in chunks])
    except Exception:
        # A reranker that will not load must not take the whole answer path down; the RRF order
        # is still a valid ranking and `reranked: 0` says so in the response.
        return 0
    if len(logits) != len(chunks):
        return 0
    for chunk, logit in zip(chunks, logits, strict=True):
        chunk.rerank_score = round(sigmoid(logit), 6)
        chunk.score = chunk.rerank_score
    chunks.sort(key=lambda c: (c.score, c.rrf_score), reverse=True)
    return len(chunks)


def chapter_overview(subject: str, chapter_no: int) -> dict[str, Any]:
    """Chunk counts per section for one chapter — feeds `GET /chapters/{subject}/{no}`."""
    counts = db.section_counts(subject)
    sections = {section: n for (chapter, section), n in counts.items() if chapter == chapter_no}
    return {"chunk_count": sum(sections.values()), "sections": sections}
