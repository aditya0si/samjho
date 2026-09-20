"""API contract tests with a stubbed retriever: no database, no model, no provider.

`unit` throughout. The retriever and the answer/quiz builders are replaced through FastAPI's
dependency overrides, so these tests pin the *contract* — paths, status codes, response shapes —
while `tests/test_retrieval_integration.py` pins the behaviour behind them.

The stubs are not mocks of the answer logic: where a response needs an answer, the test builds it
with the real (pure) `answer.build_from_chunks` / `quiz.retrieval_only_quiz`, so the shape asserted
here is the shape the real code produces.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import answer as answer_mod
from api import main as main_mod
from api import quiz as quiz_mod
from api.retriever import RetrievalOutcome, RetrievalUnavailable, RetrievedChunk

pytestmark = pytest.mark.unit

EMPTY_CORPUS = {"available": True, "subjects": {}, "chunks": 0}
NO_DATABASE = {"available": False, "subjects": {}, "chunks": 0}

CONTRACT_ASK_KEYS = {
    "answer",
    "citations",
    "refused",
    "refusal_reason",
    "retrieval",
    "provider",
}
CONTRACT_RETRIEVAL_KEYS = {"mode", "candidates", "reranked", "took_ms"}

CHUNK = RetrievedChunk(
    id="fixture-science-1-1.2-8",
    subject="science",
    chapter_no=1,
    chapter_title="Everyday Reactions in the Kitchen",
    section_no="1.2",
    section_title="Reactions That Need Light",
    page_start=8,
    page_end=8,
    math_heavy=False,
    text=(
        "Silver chloride is a pale white solid that turns grey when it is left in sunlight. "
        "Light supplies the energy that splits it into silver metal and chlorine gas."
    ),
    score=0.94,
    rerank_score=0.94,
    rrf_score=0.02,
)

SILVER_QUESTION = "why does silver chloride turn grey in sunlight"


class InMemoryStore:
    """Stand-in for `api.progress.ProgressStore`, aggregated the way `db.progress_rows` does."""

    name = "memory"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.rows: list[dict[str, Any]] = []

    def available(self) -> bool:
        return self._available

    def record(self, attempts: list[dict[str, Any]]) -> int:
        self.rows.extend(attempts)
        return len(attempts)

    def history(self, student_id: str, subject: str | None = None) -> list[dict[str, Any]]:
        agg: dict[tuple[str, int], dict[str, Any]] = {}
        for row in self.rows:
            if row["student_id"] != student_id:
                continue
            if subject and row["subject"] != subject:
                continue
            key = (row["subject"], row["chapter_no"])
            entry = agg.setdefault(
                key,
                {
                    "subject": row["subject"],
                    "chapter_no": row["chapter_no"],
                    "attempts": 0,
                    "correct": 0,
                    "last_attempt": None,
                },
            )
            entry["attempts"] += 1
            entry["correct"] += 1 if row["correct"] else 0
        out = []
        for entry in agg.values():
            entry["accuracy"] = round(entry["correct"] / entry["attempts"], 4)
            out.append(entry)
        return sorted(out, key=lambda r: (r["subject"], r["chapter_no"]))


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """TestClient that cannot read a live database.

    Startup is patched to see no database, and every corpus-reading function the endpoints can
    reach is stubbed to the empty-corpus answer. Without those stubs these tests would assert the
    accidental contents of whatever database happens to be running — the shared development
    database does hold a real ingested corpus, so a unit test that reads it is a bug.
    """
    monkeypatch.setattr(main_mod.db, "available", lambda *a, **k: False)
    monkeypatch.setattr(main_mod.db, "chapter_counts", lambda subject: {})
    monkeypatch.setattr(main_mod.db, "section_counts", lambda subject: {})
    monkeypatch.setattr(main_mod.db, "subjects_in_corpus", lambda: [])
    main_mod.app.dependency_overrides[main_mod.get_corpus_info] = lambda: dict(EMPTY_CORPUS)
    with TestClient(main_mod.app) as test_client:
        yield test_client
    main_mod.app.dependency_overrides.clear()


def use_corpus_info(info: dict[str, Any]) -> None:
    main_mod.app.dependency_overrides[main_mod.get_corpus_info] = lambda: dict(info)


def stub_answer(fn) -> None:
    main_mod.app.dependency_overrides[main_mod.get_answer_fn] = lambda: fn


def stub_quiz(fn) -> None:
    main_mod.app.dependency_overrides[main_mod.get_quiz_fn] = lambda: fn


def stub_store(store: InMemoryStore) -> None:
    main_mod.app.dependency_overrides[main_mod.get_progress_store] = lambda: store


def outcome(chunks: list[RetrievedChunk], **kwargs: Any) -> RetrievalOutcome:
    defaults: dict[str, Any] = {
        "mode": "hybrid",
        "candidates": len(chunks),
        "reranked": len(chunks),
        "took_ms": 7,
        "vector_candidates": len(chunks),
        "fts_candidates": len(chunks),
        "corpus_chunks": len(chunks),
    }
    defaults.update(kwargs)
    return RetrievalOutcome(chunks=chunks, **defaults)


# --------------------------------------------------------------------------------------
# /health
# --------------------------------------------------------------------------------------


def test_health_with_no_corpus_and_no_provider(client: TestClient) -> None:
    """The supported zero-configuration state: the app must serve this, not 500 on it."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["corpus_chunks"] == 0
    assert body["provider"] == "retrieval-only"
    assert body["db"] == "ok"
    assert body["syllabus"] == "ok"
    assert body["embedding_model"] == "BAAI/bge-small-en-v1.5"
    assert body["embedding_model_loaded"] is False, "health must not trigger a model download"
    assert body["reranker_loaded"] is False


def test_health_degrades_without_a_database(client: TestClient) -> None:
    use_corpus_info(NO_DATABASE)
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["db"] == "unavailable"
    assert body["corpus_chunks"] == 0


def test_health_survives_a_throwing_database_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_mod.app.dependency_overrides.pop(main_mod.get_corpus_info)

    def boom() -> bool:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main_mod.db, "available", boom)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_metrics_endpoint_serves_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "samjho_ask_total" in response.text
    assert "samjho_corpus_chunks" in response.text


# --------------------------------------------------------------------------------------
# startup model warm-up (the first /ask must not pay the load cost)
# --------------------------------------------------------------------------------------


def test_warmup_skips_an_empty_corpus(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main_mod.db, "count_chunks", lambda *a, **k: 0)
    monkeypatch.setattr(main_mod.embed_mod, "prefetch", lambda: calls.append("prefetch"))
    main_mod._warm_models_in_background()
    assert calls == [], "an empty corpus has nothing to search, so no model should be loaded"


def test_warmup_runs_when_the_corpus_has_chunks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(main_mod.db, "count_chunks", lambda *a, **k: 324)
    monkeypatch.setattr(main_mod.embed_mod, "prefetch", lambda: calls.append("prefetch"))
    main_mod._warm_models_in_background()
    for _ in range(100):
        if calls:
            break
        time.sleep(0.02)
    assert calls == ["prefetch"]


def test_warmup_failure_does_not_break_startup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom() -> dict[str, str]:
        raise RuntimeError("model cache is missing")

    monkeypatch.setattr(main_mod.db, "count_chunks", lambda *a, **k: 5)
    monkeypatch.setattr(main_mod.embed_mod, "prefetch", boom)
    main_mod._warm_models_in_background()  # must not raise: /ask pays the cost instead
    assert client.get("/health").status_code == 200


# --------------------------------------------------------------------------------------
# /subjects and /chapters
# --------------------------------------------------------------------------------------


def test_subjects_returns_the_syllabus_without_book_text(client: TestClient) -> None:
    response = client.get("/subjects")
    assert response.status_code == 200
    body = response.json()
    assert body["board"] == "CBSE"
    assert body["class"] == 10
    subjects = {s["id"]: s for s in body["subjects"]}
    assert "science" in subjects and "maths" in subjects
    science = subjects["science"]
    chapter_one = next(c for c in science["chapters"] if c["no"] == 1)
    assert chapter_one["title"]
    assert chapter_one["sections"], "a chapter must list its sections"
    assert chapter_one["ingested"] is False
    assert chapter_one["chunk_count"] == 0
    assert body["corpus_chunks"] == {"science": 0, "maths": 0}
    assert '"text"' not in response.text, "the syllabus endpoint must never serve book text"
    assert body["corpus_available"] is True


def test_subjects_marks_ingested_chapters(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_corpus_info({"available": True, "subjects": {"science": 5, "maths": 0}, "chunks": 5})
    monkeypatch.setattr(main_mod.db, "chapter_counts", lambda subject: {1: 5} if subject == "science" else {})
    monkeypatch.setattr(
        main_mod.db,
        "section_counts",
        lambda subject: {(1, "1.1"): 2, (1, "1.2"): 3} if subject == "science" else {},
    )
    body = client.get("/subjects").json()
    science = next(s for s in body["subjects"] if s["id"] == "science")
    chapter_one = next(c for c in science["chapters"] if c["no"] == 1)
    assert chapter_one["ingested"] is True
    assert chapter_one["chunk_count"] == 5
    sections = {s["no"]: s for s in chapter_one["sections"]}
    assert sections["1.1"]["chunk_count"] == 2 and sections["1.1"]["ingested"] is True
    assert sections["1.2"]["chunk_count"] == 3 and sections["1.2"]["ingested"] is True


def test_chapter_endpoint_flags_a_not_ingested_chapter(client: TestClient) -> None:
    response = client.get("/chapters/science/1")
    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "science"
    assert body["chapter_no"] == 1
    assert body["ingested"] is False
    assert body["chunk_count"] == 0
    assert body["sections"], "sections come from the syllabus even when nothing is ingested"
    assert body["note"], "an un-ingested chapter must say so"
    assert '"text"' not in response.text


def test_chapter_endpoint_reports_ingested_sections(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_corpus_info({"available": True, "subjects": {"science": 3}, "chunks": 3})
    monkeypatch.setattr(main_mod.db, "chapter_counts", lambda subject: {1: 3})
    monkeypatch.setattr(main_mod.db, "section_counts", lambda subject: {(1, "1.2"): 3})
    body = client.get("/chapters/science/1").json()
    assert body["ingested"] is True
    assert body["chunk_count"] == 3
    assert body["note"] is None
    sections = {s["no"]: s for s in body["sections"]}
    assert sections["1.2"]["ingested"] is True
    assert sections["1.1"]["ingested"] is False


def test_chapter_endpoint_404s_for_unknown_chapter(client: TestClient) -> None:
    response = client.get("/chapters/science/99")
    assert response.status_code == 404
    assert "not in the syllabus" in response.json()["detail"]


def test_chapter_endpoint_404s_for_unknown_subject(client: TestClient) -> None:
    response = client.get("/chapters/astrophysics/1")
    assert response.status_code == 404
    assert "astrophysics" in response.json()["detail"]


# --------------------------------------------------------------------------------------
# /ask
# --------------------------------------------------------------------------------------


def test_ask_refusal_matches_the_contract(client: TestClient) -> None:
    stub_answer(lambda subject, question, chapter_no, top_k: answer_mod.build_from_chunks(
        subject, question, outcome([])
    ))
    response = client.post(
        "/ask", json={"subject": "science", "chapter_no": 1, "question": SILVER_QUESTION, "top_k": 6}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= CONTRACT_ASK_KEYS
    assert body["refused"] is True
    assert body["refusal_reason"] in answer_mod.REFUSAL_REASONS
    assert body["citations"] == []
    assert body["provider"] == "retrieval-only"
    assert body["retrieval"]["mode"] == "hybrid"
    assert set(body["retrieval"]) >= CONTRACT_RETRIEVAL_KEYS
    assert isinstance(body["retrieval"]["took_ms"], int)
    assert body["closest"] == [], "an empty corpus has nothing to point at"


def test_ask_refusal_points_at_the_closest_sections(client: TestClient) -> None:
    """A refusal on a non-empty corpus must be useful: nearest passages, with scores, no citations."""
    weak = CHUNK.model_copy(update={"score": 0.02})
    stub_answer(lambda subject, question, chapter_no, top_k: answer_mod.build_from_chunks(
        subject, question, outcome([weak])
    ))
    body = client.post("/ask", json={"subject": "science", "question": SILVER_QUESTION}).json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert len(body["closest"]) == 1
    closest = body["closest"][0]
    assert closest["section_no"] == "1.2"
    assert closest["page_start"] == 8
    assert closest["score"] == 0.02
    assert closest["chunk_id"] == CHUNK.id
    assert "Closest passages in your material" in body["refusal_detail"]


def test_ask_answer_matches_the_contract(client: TestClient) -> None:
    stub_answer(lambda subject, question, chapter_no, top_k: answer_mod.build_from_chunks(
        subject, question, outcome([CHUNK])
    ))
    response = client.post("/ask", json={"subject": "science", "question": SILVER_QUESTION})
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["refusal_reason"] is None
    assert body["answer"]
    assert body["citations"], "an answered question carries citations"
    citation = body["citations"][0]
    assert set(citation) >= {
        "chapter_no",
        "section_no",
        "page_start",
        "page_end",
        "chapter_title",
        "section_title",
        "score",
    }
    assert citation["chapter_no"] == 1
    assert citation["section_no"] == "1.2"
    assert citation["page_start"] == 8
    assert 0.0 <= citation["score"] <= 1.0
    assert "[Ch 1 §1.2 p.8]" in body["answer"]


def test_ask_rejects_an_unknown_subject(client: TestClient) -> None:
    response = client.post("/ask", json={"subject": "astrophysics", "question": SILVER_QUESTION})
    assert response.status_code == 400
    assert "astrophysics" in response.json()["detail"]


def test_ask_returns_503_when_the_corpus_cannot_be_read(client: TestClient) -> None:
    def broken(subject: str, question: str, chapter_no: int | None, top_k: int | None):
        raise RetrievalUnavailable("corpus database is not reachable: connection refused")

    stub_answer(broken)
    response = client.post("/ask", json={"subject": "science", "question": SILVER_QUESTION})
    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"]


def test_ask_rejects_an_empty_question(client: TestClient) -> None:
    assert client.post("/ask", json={"subject": "science", "question": ""}).status_code == 422
    assert client.post("/ask", json={"subject": "science"}).status_code == 422
    assert client.post("/ask", json={"subject": "science", "question": "q", "top_k": 99}).status_code == 422


# --------------------------------------------------------------------------------------
# /quiz
# --------------------------------------------------------------------------------------


def test_quiz_questions_carry_a_source_and_a_marking_key(client: TestClient) -> None:
    def stub(subject: str, chapter_no: int, count: int):
        return quiz_mod.QuizResult(
            subject=subject,
            chapter_no=chapter_no,
            provider="retrieval-only",
            questions=quiz_mod.retrieval_only_quiz([CHUNK], count),
            took_ms=3,
        )

    stub_quiz(stub)
    response = client.post("/quiz", json={"subject": "science", "chapter_no": 1, "count": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "retrieval-only"
    assert body["questions"], "the stub chunk is long enough for one question"
    for question in body["questions"]:
        assert set(question) >= {"id", "question", "type", "marks", "source", "marking_key"}
        assert question["source"]["section_no"] == "1.2"
        assert question["source"]["chunk_id"] == CHUNK.id
        assert question["source"]["page_start"] == 8
        assert question["marking_key"]["expected_points"]
        assert question["marking_key"]["guidance"]
        assert question["marks"] >= 1


def test_quiz_503s_when_the_corpus_cannot_be_read(client: TestClient) -> None:
    def broken(subject: str, chapter_no: int, count: int):
        raise RetrievalUnavailable("corpus database is not reachable")

    stub_quiz(broken)
    response = client.post("/quiz", json={"subject": "science", "chapter_no": 1, "count": 3})
    assert response.status_code == 503


def test_quiz_validates_its_request(client: TestClient) -> None:
    assert client.post("/quiz", json={"subject": "science", "chapter_no": 0}).status_code == 422
    assert client.post("/quiz", json={"subject": "science", "chapter_no": 1, "count": 0}).status_code == 422


# --------------------------------------------------------------------------------------
# /progress
# --------------------------------------------------------------------------------------


def test_progress_round_trip_with_an_in_memory_store(client: TestClient) -> None:
    store = InMemoryStore()
    stub_store(store)
    empty = client.get("/progress/student-1")
    assert empty.status_code == 200
    assert empty.json()["chapters"] == []
    assert empty.json()["note"]

    posted = client.post(
        "/progress/student-1",
        json={
            "subject": "science",
            "chapter_no": 1,
            "attempts": [
                {"question": "why is silver chloride grey?", "correct": True, "section_no": "1.2"},
                {"question": "what does the number mean?", "correct": False, "section_no": "1.1"},
            ],
        },
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["available"] is True
    assert body["chapters"][0]["attempts"] == 2
    assert body["chapters"][0]["correct"] == 1
    assert body["chapters"][0]["accuracy"] == 0.5
    assert body["totals"] == {"attempts": 2, "correct": 1, "chapters": 1}

    history = client.get("/progress/student-1", params={"subject": "science"}).json()
    assert history["chapters"][0]["attempts"] == 2
    assert client.get("/progress/student-2").json()["chapters"] == []


def test_progress_503s_without_a_store(client: TestClient) -> None:
    stub_store(InMemoryStore(available=False))
    assert client.get("/progress/student-1").status_code == 503
    assert (
        client.post(
            "/progress/student-1",
            json={"subject": "science", "chapter_no": 1, "attempts": [{"question": "q", "correct": True}]},
        ).status_code
        == 503
    )


# --------------------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------------------


def test_openapi_covers_every_contract_path(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    for path in (
        "/health",
        "/metrics",
        "/subjects",
        "/chapters/{subject}/{chapter_no}",
        "/ask",
        "/quiz",
        "/progress/{student_id}",
    ):
        assert path in paths, f"{path} missing from the OpenAPI document"
    assert "post" in paths["/ask"] and "get" in paths["/health"]
    assert paths["/ask"]["post"]["summary"]


def _constraints(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic emits `anyOf: [{...}, {"type": "null"}]` for optional fields; flatten it."""
    if "anyOf" in schema:
        return next((s for s in schema["anyOf"] if s.get("type") != "null"), {})
    return schema


def test_openapi_ask_schema_has_the_contract_fields(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    answer_schema = schemas["AnswerResult"]
    assert set(answer_schema["properties"]) >= CONTRACT_ASK_KEYS
    assert set(answer_schema["required"]) >= {"answer", "refused", "retrieval", "provider"}
    assert set(schemas["RetrievalInfo"]["required"]) >= CONTRACT_RETRIEVAL_KEYS
    assert set(schemas["Citation"]["required"]) >= {
        "chapter_no",
        "section_no",
        "page_start",
        "page_end",
        "chapter_title",
        "section_title",
        "score",
    }
    refusal = answer_schema["properties"]["refusal_reason"]
    assert "not_in_corpus" in refusal["description"]
    assert "closest" in answer_schema["properties"]
    assert set(schemas["ClosestSection"]["required"]) >= {
        "chapter_no",
        "section_no",
        "section_title",
        "page_start",
        "page_end",
        "score",
        "chunk_id",
    }
    assert set(schemas["QuizQuestion"]["required"]) >= {"id", "question", "marks", "source", "marking_key"}
    assert set(schemas["QuizSource"]["required"]) >= {"chapter_no", "section_no", "chunk_id"}


def test_openapi_request_schema_documents_limits(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    ask = spec["components"]["schemas"]["AskRequest"]["properties"]
    assert ask["subject"]["minLength"] == 1
    assert _constraints(ask["chapter_no"])["minimum"] == 1
    assert _constraints(ask["top_k"])["maximum"] == 20
    quiz = spec["components"]["schemas"]["QuizRequest"]["properties"]
    assert quiz["count"]["maximum"] == 20
    assert quiz["count"]["default"] == 5
