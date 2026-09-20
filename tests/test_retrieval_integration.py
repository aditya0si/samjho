"""Integration tests: real pgvector, real `bge-small-en-v1.5` embeddings, real cross-encoder.

`integration` throughout — these need Postgres (see `tests/conftest.py` for the docker command)
and download the two local models on first run. They are the tests that prove the ranking, the
refusal path and the citation contract against a database rather than against a stub.

The fixture corpus is six hand-written chunks (`tests/fixtures/synthetic_chunks.jsonl`) in two
synthetic subjects, loaded into the development database under subjects prefixed `fixture-` and
deleted again at the end of the session. A real ingested corpus in the same database is untouched.
"""

from __future__ import annotations

import re
import time
from typing import Any

import pytest

from api import answer as answer_mod
from api import db, retriever
from api import quiz as quiz_mod
from api.retriever import CITATION_RE, citation_label

pytestmark = pytest.mark.integration

SILVER = "fixture-science-1-1.2-8"
BALANCING = "fixture-science-1-1.1-2"
LEAVES = "fixture-science-1-1.2-9"
TURMERIC = "fixture-science-2-2.1-20"
QUADRATIC = "fixture-maths-1-1.1-5"
DISTANCE = "fixture-maths-1-1.2-6"

SILVER_QUESTION = "why does the silver chloride turn grey when it is left in sunlight"
BALANCING_QUESTION = "how do I balance a reaction statement by counting atoms"
QUADRATIC_QUESTION = "how many solutions does a quadratic statement have, read from the graph"
TURMERIC_QUESTION = "what colour does turmeric paste turn in a soapy liquid"
OUT_OF_CORPUS_QUESTION = "find the derivative of sin x with respect to x, using the chain rule"


def ranked_ids(chunks: list[retriever.RetrievedChunk]) -> list[str]:
    return [c.id for c in chunks]


def report(label: str, chunks: list[retriever.RetrievedChunk]) -> None:
    """Print the ranking so a human reading the test log sees the actual numbers."""
    lines = [f"{label}:"]
    for position, chunk in enumerate(chunks):
        lines.append(
            f"  #{position} {chunk.id} score={chunk.score:.4f} "
            f"rerank={chunk.rerank_score} rrf={chunk.rrf_score:.5f} "
            f"vector_rank={chunk.vector_rank} fts_rank={chunk.fts_rank}"
        )
    print("\n".join(lines))


# --------------------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------------------


def test_silver_chloride_question_ranks_the_right_chunk_first(indexed_corpus: dict[str, Any]) -> None:
    chunks = retriever.search("fixture-science", SILVER_QUESTION, None, 4)
    report(f"rank for {SILVER_QUESTION!r}", chunks)
    assert chunks, "retrieval returned nothing for an in-corpus question"
    assert chunks[0].id == SILVER, ranked_ids(chunks)
    assert chunks[0].score >= 0.35, chunks[0].score
    assert chunks[0].section_no == "1.2"
    assert chunks[0].page_start == 8


def test_balancing_question_ranks_its_own_chunk_first(indexed_corpus: dict[str, Any]) -> None:
    chunks = retriever.search("fixture-science", BALANCING_QUESTION, None, 4)
    report(f"rank for {BALANCING_QUESTION!r}", chunks)
    assert chunks[0].id == BALANCING, ranked_ids(chunks)


def test_maths_question_ranks_the_maths_chunk_first(indexed_corpus: dict[str, Any]) -> None:
    chunks = retriever.search("fixture-maths", QUADRATIC_QUESTION, None, 4)
    report(f"rank for {QUADRATIC_QUESTION!r}", chunks)
    assert chunks[0].id == QUADRATIC, ranked_ids(chunks)
    assert chunks[0].math_heavy is True


def test_leaves_passage_does_not_outrank_the_silver_passage(indexed_corpus: dict[str, Any]) -> None:
    """Both chunks live in §1.2 and both mention light; the question names silver chloride."""
    chunks = retriever.search("fixture-science", SILVER_QUESTION, None, 6)
    ids = ranked_ids(chunks)
    assert ids.index(SILVER) < ids.index(LEAVES), ids


def test_retrieval_returns_top_k_only(indexed_corpus: dict[str, Any]) -> None:
    chunks = retriever.search("fixture-science", SILVER_QUESTION, None, 2)
    assert len(chunks) == 2


def test_chapter_filter_confines_the_result_set(indexed_corpus: dict[str, Any]) -> None:
    chunks = retriever.search("fixture-science", TURMERIC_QUESTION, 1, 6)
    assert chunks, "chapter 1 should still return chunks for this question"
    assert {c.chapter_no for c in chunks} == {1}
    assert TURMERIC not in ranked_ids(chunks)


def test_empty_chapter_is_not_an_error(indexed_corpus: dict[str, Any]) -> None:
    assert retriever.search("fixture-science", SILVER_QUESTION, 99, 6) == []


def test_unknown_subject_is_not_an_error(indexed_corpus: dict[str, Any]) -> None:
    assert retriever.search("fixture-nonexistent", SILVER_QUESTION, None, 6) == []


# --------------------------------------------------------------------------------------
# both arms of the hybrid actually contribute
# --------------------------------------------------------------------------------------


def test_both_arms_return_candidates(
    indexed_corpus: dict[str, Any], fixture_chunks: list[dict[str, Any]]
) -> None:
    science_chunks = [r for r in fixture_chunks if r["subject"] == "fixture-science"]
    outcome = retriever.search_detailed("fixture-science", TURMERIC_QUESTION, None, 6)
    assert outcome.vector_candidates > 0
    assert outcome.fts_candidates > 0, "the full-text arm must contribute candidates"
    assert outcome.candidates > 0
    assert outcome.mode == "hybrid"
    assert outcome.reranked == len(outcome.chunks)
    assert outcome.corpus_chunks == len(science_chunks), (
        f"the corpus counter should see exactly the {len(science_chunks)} fixture-science chunks"
    )
    assert outcome.extra["fts_query"] == retriever.build_fts_query(TURMERIC_QUESTION)


def test_full_text_arm_finds_the_rare_term(indexed_corpus: dict[str, Any]) -> None:
    """'turmeric' appears in exactly one chunk. The FTS arm must surface it, and the fused
    result must carry a non-null fts_rank for it."""
    tsquery = retriever.build_fts_query(TURMERIC_QUESTION)
    rows = db.fts_search("fixture-science", tsquery, None, 10)
    assert tsquery, "the question must reduce to a usable tsquery"
    assert TURMERIC in [str(r["id"]) for r in rows], tsquery
    chunks = retriever.search("fixture-science", TURMERIC_QUESTION, None, 6)
    report(f"rank for {TURMERIC_QUESTION!r}", chunks)
    assert chunks[0].id == TURMERIC, ranked_ids(chunks)
    assert chunks[0].fts_rank is not None


def test_and_semantics_would_have_matched_nothing(indexed_corpus: dict[str, Any]) -> None:
    """Regression test for the bug that made the arm silently useless.

    `websearch_to_tsquery`/`plainto_tsquery` AND every term, so a question matches only a passage
    containing *all* of them — the turmeric chunk matches five of six terms and was therefore never
    a candidate, while the response still reported `mode: "hybrid"`. Both halves are asserted here:
    the AND form returns nothing, the OR form returns the chunk.
    """
    and_query = " & ".join(retriever.content_terms(TURMERIC_QUESTION))
    with db.cursor() as cur:
        and_rows = cur.execute(
            "SELECT id FROM chunks WHERE subject = %s AND tsv @@ to_tsquery('english', %s)",
            ("fixture-science", and_query),
        ).fetchall()
        or_rows = cur.execute(
            "SELECT id FROM chunks WHERE subject = %s AND tsv @@ to_tsquery('english', %s)",
            ("fixture-science", retriever.build_fts_query(TURMERIC_QUESTION)),
        ).fetchall()
    print(f"AND tsquery {and_query!r} -> {len(and_rows)} rows; OR tsquery -> {len(or_rows)} rows")
    assert and_rows == [], "the AND form is expected to match nothing (this is the bug's shape)"
    assert TURMERIC in [str(r["id"]) for r in or_rows]


# --------------------------------------------------------------------------------------
# the refusal path, against a real corpus
# --------------------------------------------------------------------------------------


def test_out_of_corpus_question_is_refused(indexed_corpus: dict[str, Any]) -> None:
    """The headline refusal test: a Class 12 calculus question against a corpus that has no
    calculus in it must come back refused, with a reason, and with no answer prose."""
    result = answer_mod.answer_question("fixture-science", OUT_OF_CORPUS_QUESTION)
    print(
        f"refusal: refused={result.refused} reason={result.refusal_reason}\n"
        f"  detail={result.refusal_detail}\n"
        f"  answer={result.answer!r}\n"
        f"  candidates={result.retrieval.candidates} reranked={result.retrieval.reranked} "
        f"corpus_chunks={result.retrieval.corpus_chunks} took_ms={result.retrieval.took_ms}"
    )
    assert result.refused is True
    assert result.refusal_reason in {"not_in_corpus", "below_threshold"}
    assert result.citations == []
    assert result.provider == "retrieval-only"
    # No invented prose: the answer is the fixed refusal sentence, nothing answer-shaped.
    assert result.answer == (
        "Not in your material: nothing in the ingested corpus supports an answer to this question."
    )
    for banned in ("derivative", "chain rule", "sin"):
        assert banned not in result.answer.lower()
    assert result.refusal_detail, "a refusal must explain itself"


def test_other_board_question_is_refused(indexed_corpus: dict[str, Any]) -> None:
    result = answer_mod.answer_question(
        "fixture-science", "state and prove the law of thermodynamics for an ideal gas"
    )
    assert result.refused is True
    assert result.refusal_reason in {"not_in_corpus", "below_threshold"}
    assert result.citations == []


def test_question_about_a_chapter_with_no_corpus_is_refused(indexed_corpus: dict[str, Any]) -> None:
    result = answer_mod.answer_question("fixture-science", SILVER_QUESTION, chapter_no=99)
    assert result.refused is True
    assert result.refusal_reason == "no_corpus"
    assert result.citations == []
    assert "fixture-science" in (result.refusal_detail or "")


def test_subject_with_no_corpus_at_all_is_refused(indexed_corpus: dict[str, Any]) -> None:
    result = answer_mod.answer_question("fixture-nothing-ingested", SILVER_QUESTION)
    assert result.refused is True
    assert result.refusal_reason == "no_corpus"
    assert result.citations == []
    assert result.retrieval.corpus_chunks == 0


# --------------------------------------------------------------------------------------
# the answer contract, against a real corpus
# --------------------------------------------------------------------------------------


def test_in_corpus_question_is_answered_with_traceable_citations(
    indexed_corpus: dict[str, Any],
) -> None:
    result = answer_mod.answer_question("fixture-science", SILVER_QUESTION, None, 4)
    print(f"answer provider={result.provider} refused={result.refused}\n{result.answer}")
    assert result.refused is False
    assert result.refusal_reason is None
    assert result.provider == "retrieval-only"
    assert result.provider_configured is False
    assert result.citations, "an answered question must carry citations"

    stored = db.chunks_by_ids([c.chunk_id for c in result.citations])
    assert set(stored) == {c.chunk_id for c in result.citations}, "citation points at no chunk"
    for citation in result.citations:
        row = stored[citation.chunk_id]
        assert citation.chapter_no == row["chapter_no"]
        assert citation.section_no == row["section_no"]
        assert citation.page_start == row["page_start"]
        assert citation.page_end == row["page_end"]
        assert citation.chapter_title == row["chapter_title"]
        assert 0.0 <= citation.score <= 1.0

    # Every [Ch …] marker in the prose must be one of the retrieved labels — nothing invented.
    allowed = {citation_label(chunk) for chunk in retriever.search("fixture-science", SILVER_QUESTION, None, 4)}
    labels = {m.group(0) for m in CITATION_RE.finditer(result.answer)}
    assert labels, "the prose must cite"
    assert labels <= allowed, labels - allowed
    assert "[Ch 1 §1.2 p.8]" in result.answer


def test_retrieval_only_quotes_are_verbatim_from_the_corpus(indexed_corpus: dict[str, Any]) -> None:
    result = answer_mod.answer_question("fixture-science", BALANCING_QUESTION, None, 4)
    assert result.refused is False
    quotes = re.findall(r'"([^"]{20,})"', result.answer)
    assert quotes
    corpus_text = " ".join(row["text"] for row in db.chapter_chunks("fixture-science", 1))
    for quote in quotes:
        assert quote in corpus_text, f"quote not found in the corpus: {quote!r}"


# --------------------------------------------------------------------------------------
# latency
#
# Retrieval latency here has two parts that behave completely differently under load:
#
#   * database + fusion work (this code's own cost): ~5-8 ms per query on an idle machine and
#     20-40 ms while other agents hammer the box. Stable, and where a regression would show up.
#   * local model inference (bge-small encode + cross-encoder rerank): CPU-bound, and it moves
#     with machine load. Warm end-to-end p50 measured across runs on this host: 356, 455, 502, 505,
#     567, 588, 680, 1583, 1612 ms; p95: 485, 578, 586, 615, 656, 820, 840, 880, 1193, 2000, 2024 ms.
#     The spread is the machine, not the code: the same loop reports min 207 ms in one run and min
#     1214 ms in another, with identical query results.
#
# Cold start is excluded on purpose: the first call in a process loads both models (measured 53.6 s
# inside the first /ask, mostly model load; ~1.8 s with a warm cache). api.main now warms them in a
# background thread at startup.
#
# The gate is therefore the stable part — the non-inference phases get a tight budget — while the
# end-to-end number is asserted only at 2x the worst p50/p95 ever measured on this host, which
# catches a real regression without failing because another agent started a build. Both
# distributions are printed on every run.
# --------------------------------------------------------------------------------------

DB_PHASE_P95_BUDGET_MS = 250  # measured 5-8 ms idle, 20-40 ms loaded: ~6x headroom
END_TO_END_P50_BUDGET_MS = 3200  # 2 x worst measured warm p50 (1612 ms)
END_TO_END_P95_BUDGET_MS = 4100  # 2 x worst measured warm p95 (2024 ms)
LATENCY_SAMPLES = 10


def _distribution(samples: list[float]) -> tuple[float, float, float, float]:
    ordered = sorted(samples)
    p50 = ordered[len(ordered) // 2]
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * len(ordered))) - 1)]
    return ordered[0], p50, p95, ordered[-1]


def test_retrieval_db_phase_latency(indexed_corpus: dict[str, Any]) -> None:
    """The gate: every retrieval phase that does not run a model, over 10 calls."""
    from api import embed as embed_mod

    vector = embed_mod.embed_query(SILVER_QUESTION)  # computed once, outside the measurement
    tsquery = retriever.build_fts_query(SILVER_QUESTION)
    ids = [c.id for c in retriever.search("fixture-science", SILVER_QUESTION, None, 6)]

    samples: list[float] = []
    for _ in range(LATENCY_SAMPLES):
        started = time.perf_counter()
        db.count_chunks("fixture-science")
        db.vector_search("fixture-science", vector, None, 24)
        db.fts_search("fixture-science", tsquery, None, 24)
        db.chunks_by_ids(ids)
        samples.append((time.perf_counter() - started) * 1000)

    minimum, p50, p95, maximum = _distribution(samples)
    print(
        f"db-phase latency over {LATENCY_SAMPLES} calls (no model): min={minimum:.1f} p50={p50:.1f} "
        f"p95={p95:.1f} max={maximum:.1f} ms (budget p95<{DB_PHASE_P95_BUDGET_MS} ms)"
    )
    assert p95 < DB_PHASE_P95_BUDGET_MS, (
        f"database/fusion p95 {p95:.1f} ms exceeds {DB_PHASE_P95_BUDGET_MS} ms "
        f"(samples: {[round(t, 1) for t in sorted(samples)]})"
    )


def test_search_latency(indexed_corpus: dict[str, Any]) -> None:
    """End-to-end steady state: cold start excluded, distribution reported, 2x-worst budget."""
    questions = [SILVER_QUESTION, BALANCING_QUESTION, TURMERIC_QUESTION, QUADRATIC_QUESTION]
    subjects = ["fixture-science", "fixture-science", "fixture-science", "fixture-maths"]

    # Warm-up: model load and first-touch page cache happen here, outside the measurement.
    retriever.search(subjects[0], questions[0], None, 6)
    retriever.search(subjects[3], questions[3], None, 6)

    timings: list[float] = []
    for index in range(LATENCY_SAMPLES):
        subject = subjects[index % len(subjects)]
        question = questions[index % len(questions)]
        started = time.perf_counter()
        retriever.search(subject, question, None, 6)
        timings.append((time.perf_counter() - started) * 1000)

    minimum, p50, p95, maximum = _distribution(timings)
    print(
        f"warm search latency over {LATENCY_SAMPLES} calls (incl. model inference): min={minimum:.0f} "
        f"p50={p50:.0f} p95={p95:.0f} max={maximum:.0f} ms "
        f"(budget p50<{END_TO_END_P50_BUDGET_MS} p95<{END_TO_END_P95_BUDGET_MS} ms)"
    )
    assert p50 < END_TO_END_P50_BUDGET_MS, (
        f"warm p50 {p50:.0f} ms exceeds {END_TO_END_P50_BUDGET_MS} ms "
        f"(samples: {[round(t) for t in sorted(timings)]})"
    )
    assert p95 < END_TO_END_P95_BUDGET_MS, (
        f"warm p95 {p95:.0f} ms exceeds {END_TO_END_P95_BUDGET_MS} ms "
        f"(samples: {[round(t) for t in sorted(timings)]})"
    )


def test_answer_latency(indexed_corpus: dict[str, Any]) -> None:
    answer_mod.answer_question("fixture-science", SILVER_QUESTION, None, 6)  # warm-up
    started = time.perf_counter()
    result = answer_mod.answer_question("fixture-science", SILVER_QUESTION, None, 6)
    took_ms = (time.perf_counter() - started) * 1000
    print(
        f"warm answer latency: {took_ms:.0f} ms end to end, retrieval took {result.retrieval.took_ms} ms "
        f"(candidates={result.retrieval.candidates}, reranked={result.retrieval.reranked})"
    )
    assert result.refused is False
    assert took_ms < END_TO_END_P95_BUDGET_MS * 2


# --------------------------------------------------------------------------------------
# quiz: only from the requested chapter, always with a source and a marking key
# --------------------------------------------------------------------------------------


def test_quiz_uses_only_the_requested_chapter(indexed_corpus: dict[str, Any]) -> None:
    result = quiz_mod.generate_quiz("fixture-science", 1, 3)
    assert result.provider == "retrieval-only"
    assert result.questions, result.note
    chapter_one = {str(r["id"]) for r in db.chapter_chunks("fixture-science", 1)}
    chapter_two = {str(r["id"]) for r in db.chapter_chunks("fixture-science", 2)}
    assert chapter_one and chapter_two
    for question in result.questions:
        assert question.source.chunk_id in chapter_one
        assert question.source.chunk_id not in chapter_two
        assert question.source.chapter_no == 1
        assert question.source.section_no in {"1.1", "1.2"}
        assert question.source.page_start >= 2
        assert question.marking_key.expected_points
        assert question.marking_key.guidance
        assert question.marks >= 1
    print(f"quiz: {len(result.questions)} questions, provider={result.provider}")
    for question in result.questions:
        print(f"  [{question.source.section_no} p.{question.source.page_start}] {question.question}")


def test_quiz_marking_keys_are_verbatim_corpus_sentences(indexed_corpus: dict[str, Any]) -> None:
    result = quiz_mod.generate_quiz("fixture-science", 1, 3)
    rows = {str(r["id"]): str(r["text"]) for r in db.chapter_chunks("fixture-science", 1)}
    for question in result.questions:
        source_text = rows[question.source.chunk_id]
        for point in question.marking_key.expected_points:
            assert point in source_text, f"marking key is not from the corpus: {point!r}"


def test_quiz_on_an_uningested_chapter_is_empty_and_says_why(indexed_corpus: dict[str, Any]) -> None:
    result = quiz_mod.generate_quiz("fixture-science", 99, 3)
    assert result.questions == []
    assert result.note and "no ingested chunks" in result.note
    assert result.provider == "retrieval-only"


# --------------------------------------------------------------------------------------
# schema: the indexes and the generated tsvector column actually exist
# --------------------------------------------------------------------------------------


def test_chunks_table_has_hnsw_and_gin_indexes(indexed_corpus: dict[str, Any]) -> None:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'chunks'"
        ).fetchall()
    defs = {row["indexname"]: row["indexdef"] for row in rows}
    print("indexes: " + "; ".join(sorted(defs)))
    assert any("hnsw" in d and "embedding" in d for d in defs.values()), defs
    assert any("gin" in d and "tsv" in d for d in defs.values()), defs


def test_tsv_is_a_generated_column(indexed_corpus: dict[str, Any]) -> None:
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT attgenerated, atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'tsv'"
        ).fetchone()
    assert row is not None, "chunks.tsv is missing"
    assert row["attgenerated"] == "s", "tsv must be GENERATED ALWAYS ... STORED"


def test_embedding_column_dimension_matches_config(indexed_corpus: dict[str, Any]) -> None:
    from api.config import get_settings

    with db.cursor() as cur:
        row = cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        ).fetchone()
    assert row is not None, "chunks.embedding is missing"
    assert row["atttypmod"] == get_settings().embedding_dim


def test_migrations_are_recorded(indexed_corpus: dict[str, Any]) -> None:
    with db.cursor() as cur:
        versions = [
            r["version"]
            for r in cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
    assert versions == [1, 2], versions
    assert db.init_schema() == [], "re-running migrations must be a no-op"


# --------------------------------------------------------------------------------------
# progress round-trip
# --------------------------------------------------------------------------------------


def test_progress_round_trip(indexed_corpus: dict[str, Any]) -> None:
    from api.progress import DEFAULT_STORE

    student = "fixture-student-1"
    with db.get_pool().connection() as conn:
        conn.execute("DELETE FROM quiz_attempts WHERE student_id = %s", (student,))
    recorded = DEFAULT_STORE.record(
        [
            {
                "student_id": student,
                "subject": "fixture-science",
                "chapter_no": 1,
                "section_no": "1.2",
                "question": "why does silver chloride turn grey?",
                "expected_key": "light splits it into silver metal and chlorine",
                "answer": "because of light",
                "correct": True,
            },
            {
                "student_id": student,
                "subject": "fixture-science",
                "chapter_no": 1,
                "section_no": "1.1",
                "question": "what does the number before a formula mean?",
                "expected_key": "how many units take part",
                "answer": "no idea",
                "correct": False,
            },
        ]
    )
    assert recorded == 2
    history = DEFAULT_STORE.history(student)
    assert len(history) == 1
    assert history[0]["chapter_no"] == 1
    assert history[0]["attempts"] == 2
    assert history[0]["correct"] == 1
    assert history[0]["accuracy"] == pytest.approx(0.5)
    print(f"progress: {history}")
    with db.get_pool().connection() as conn:
        conn.execute("DELETE FROM quiz_attempts WHERE student_id = %s", (student,))
