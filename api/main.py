"""The samjho API (CONTRACTS section 4).

Endpoints: `/health`, `/metrics`, `/subjects`, `/chapters/{subject}/{no}`, `/ask`, `/quiz`,
`/progress/{student_id}`.

Two properties the rest of the project depends on:

* **It starts with nothing configured.** No LLM key, no ingested corpus, no model download: the
  process serves `/health`, `/subjects` and `/chapters/...`, and `/ask` answers with a refusal
  whose reason is `no_corpus`. The web app renders its "corpus not ingested yet" state from that.
* **It never dresses a failure up as an answer.** A database outage is a 503, an unknown subject is
  a 400, a chapter the corpus does not cover is a 200 with an explicit refusal (the question was
  well-formed; the material just does not cover it).

Every endpoint's response shape is a pydantic model, so the generated OpenAPI is the contract
rather than an approximation of it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from . import db, retriever, syllabus
from . import embed as embed_mod
from . import quiz as quiz_mod
from .answer import AnswerResult, answer_question
from .config import get_settings
from .progress import DEFAULT_STORE, ProgressStore
from .quiz import QuizResult
from .retriever import RetrievalUnavailable

log = logging.getLogger("samjho.api")

VERSION = "0.1.0"

# --------------------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------------------

ASK_TOTAL = Counter("samjho_ask_total", "Questions answered", ["subject", "outcome"])
REFUSALS_TOTAL = Counter(
    "samjho_refusals_total", "Refusals, by reason", ["reason"]
)
ASK_SECONDS = Histogram("samjho_ask_seconds", "End-to-end /ask latency", ["outcome"])
RETRIEVAL_SECONDS = Histogram("samjho_retrieval_seconds", "Hybrid retrieval latency", ["mode"])
QUIZ_TOTAL = Counter("samjho_quiz_total", "Quizzes generated", ["subject", "provider"])
CORPUS_CHUNKS = Gauge("samjho_corpus_chunks", "Chunks in the ingested corpus")
HTTP_REQUESTS = Counter(
    "samjho_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
LLM_FALLBACKS = Counter(
    "samjho_provider_fallbacks_total", "Provider calls that degraded to retrieval-only", ["reason"]
)


# --------------------------------------------------------------------------------------
# response models
# --------------------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' when the database is reachable, 'degraded' otherwise.")
    corpus_chunks: int
    provider: str = Field(description="Answer path in use: a provider name, or 'retrieval-only'.")
    db: str = Field(description="'ok' | 'unavailable'")
    syllabus: str = Field(description="'ok' | 'missing'")
    embedding_model: str
    reranker_model: str
    embedding_model_loaded: bool
    reranker_loaded: bool
    version: str


class SectionOut(BaseModel):
    no: str
    title: str
    page: int | None = None
    ingested: bool = False
    chunk_count: int = 0


class ChapterOut(BaseModel):
    no: int
    title: str
    pages: int | None = None
    status: str | None = None
    ingested: bool = False
    chunk_count: int = 0
    sections: list[SectionOut] = Field(default_factory=list)


class SubjectOut(BaseModel):
    id: str
    name: str
    book_code: str | None = None
    chapters: list[ChapterOut] = Field(default_factory=list)


class SubjectsResponse(BaseModel):
    """Syllabus structure only — no textbook text, safe to serve publicly (PLAN section 1)."""

    board: str | None = None
    class_level: int | None = Field(
        default=None,
        serialization_alias="class",
        description="Class number, as the syllabus file names it (JSON key: 'class').",
    )
    subjects: list[SubjectOut]
    corpus_chunks: dict[str, int] = Field(
        default_factory=dict, description="Ingested chunk count per subject id."
    )
    corpus_available: bool = True
    note: str | None = None


class ChapterResponse(BaseModel):
    subject: str
    subject_name: str
    chapter_no: int
    title: str
    pages: int | None = None
    status: str | None = None
    ingested: bool = Field(description="True when the corpus holds at least one chunk of this chapter.")
    chunk_count: int
    sections: list[SectionOut]
    corpus_available: bool = True
    note: str | None = None


class AskRequest(BaseModel):
    subject: str = Field(min_length=1, examples=["science"])
    question: str = Field(min_length=1, examples=["why does silver chloride turn grey in sunlight"])
    chapter_no: int | None = Field(default=None, ge=1, description="Restrict retrieval to one chapter.")
    top_k: int | None = Field(default=None, ge=1, le=20, description="Chunks to retrieve (default 6).")


class QuizRequest(BaseModel):
    subject: str = Field(min_length=1)
    chapter_no: int = Field(ge=1)
    count: int = Field(default=5, ge=1, le=20)


class ProgressAttempt(BaseModel):
    question: str
    correct: bool
    section_no: str | None = None
    expected_key: str | None = None
    answer: str | None = None


class ProgressSubmit(BaseModel):
    subject: str
    chapter_no: int = Field(ge=1)
    attempts: list[ProgressAttempt] = Field(min_length=1)


class ChapterProgress(BaseModel):
    subject: str
    chapter_no: int
    attempts: int
    correct: int
    accuracy: float
    last_attempt: str | None = None


class ProgressResponse(BaseModel):
    student_id: str
    available: bool
    chapters: list[ChapterProgress] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
    note: str | None = None


# --------------------------------------------------------------------------------------
# dependencies — the seams the API tests stub
# --------------------------------------------------------------------------------------


def get_settings_dep():
    return get_settings()


def get_search_fn() -> Callable[..., list[retriever.RetrievedChunk]]:
    return retriever.search


def get_answer_fn() -> Callable[..., AnswerResult]:
    return answer_question


def get_quiz_fn() -> Callable[..., QuizResult]:
    return quiz_mod.generate_quiz


def get_progress_store() -> ProgressStore:
    return DEFAULT_STORE


def get_corpus_info() -> dict[str, Any]:
    """Chunk counts per subject + database liveness. Never raises: /health must always answer."""
    info: dict[str, Any] = {"available": False, "subjects": {}, "chunks": 0}
    try:
        if not db.available():
            return info
        info["available"] = True
        for subject in db.subjects_in_corpus():
            count = db.count_chunks(subject)
            info["subjects"][subject] = count
            info["chunks"] += count
    except Exception as exc:  # pragma: no cover - defensive, /health must not 500
        log.warning("corpus info unavailable: %s", exc)
    return info


SearchFn = Annotated[Callable[..., list[retriever.RetrievedChunk]], Depends(get_search_fn)]
AnswerFn = Annotated[Callable[..., AnswerResult], Depends(get_answer_fn)]
QuizFn = Annotated[Callable[..., QuizResult], Depends(get_quiz_fn)]
Store = Annotated[ProgressStore, Depends(get_progress_store)]
CorpusInfo = Annotated[dict[str, Any], Depends(get_corpus_info)]


# --------------------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Apply migrations when a database is reachable. A missing database is not fatal: the app
    still serves /health and /subjects, which is exactly the pre-ingest state."""
    try:
        if db.available():
            applied = db.init_schema()
            log.info("samjho schema ready (migrations applied now: %s)", applied or "none")
            _warm_models_in_background()
        else:
            log.warning("no database reachable at startup — serving the empty-corpus state")
    except Exception as exc:  # pragma: no cover - startup must not crash the container
        log.warning("schema init skipped: %s", exc)
    yield


def _warm_models_in_background() -> None:
    """Load the embedding and reranking models off the request path.

    Measured: the first `/ask` in a fresh process spent 53.6 s inside the request, almost all of it
    loading the models (the retrieval itself was ~500 ms warm). Warming only when the corpus is
    non-empty keeps the empty-corpus startup honest — there is nothing to search, so there is no
    reason to touch a model. A failure here is logged and ignored: `/ask` will simply pay the cost
    once, and `/health` reports whether the models are loaded.
    """

    def warm() -> None:
        try:
            loaded = embed_mod.prefetch()
            log.info("models warm: %s", loaded)
        except Exception as exc:  # pragma: no cover - depends on the machine's cache
            log.warning("model warm-up failed, the first /ask will load them: %s", exc)

    try:
        if db.count_chunks() == 0:
            log.info("corpus is empty — skipping model warm-up (nothing to search yet)")
            return
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("could not count chunks for warm-up: %s", exc)
        return
    threading.Thread(target=warm, name="samjho-warmup", daemon=True).start()


app = FastAPI(
    title="samjho API",
    version=VERSION,
    lifespan=lifespan,
    description=(
        "Retrieval and answering for samjho, a CBSE Class 10 study companion. Answers are cited "
        "to the student's own copy of their textbook (chapter, section, page); a question the "
        "ingested corpus does not cover is refused with a reason instead of answered."
    ),
    openapi_tags=[
        {"name": "meta", "description": "Health and metrics."},
        {"name": "syllabus", "description": "Syllabus structure — no textbook text."},
        {"name": "ask", "description": "Cited answers, with refusal as a first-class result."},
        {"name": "quiz", "description": "Quizzes generated from one chapter's ingested chunks."},
        {"name": "progress", "description": "Per-chapter quiz history."},
    ],
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        HTTP_REQUESTS.labels(request.method, request.url.path, "500").inc()
        raise
    HTTP_REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
    response.headers["x-samjho-took-ms"] = str(int((time.perf_counter() - started) * 1000))
    return response


@app.get("/health", response_model=HealthResponse, tags=["meta"], summary="Liveness + corpus state")
def health(corpus: CorpusInfo) -> HealthResponse:
    settings = get_settings()
    CORPUS_CHUNKS.set(corpus["chunks"])
    return HealthResponse(
        status="ok" if corpus["available"] else "degraded",
        corpus_chunks=int(corpus["chunks"]),
        provider=settings.provider_name,
        db="ok" if corpus["available"] else "unavailable",
        syllabus="ok" if syllabus.syllabus_available() else "missing",
        embedding_model=settings.embedding_model,
        reranker_model=settings.reranker_model if settings.reranker_enabled else "",
        embedding_model_loaded=embed_mod.model_loaded(),
        reranker_loaded=embed_mod.reranker_loaded(),
        version=VERSION,
    )


@app.get("/metrics", tags=["meta"], summary="Prometheus metrics", response_class=Response)
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/subjects", response_model=SubjectsResponse, tags=["syllabus"], summary="Syllabus structure")
def get_subjects(corpus: CorpusInfo) -> SubjectsResponse:
    try:
        raw = syllabus.load_syllabus()
        subjects = syllabus.subjects()
        board = raw.get("board")
        class_no = raw.get("class")
        note = None
    except syllabus.SyllabusError as exc:
        subjects, board, class_no = [], None, None
        note = f"Syllabus not available: {exc}"

    counts: dict[str, int] = {}
    per_chapter: dict[str, dict[int, int]] = {}
    per_section: dict[str, dict[tuple[int, str], int]] = {}
    for subject in subjects:
        sid = str(subject["id"])
        if corpus["available"]:
            try:
                per_chapter[sid] = db.chapter_counts(sid)
                per_section[sid] = db.section_counts(sid)
            except Exception as exc:  # pragma: no cover - defensive
                log.warning("counts for %s unavailable: %s", sid, exc)
        counts[sid] = int(corpus["subjects"].get(sid, 0))

    out = [
        SubjectOut(
            id=str(s["id"]),
            name=str(s["name"]),
            book_code=s.get("book_code"),
            chapters=[
                _chapter_out(ch, per_chapter.get(str(s["id"]), {}), per_section.get(str(s["id"]), {}))
                for ch in s["chapters"]
            ],
        )
        for s in subjects
    ]
    return SubjectsResponse(
        board=board,
        class_level=class_no,
        subjects=out,
        corpus_chunks=counts,
        corpus_available=bool(corpus["available"]),
        note=note,
    )


def _chapter_out(
    chapter: dict[str, Any],
    chapter_counts: dict[int, int],
    section_counts: dict[tuple[int, str], int],
) -> ChapterOut:
    """`ingested` is a corpus fact, not a syllabus fact: the syllabus lists chapters that may not
    have been ingested yet, and the web app has to tell those two states apart."""
    chapter_no = int(chapter["no"])
    chunk_count = int(chapter_counts.get(chapter_no, 0))
    return ChapterOut(
        no=chapter_no,
        title=str(chapter.get("title", "")),
        pages=chapter.get("pages"),
        status=chapter.get("status"),
        ingested=chunk_count > 0,
        chunk_count=chunk_count,
        sections=[
            SectionOut(
                no=str(s.get("no")),
                title=str(s.get("title", "")),
                page=s.get("page"),
                ingested=int(section_counts.get((chapter_no, str(s.get("no"))), 0)) > 0,
                chunk_count=int(section_counts.get((chapter_no, str(s.get("no"))), 0)),
            )
            for s in chapter.get("sections", [])
        ],
    )


@app.get(
    "/chapters/{subject}/{chapter_no}",
    response_model=ChapterResponse,
    tags=["syllabus"],
    summary="One chapter: sections and whether it is ingested",
)
def get_chapter(subject: str, chapter_no: int, corpus: CorpusInfo) -> ChapterResponse:
    chapter = syllabus.get_chapter(subject, chapter_no)
    subject_meta = syllabus.get_subject(subject)
    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"chapter {chapter_no} of subject '{subject}' is not in the syllabus"
                if subject_meta
                else f"subject '{subject}' is not in the syllabus"
            ),
        )

    counts: dict[int, int] = {}
    section_counts: dict[str, int] = {}
    if corpus["available"]:
        try:
            counts = db.chapter_counts(subject)
            section_counts = retriever.chapter_overview(subject, chapter_no)["sections"]
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("chapter counts unavailable: %s", exc)

    chunk_count = int(counts.get(chapter_no, 0))
    sections = [
        SectionOut(
            no=str(s.get("no")),
            title=str(s.get("title", "")),
            page=s.get("page"),
            ingested=int(section_counts.get(str(s.get("no")), 0)) > 0,
            chunk_count=int(section_counts.get(str(s.get("no")), 0)),
        )
        for s in chapter.get("sections", [])
    ]
    return ChapterResponse(
        subject=subject,
        subject_name=str((subject_meta or {}).get("name", subject)),
        chapter_no=chapter_no,
        title=str(chapter.get("title", "")),
        pages=chapter.get("pages"),
        status=chapter.get("status"),
        ingested=chunk_count > 0,
        chunk_count=chunk_count,
        sections=sections,
        corpus_available=bool(corpus["available"]),
        note=None if chunk_count else "This chapter is not in the ingested corpus yet.",
    )


@app.post("/ask", response_model=AnswerResult, tags=["ask"], summary="Ask a question, cited or refused")
def ask(request: AskRequest, answer_fn: AnswerFn) -> AnswerResult:
    if not _subject_known(request.subject):
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown subject '{request.subject}': it is neither in the syllabus nor in the "
                "ingested corpus"
            ),
        )
    started = time.perf_counter()
    try:
        result = answer_fn(request.subject, request.question, request.chapter_no, request.top_k)
    except RetrievalUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    outcome = "refused" if result.refused else "answered"
    ASK_TOTAL.labels(request.subject, outcome).inc()
    ASK_SECONDS.labels(outcome).observe(time.perf_counter() - started)
    RETRIEVAL_SECONDS.labels(result.retrieval.mode).observe(result.retrieval.took_ms / 1000)
    if result.refused and result.refusal_reason:
        REFUSALS_TOTAL.labels(result.refusal_reason).inc()
    if result.degraded:
        LLM_FALLBACKS.labels(result.provider_error or "unknown").inc()
    return result


def _subject_known(subject: str) -> bool:
    if syllabus.get_subject(subject) is not None:
        return True
    try:
        return subject in db.subjects_in_corpus()
    except Exception:
        return True  # database unreachable: let /ask report the outage, not a bad-subject 400


@app.post("/quiz", response_model=QuizResult, tags=["quiz"], summary="Quiz from one chapter's chunks")
def make_quiz(request: QuizRequest, quiz_fn: QuizFn) -> QuizResult:
    try:
        result = quiz_fn(request.subject, request.chapter_no, request.count)
    except RetrievalUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    QUIZ_TOTAL.labels(request.subject, result.provider).inc()
    return result


@app.get(
    "/progress/{student_id}",
    response_model=ProgressResponse,
    tags=["progress"],
    summary="Per-chapter quiz history",
)
def get_progress(
    student_id: str,
    store: Store,
    subject: Annotated[str | None, Query(description="Filter to one subject")] = None,
) -> ProgressResponse:
    if not store.available():
        raise HTTPException(
            status_code=503,
            detail="progress store unavailable: no database connection (see /health)",
        )
    chapters = [ChapterProgress(**row) for row in store.history(student_id, subject)]
    return ProgressResponse(
        student_id=student_id,
        available=True,
        chapters=chapters,
        totals={
            "attempts": sum(c.attempts for c in chapters),
            "correct": sum(c.correct for c in chapters),
            "chapters": len(chapters),
        },
        note=None if chapters else "No quiz attempts recorded for this student yet.",
    )


@app.post(
    "/progress/{student_id}",
    response_model=ProgressResponse,
    tags=["progress"],
    summary="Record quiz answers",
)
def post_progress(student_id: str, submission: ProgressSubmit, store: Store) -> ProgressResponse:
    """Not in CONTRACTS section 4 (which only freezes the GET) — the write side the web app needs
    so the GET has something to return. Additive: the frozen GET is unchanged."""
    if not store.available():
        raise HTTPException(
            status_code=503,
            detail="progress store unavailable: no database connection (see /health)",
        )
    store.record(
        [
            {
                "student_id": student_id,
                "subject": submission.subject,
                "chapter_no": submission.chapter_no,
                "section_no": attempt.section_no,
                "question": attempt.question,
                "expected_key": attempt.expected_key,
                "answer": attempt.answer,
                "correct": attempt.correct,
            }
            for attempt in submission.attempts
        ]
    )
    chapters = [ChapterProgress(**row) for row in store.history(student_id, submission.subject)]
    return ProgressResponse(
        student_id=student_id,
        available=True,
        chapters=chapters,
        totals={
            "attempts": sum(c.attempts for c in chapters),
            "correct": sum(c.correct for c in chapters),
            "chapters": len(chapters),
        },
        note=f"Recorded {len(submission.attempts)} attempt(s).",
    )
