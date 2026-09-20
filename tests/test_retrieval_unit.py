"""Retrieval, refusal and answer-contract tests that need no database and no model download.

`unit` throughout. The integration half (real pgvector, real embeddings, real cross-encoder) is in
`tests/test_retrieval_integration.py`.

What is actually being proved here:

* the fixture matches the CONTRACTS section-2 chunk shape, so retrieval and ingest cannot drift;
* reciprocal-rank fusion behaves like RRF (agreement between arms beats a single strong arm) and
  honours `FTS_WEIGHT`;
* every refusal path returns `refused: true`, a reason from the frozen enum, no citations, and no
  prose that could be mistaken for an answer;
* a configured provider is **never called** once the evidence check has failed — the strongest
  guarantee available that a refusal cannot contain invented prose;
* a provider cannot inject a citation that was not retrieved, and its own words are checked;
* the retrieval-only answer quotes the corpus verbatim (asserted by substring against the source
  chunk, not by eyeballing).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from api import answer as answer_mod
from api import db
from api import quiz as quiz_mod
from api import syllabus as syllabus_mod
from api.config import get_settings
from api.retriever import (
    CITATION_RE,
    RetrievalOutcome,
    RetrievedChunk,
    build_fts_query,
    citation_label,
    content_terms,
    rrf_fuse,
    term_overlap_fraction,
)

pytestmark = pytest.mark.unit

CONTRACT_CHUNK_FIELDS = {
    "id": str,
    "subject": str,
    "chapter_no": int,
    "chapter_title": str,
    "section_no": str,
    "section_title": str,
    "page_start": int,
    "page_end": int,
    "math_heavy": bool,
    "text": str,
}


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def make_chunk(record: dict[str, Any], score: float = 0.9, **overrides: Any) -> RetrievedChunk:
    payload = {**record, "score": score, "rrf_score": score, "rerank_score": score}
    payload.update(overrides)
    return RetrievedChunk(**payload)


def outcome(chunks: list[RetrievedChunk], **kwargs: Any) -> RetrievalOutcome:
    defaults: dict[str, Any] = {
        "mode": "hybrid",
        "candidates": len(chunks),
        "reranked": len(chunks),
        "took_ms": 12,
        "vector_candidates": len(chunks),
        "fts_candidates": len(chunks),
        "corpus_chunks": len(chunks),
    }
    defaults.update(kwargs)
    return RetrievalOutcome(chunks=chunks, **defaults)


# --------------------------------------------------------------------------------------
# fixture + contract shape
# --------------------------------------------------------------------------------------


def test_fixture_matches_chunk_contract(fixture_chunks: list[dict[str, Any]]) -> None:
    for record in fixture_chunks:
        assert set(record) == set(CONTRACT_CHUNK_FIELDS), record["id"]
        for field, expected_type in CONTRACT_CHUNK_FIELDS.items():
            assert isinstance(record[field], expected_type), (record["id"], field)
        assert record["id"] == (
            f"{record['subject']}-{record['chapter_no']}-{record['section_no']}-{record['page_start']}"
        )
        assert record["page_end"] >= record["page_start"]
        assert 100 <= len(record["text"]) <= 1200, record["id"]


def test_fixture_ids_are_unique(fixture_chunks: list[dict[str, Any]]) -> None:
    ids = [r["id"] for r in fixture_chunks]
    assert len(ids) == len(set(ids))


def test_fixture_has_one_math_heavy_page(fixture_chunks: list[dict[str, Any]]) -> None:
    heavy = [r["id"] for r in fixture_chunks if r["math_heavy"]]
    assert heavy == ["fixture-maths-1-1.1-5"], heavy


def test_chunk_ids_never_span_chapters(fixture_chunks: list[dict[str, Any]]) -> None:
    """CONTRACTS section 2: chunks never span chapters — the id encodes chapter and section."""
    for record in fixture_chunks:
        assert record["id"].split("-")[3] == record["section_no"]


# --------------------------------------------------------------------------------------
# citation labels and content terms
# --------------------------------------------------------------------------------------


def test_citation_label_single_and_multi_page(fixture_chunks: list[dict[str, Any]]) -> None:
    single = make_chunk(fixture_chunks[1])
    assert citation_label(single) == "[Ch 1 §1.2 p.8]"
    multi = make_chunk(fixture_chunks[3])
    assert citation_label(multi) == "[Ch 2 §2.1 pp.20-21]"
    assert CITATION_RE.fullmatch("[Ch 1 §1.2 p.8]") is not None
    assert CITATION_RE.fullmatch("[Ch 2 §2.1 pp.20-21]") is not None


def test_content_terms_drop_stopwords_and_question_words() -> None:
    terms = content_terms("Why does the silver chloride turn grey in sunlight?")
    assert "silver" in terms and "chloride" in terms and "sunlight" in terms
    assert "the" not in terms and "why" not in terms and "does" not in terms
    assert "in" not in terms


def test_term_overlap_is_zero_for_a_different_topic(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1]), make_chunk(fixture_chunks[2])]
    assert term_overlap_fraction("Find the derivative of sin x", chunks) == 0.0
    assert term_overlap_fraction("why does silver chloride turn grey in sunlight", chunks) > 0.5


# --------------------------------------------------------------------------------------
# reciprocal-rank fusion
# --------------------------------------------------------------------------------------


def test_rrf_agreement_between_arms_wins() -> None:
    # `both` is 2nd in each arm; `vector_only` is 1st in the vector arm and absent from FTS.
    fused = rrf_fuse(
        vector_ids=["vector_only", "both", "tail"],
        fts_ids=["fts_only", "both"],
        fts_weight=0.4,
    )
    assert fused["both"]["rrf_score"] > fused["vector_only"]["rrf_score"]
    assert fused["both"]["vector_rank"] == 1
    assert fused["both"]["fts_rank"] == 1
    assert fused["fts_only"]["vector_rank"] is None
    assert fused["vector_only"]["fts_rank"] is None


def test_rrf_weight_controls_the_fts_arm() -> None:
    vector_ids = ["v1", "v2", "v3"]
    fts_ids = ["f1", "f2", "v2"]
    low = rrf_fuse(vector_ids, fts_ids, fts_weight=0.0)
    high = rrf_fuse(vector_ids, fts_ids, fts_weight=1.0)
    assert low["v1"]["rrf_score"] > low["f1"]["rrf_score"]
    assert high["f1"]["rrf_score"] > high["v1"]["rrf_score"]
    # the doc both arms found keeps a contribution from each, weighted by FTS_WEIGHT
    assert high["v2"]["rrf_score"] == pytest.approx(1 / 63)  # 1.0 * 1/(60+3) + 0.0
    assert low["v2"]["rrf_score"] == pytest.approx(1 / 62)  # 0.0 + 1.0 * 1/(60+2)


def test_rrf_rejects_an_out_of_range_weight() -> None:
    with pytest.raises(ValueError):
        rrf_fuse(["a"], ["b"], fts_weight=1.5)


# --------------------------------------------------------------------------------------
# the full-text arm's query shape (regression: AND semantics silently matched nothing)
# --------------------------------------------------------------------------------------


def test_build_fts_query_ors_the_content_terms() -> None:
    query = build_fts_query("What colour does turmeric paste turn in a soapy liquid?")
    assert "|" in query, query
    assert " & " not in query
    for term in ("colour", "turmeric", "soapy"):
        assert term in query
    assert "what" not in query and "does" not in query and "the" not in query


def test_build_fts_query_is_deduplicated_and_capped() -> None:
    assert build_fts_query("silver silver silver chloride") == "silver | chloride"
    long_query = build_fts_query(" ".join(f"term{index}" for index in range(40)), max_terms=12)
    assert long_query.count("|") == 11


def test_build_fts_query_cannot_inject_tsquery_operators() -> None:
    """The terms come from `content_terms`, so punctuation cannot break or rewrite the query."""
    query = build_fts_query("silver & chloride | grey ! sunlight (decompose) :* 'quote'")
    assert query == "silver | chloride | grey | sunlight | decompose | quote"


def test_build_fts_query_is_empty_without_content_terms() -> None:
    assert build_fts_query("what does the it do") == ""
    assert build_fts_query("") == ""


def test_fts_arm_skips_an_empty_query_without_touching_the_database() -> None:
    """No content terms means no arm, and no connection attempt: this returns before any query."""
    assert db.fts_search("science", "") == []
    assert db.fts_search("science", "   ") == []


def test_rrf_default_weight_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.config import reset_settings_cache

    monkeypatch.setenv("FTS_WEIGHT", "0.75")
    reset_settings_cache()
    assert get_settings().fts_weight == 0.75
    monkeypatch.delenv("FTS_WEIGHT")
    reset_settings_cache()
    assert get_settings().fts_weight == 0.4


# --------------------------------------------------------------------------------------
# evidence check
# --------------------------------------------------------------------------------------


def test_assess_evidence_no_chunks_is_no_corpus() -> None:
    verdict = answer_mod.assess_evidence("anything at all", [])
    assert verdict.ok is False
    assert verdict.reason == "no_corpus"


def test_assess_evidence_below_threshold(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1], score=0.2)]
    verdict = answer_mod.assess_evidence(
        "why does silver chloride turn grey in sunlight", chunks, min_score=0.35
    )
    assert verdict.ok is False
    assert verdict.reason == "below_threshold"
    assert verdict.top_score == pytest.approx(0.2)


def test_weak_band_refuses_when_the_question_words_are_absent(
    fixture_chunks: list[dict[str, Any]],
) -> None:
    """A mid-band score cannot rescue a question whose words are simply not in the passage."""
    chunks = [make_chunk(fixture_chunks[1], score=0.2)]
    verdict = answer_mod.assess_evidence("Find the integral of x squared", chunks)
    assert verdict.ok is False
    assert verdict.reason == "not_in_corpus"
    assert verdict.overlap == 0.0


def test_confident_score_answers_even_without_lexical_overlap(
    fixture_chunks: list[dict[str, Any]],
) -> None:
    """The over-refusal fix: a paraphrase that the reranker is sure about must be answered even
    when the student's words do not appear in the book's wording. Measured: this was refusing
    "why do fried snacks kept in the open begin to smell and taste unpleasant" (score 0.0970) on a
    real corpus, while the refusal set's highest score was 0.4359."""
    chunks = [make_chunk(fixture_chunks[1], score=0.97)]
    verdict = answer_mod.assess_evidence("how does the compound react when exposed to daylight", chunks)
    assert verdict.overlap == 0.0, "the fixture wording really does not share the question's words"
    assert verdict.ok is True
    assert verdict.reason is None


def test_evidence_bands_are_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.config import Settings, reset_settings_cache

    monkeypatch.setenv("REFUSAL_MIN_SCORE", "0.2")
    monkeypatch.setenv("REFUSAL_CONFIDENT_SCORE", "0.5")
    monkeypatch.setenv("REFUSAL_MIN_OVERLAP", "0.6")
    reset_settings_cache()
    settings = get_settings()
    assert settings.refusal_min_score == 0.2
    assert settings.refusal_confident_score == 0.5
    assert settings.refusal_min_overlap == 0.6

    # The shipped defaults, from the field definitions — independent of env vars and of any `.env`
    # on the machine (a developer's `.env` may still carry the old, uncalibrated 0.35).
    assert Settings.model_fields["refusal_min_score"].default == 0.05
    assert Settings.model_fields["refusal_confident_score"].default == 0.95
    assert Settings.model_fields["refusal_min_overlap"].default == 0.40
    reset_settings_cache()


def test_evidence_verdict_on_the_measured_boundaries(fixture_chunks: list[dict[str, Any]]) -> None:
    """Pin the decision at the calibrated values: 0.05 floor, 0.95 confident, 0.40 overlap."""
    from api.config import get_settings

    effective = get_settings()
    assert (
        effective.refusal_min_score,
        effective.refusal_confident_score,
        effective.refusal_min_overlap,
    ) == (0.05, 0.95, 0.40), (
        "the effective thresholds differ from the calibrated defaults. `tests/conftest.py` pins "
        "these for hermeticity, so a mismatch means that pin (or the field default in "
        "api/config.py) is out of date — the boundary assertions below are only meaningful at the "
        "calibrated values."
    )
    question = "why does silver chloride turn grey in sunlight"

    def verdict_for(score: float, text: str | None = None) -> answer_mod.EvidenceVerdict:
        candidate = make_chunk(fixture_chunks[1], score=score)
        if text is not None:
            candidate = candidate.model_copy(update={"text": text})
        return answer_mod.assess_evidence(question, [candidate])

    assert verdict_for(0.049).reason == "below_threshold"
    assert verdict_for(0.05).ok is True, "the floor is inclusive"
    assert verdict_for(0.89).ok is True, "0.89 clears the overlap requirement"
    assert verdict_for(0.95).ok is True, "the confident band is inclusive"
    # The counterexample that moved the confident line from 0.90 to 0.95: the maths refusal set
    # showed an off-syllabus question ("determinants / Cramer's rule", a Class 12 topic) scoring
    # 0.9073 with 0.20 lexical overlap, and it was answered out of a Class 10 book. Below the new
    # line, a high score without lexical support must be refused.
    assert verdict_for(0.9073, "the tangent to a curve at a point").reason == "not_in_corpus"
    # below the confident band and no lexical support -> refused
    assert verdict_for(0.5, "sunlight splits the salt into a metal and a gas").reason == "not_in_corpus"
    # below the confident band with enough lexical support -> answered
    assert verdict_for(0.5).ok is True


def test_assess_evidence_accepts_supported_question(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1], score=0.9)]
    verdict = answer_mod.assess_evidence("why does silver chloride turn grey in sunlight", chunks)
    assert verdict.ok is True
    assert verdict.reason is None


# --------------------------------------------------------------------------------------
# refusal paths
# --------------------------------------------------------------------------------------


def test_empty_corpus_refuses_with_no_corpus(fixture_chunks: list[dict[str, Any]]) -> None:
    result = answer_mod.build_from_chunks(
        "fixture-science", "why does silver chloride turn grey", outcome([])
    )
    assert result.refused is True
    assert result.refusal_reason == "no_corpus"
    assert result.citations == []
    assert result.provider == "retrieval-only"
    assert "nothing in the ingested corpus" in result.answer


def test_low_score_refuses_with_below_threshold(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1], score=0.01)]
    result = answer_mod.build_from_chunks(
        "fixture-science", "why does silver chloride turn grey in sunlight", outcome(chunks)
    )
    assert result.refused is True
    assert result.refusal_reason == "below_threshold"
    assert result.citations == []
    assert "0.010" in (result.refusal_detail or "")


def test_out_of_topic_refuses_with_not_in_corpus(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1], score=0.88)]
    result = answer_mod.build_from_chunks(
        "fixture-science", "Find the derivative of sin x with respect to x", outcome(chunks)
    )
    assert result.refused is True
    assert result.refusal_reason == "not_in_corpus"
    assert result.citations == []
    # A refusal must not smuggle in an answer-shaped sentence.
    assert result.answer == (
        "Not in your material: nothing in the ingested corpus supports an answer to this question."
    )
    assert not re.search(r"\bsin\b|\bderivative\b", result.answer, re.IGNORECASE)


def test_refusal_never_calls_a_configured_provider(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    """The core anti-fabrication guarantee: with a provider configured, an unsupported question
    still refuses *without* the provider ever being asked."""
    from api.config import reset_settings_cache

    monkeypatch.setenv("ANSWER_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.setenv("LLM_API_KEY", "sk-not-a-real-key")
    reset_settings_cache()
    assert get_settings().provider_configured is True

    def explode(*_args: Any, **_kwargs: Any) -> str:
        raise AssertionError("the provider must not be called when the evidence check fails")

    monkeypatch.setattr(answer_mod, "_call_llm", explode)
    chunks = [make_chunk(fixture_chunks[1], score=0.30)]
    result = answer_mod.build_from_chunks(
        "fixture-science", "Find the derivative of sin x", outcome(chunks)
    )
    assert result.refused is True
    assert result.refusal_reason == "not_in_corpus"
    assert result.provider_configured is True
    assert result.provider == "retrieval-only"
    reset_settings_cache()


def test_refusal_reason_is_always_from_the_frozen_enum(fixture_chunks: list[dict[str, Any]]) -> None:
    cases = [
        answer_mod.build_from_chunks("fixture-science", "q about silver chloride", outcome([])),
        answer_mod.build_from_chunks(
            "fixture-science",
            "why does silver chloride turn grey in sunlight",
            outcome([make_chunk(fixture_chunks[1], score=0.01)]),
        ),
        answer_mod.build_from_chunks(
            "fixture-science",
            "integrate x squared dx",
            outcome([make_chunk(fixture_chunks[1], score=0.40)]),
        ),
    ]
    for result in cases:
        assert result.refused is True
        assert result.refusal_reason in answer_mod.REFUSAL_REASONS
        assert result.citations == []


def test_refusal_points_at_the_closest_sections(fixture_chunks: list[dict[str, Any]]) -> None:
    """A refusal must not leave the student with nothing: the nearest passages are listed, with
    their honest scores, and are never presented as an answer."""
    chunks = [
        make_chunk(fixture_chunks[1], score=0.004),  # §1.2 silver chloride
        make_chunk(fixture_chunks[2], score=0.002),  # §1.2 leaves (same section: deduped)
        make_chunk(fixture_chunks[3], score=0.001),  # §2.1 indicators
    ]
    result = answer_mod.build_from_chunks(
        "fixture-science", "Find the derivative of sin x", outcome(chunks)
    )
    assert result.refused is True
    assert result.citations == [], "a pointer is not a citation"
    assert [c.section_no for c in result.closest] == ["1.2", "2.1"], "distinct sections, in score order"
    assert result.closest[0].score == pytest.approx(0.004)
    assert result.closest[0].chunk_id == fixture_chunks[1]["id"]
    assert result.closest[0].section_title
    assert "Closest passages in your material" in (result.refusal_detail or "")
    assert "§1.2" in (result.refusal_detail or "")
    # the pointer never becomes prose: the answer text stays the fixed refusal sentence
    assert result.answer == (
        "Not in your material: nothing in the ingested corpus supports an answer to this question."
    )


def test_refusal_with_no_retrieved_passages_has_no_closest(
    fixture_chunks: list[dict[str, Any]],
) -> None:
    result = answer_mod.build_from_chunks("fixture-science", "anything", outcome([]))
    assert result.refused is True
    assert result.closest == []
    assert "Closest passages" not in (result.refusal_detail or "")


def test_zero_scored_passages_are_not_offered_as_closest(
    fixture_chunks: list[dict[str, Any]],
) -> None:
    """A question from a completely different domain scores ~0 everywhere; pointing at a random
    section then would be worse than saying nothing."""
    chunks = [make_chunk(fixture_chunks[1], score=0.0), make_chunk(fixture_chunks[2], score=0.0)]
    result = answer_mod.build_from_chunks(
        "fixture-science", "What is the share price of Infosys today?", outcome(chunks)
    )
    assert result.refused is True
    assert result.closest == []


def test_answered_questions_carry_no_closest_list(fixture_chunks: list[dict[str, Any]]) -> None:
    result = answer_mod.build_from_chunks(
        "fixture-science",
        "why does silver chloride turn grey in sunlight",
        outcome([make_chunk(fixture_chunks[1], score=0.95)]),
    )
    assert result.refused is False
    assert result.closest == []


# --------------------------------------------------------------------------------------
# retrieval-only answer: verbatim quotes
# --------------------------------------------------------------------------------------


def test_retrieval_only_answer_quotes_verbatim(fixture_chunks: list[dict[str, Any]]) -> None:
    chunk = make_chunk(fixture_chunks[1], score=0.95)
    result = answer_mod.build_from_chunks(
        "fixture-science", "why does silver chloride turn grey in sunlight", outcome([chunk])
    )
    assert result.refused is False
    assert result.provider == "retrieval-only"
    assert result.provider_configured is False
    quotes = re.findall(r'"([^"]{20,})"', result.answer)
    assert quotes, result.answer
    for quote in quotes:
        assert quote in chunk.text, f"not verbatim: {quote!r}"
    assert "[Ch 1 §1.2 p.8]" in result.answer
    assert [c.chunk_id for c in result.citations] == [chunk.id]


def test_retrieval_only_answer_notes_math_heavy_pages(fixture_chunks: list[dict[str, Any]]) -> None:
    chunk = make_chunk(fixture_chunks[4], score=0.9)
    result = answer_mod.build_from_chunks(
        "fixture-maths",
        "how many solutions does a quadratic statement have",
        outcome([chunk]),
    )
    assert result.refused is False
    assert any("equation-heavy" in note for note in result.notes), result.notes


def test_citations_are_only_retrieved_chunks(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(fixture_chunks[1], score=0.95), make_chunk(fixture_chunks[2], score=0.4)]
    result = answer_mod.build_from_chunks(
        "fixture-science",
        "why does silver chloride turn grey in sunlight and what does light do in leaves",
        outcome(chunks),
    )
    assert result.refused is False
    allowed = {c.id for c in chunks}
    assert {c.chunk_id for c in result.citations} <= allowed
    labels_in_answer = {m.group(0) for m in CITATION_RE.finditer(result.answer)}
    allowed_labels = {citation_label(c) for c in chunks}
    assert labels_in_answer <= allowed_labels, labels_in_answer - allowed_labels


def test_weak_passages_are_not_quoted(fixture_chunks: list[dict[str, Any]]) -> None:
    """The real corpus produces the right chunk at 0.9999 and a runner-up at 0.0045; quoting that
    runner-up as "what your book says" would mislead a student, even though it shares a word."""
    strong = make_chunk(fixture_chunks[1], score=0.9999)
    weak = make_chunk(fixture_chunks[2], score=0.0045)
    result = answer_mod.build_from_chunks(
        "fixture-science", "why does silver chloride turn grey in sunlight", outcome([strong, weak])
    )
    assert result.refused is False
    assert [c.chunk_id for c in result.citations] == [strong.id]
    assert "silver chloride" in result.answer.lower()
    assert "leaves" not in result.answer.lower(), "a passage 200x weaker must not be quoted"


def test_quote_floor_is_relative_and_configurable(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    from api.config import reset_settings_cache

    strong = make_chunk(fixture_chunks[1], score=0.9)
    medium = make_chunk(fixture_chunks[2], score=0.5)
    monkeypatch.setenv("QUOTE_MIN_RATIO", "0.4")
    reset_settings_cache()
    quotes = answer_mod.select_quotes(
        "why does silver chloride turn grey in sunlight and what does light do in leaves",
        [strong, medium],
    )
    assert {chunk.id for chunk, _ in quotes} == {strong.id, medium.id}
    monkeypatch.setenv("QUOTE_MIN_RATIO", "0.9")
    reset_settings_cache()
    quotes = answer_mod.select_quotes(
        "why does silver chloride turn grey in sunlight and what does light do in leaves",
        [strong, medium],
    )
    assert {chunk.id for chunk, _ in quotes} == {strong.id}
    reset_settings_cache()


def test_cold_start_is_reported_in_the_notes(fixture_chunks: list[dict[str, Any]]) -> None:
    chunk = make_chunk(fixture_chunks[1], score=0.95)
    warm = answer_mod.build_from_chunks(
        "fixture-science", "why does silver chloride turn grey in sunlight", outcome([chunk])
    )
    assert warm.notes == [] and warm.retrieval.cold_start is False
    cold = answer_mod.build_from_chunks(
        "fixture-science",
        "why does silver chloride turn grey in sunlight",
        outcome([chunk], extra={"cold_start": True}),
    )
    assert cold.retrieval.cold_start is True
    assert any("load the local models" in note for note in cold.notes)


# --------------------------------------------------------------------------------------
# provider path: invented citations are impossible
# --------------------------------------------------------------------------------------


def test_provider_answer_drops_a_fabricated_citation_id(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    chunk = make_chunk(fixture_chunks[1], score=0.95)
    monkeypatch.setattr(
        answer_mod,
        "_call_llm",
        lambda _prompt: (
            '{"answer": "Silver chloride turns grey because light splits it into silver metal '
            '[Ch 1 §1.2 p.8] and also [Ch 9 §9.9 p.99].", '
            '"citation_ids": ["fixture-science-1-1.2-8", "science-9-9.9-99"], "insufficient": false}'
        ),
    )
    text, cited, stripped, error = answer_mod.provider_answer(
        "fixture-science", "why does silver chloride turn grey in sunlight", [chunk]
    )
    assert error is None
    assert "[Ch 9 §9.9 p.99]" not in text
    assert "[Ch 1 §1.2 p.8]" in text
    assert stripped == 1
    assert [c.id for c in cited] == [chunk.id]


def test_provider_insufficient_becomes_a_refusal(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    from api.config import reset_settings_cache

    monkeypatch.setenv("ANSWER_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    reset_settings_cache()
    monkeypatch.setattr(
        answer_mod, "_call_llm", lambda _prompt: '{"answer": "", "citation_ids": [], "insufficient": true}'
    )
    result = answer_mod.build_from_chunks(
        "fixture-science",
        "why does silver chloride turn grey in sunlight",
        outcome([make_chunk(fixture_chunks[1], score=0.95)]),
    )
    assert result.refused is True
    assert result.refusal_reason == "not_in_corpus"
    assert result.citations == []
    assert "reported that the retrieved passages do not answer" in (result.refusal_detail or "")
    reset_settings_cache()


def test_provider_answer_without_markers_gets_sources_appended(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    chunk = make_chunk(fixture_chunks[1], score=0.95)
    monkeypatch.setattr(
        answer_mod,
        "_call_llm",
        lambda _prompt: '{"answer": "Light splits silver chloride into grey silver metal.", '
        '"citation_ids": ["fixture-science-1-1.2-8"], "insufficient": false}',
    )
    text, cited, _stripped, error = answer_mod.provider_answer(
        "fixture-science", "why does silver chloride turn grey", [chunk]
    )
    assert error is None
    assert "[Ch 1 §1.2 p.8]" in text
    assert [c.id for c in cited] == [chunk.id]


def test_provider_failure_degrades_to_retrieval_only(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    from api.config import reset_settings_cache

    monkeypatch.setenv("ANSWER_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    reset_settings_cache()

    def boom(_prompt: str) -> str:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(answer_mod, "_call_llm", boom)
    result = answer_mod.build_from_chunks(
        "fixture-science",
        "why does silver chloride turn grey in sunlight",
        outcome([make_chunk(fixture_chunks[1], score=0.95)]),
    )
    assert result.refused is False
    assert result.degraded is True
    assert result.provider == "retrieval-only"
    assert result.provider_configured is True
    assert "TimeoutError" in (result.provider_error or "")
    assert result.citations and result.citations[0].chunk_id == fixture_chunks[1]["id"]
    reset_settings_cache()


def test_provider_non_json_output_is_reported_not_answered(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(answer_mod, "_call_llm", lambda _prompt: "Sure! Here is a nice answer.")
    text, cited, _stripped, error = answer_mod.provider_answer(
        "fixture-science", "why does silver chloride turn grey", [make_chunk(fixture_chunks[1])]
    )
    assert text == "" and cited == []
    assert error and "non-JSON" in error


def test_parse_llm_json_tolerates_a_markdown_fence() -> None:
    parsed = answer_mod._parse_llm_json('```json\n{"answer": "x", "insufficient": false}\n```')
    assert parsed == {"answer": "x", "insufficient": False}


# --------------------------------------------------------------------------------------
# quiz: sources and marking keys
# --------------------------------------------------------------------------------------


def test_retrieval_only_quiz_carries_source_and_key(fixture_chunks: list[dict[str, Any]]) -> None:
    chunks = [make_chunk(r) for r in fixture_chunks[:3]]
    questions = quiz_mod.retrieval_only_quiz(chunks, 3)
    assert len(questions) == 3
    by_id = {c.id: c for c in chunks}
    for question in questions:
        assert question.source.chunk_id in by_id
        assert question.source.section_no == by_id[question.source.chunk_id].section_no
        assert question.source.page_start == by_id[question.source.chunk_id].page_start
        assert question.marking_key.expected_points
        for point in question.marking_key.expected_points:
            assert point in by_id[question.source.chunk_id].text
        assert question.marks >= 1
        assert question.type in {"short_answer", "fill_in_the_blank"}


def test_quiz_never_invents_a_question_from_nothing() -> None:
    """A chunk too short to hold a usable sentence produces no question, rather than a made-up one."""
    tiny = RetrievedChunk(
        id="fixture-science-9-9.9-99",
        subject="fixture-science",
        chapter_no=9,
        chapter_title="Too Short",
        section_no="9.9",
        section_title="Barely There",
        page_start=99,
        page_end=99,
        math_heavy=False,
        text="See figure 9.1.",
    )
    assert quiz_mod.retrieval_only_quiz([tiny], 3) == []


def test_provider_quiz_drops_a_fabricated_source_chunk(
    monkeypatch: pytest.MonkeyPatch, fixture_chunks: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(
        quiz_mod,
        "_parse_json_object",
        lambda _raw: {
            "questions": [
                {
                    "question": "Real one?",
                    "type": "short_answer",
                    "marks": 2,
                    "source_chunk_id": fixture_chunks[0]["id"],
                    "marking_key": {"expected_points": ["something"], "guidance": "g"},
                },
                {
                    "question": "From a chapter that was not retrieved?",
                    "type": "short_answer",
                    "marks": 2,
                    "source_chunk_id": "science-7-7.7-77",
                    "marking_key": {"expected_points": ["made up"], "guidance": "g"},
                },
            ]
        },
    )
    monkeypatch.setattr(answer_mod, "_call_llm", lambda _prompt: "{}")
    questions, error = quiz_mod._provider_quiz([make_chunk(fixture_chunks[0])], 5)
    assert error is None
    assert [q.source.chunk_id for q in questions] == [fixture_chunks[0]["id"]]


# --------------------------------------------------------------------------------------
# licensing boundary: the syllabus endpoint can never leak book text
# --------------------------------------------------------------------------------------


def test_syllabus_exposes_structure_only() -> None:
    subjects = syllabus_mod.subjects()
    assert subjects, "data/syllabus/class10.json should be present and parseable"
    blob = repr(subjects)
    assert "'text':" not in blob and '"text":' not in blob
    for subject in subjects:
        for chapter in subject["chapters"]:
            assert set(chapter) <= {"no", "title", "pages", "status", "sections"}
            for section in chapter["sections"]:
                assert set(section) <= {"no", "title", "page"}


def test_syllabus_suggestion_is_lexical_not_invented() -> None:
    assert syllabus_mod.suggest_chapter("science", "zzz qqq vvv") is None
    hit = syllabus_mod.suggest_chapter("science", "what is a chemical reaction")
    subject = syllabus_mod.get_subject("science")
    assert subject is not None
    chapter_numbers = [c["no"] for c in subject["chapters"]]
    assert hit is None or hit["no"] in chapter_numbers
