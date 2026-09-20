"""Shared fixtures for the retrieval / API test suite.

Marker conventions (pyproject `markers`):

* `unit` — no database, no model download. Fast and deterministic.
* `integration` — needs Postgres + pgvector (and downloads the local models on first run).

The integration tests **fail loudly** when the database is missing rather than skipping: CI runs
them against the compose service, and a silent skip would let a broken retrieval path look green.
The failure message carries the exact command to start a database.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SYNTHETIC_CHUNKS = FIXTURES_DIR / "synthetic_chunks.jsonl"

# Every fixture subject starts with this prefix, so cleanup can never touch a real corpus.
FIXTURE_SUBJECT_PREFIX = "fixture-"

DEV_DATABASE_HINT = (
    "Postgres with pgvector is not reachable at DATABASE_URL.\n"
    "Start one with:\n"
    "  docker run -d --name samjho-pg -e POSTGRES_PASSWORD=samjho -e POSTGRES_USER=samjho "
    "-e POSTGRES_DB=samjho -p 5439:5432 pgvector/pgvector:pg16\n"
    "  DATABASE_URL=postgresql://samjho:samjho@localhost:5439/samjho pytest -m integration"
)


@pytest.fixture(autouse=True)
def deterministic_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No LLM provider, no tuning overrides from the developer's shell unless a test asks for them.

    Env vars win over `.env` in pydantic-settings, so pinning these to empty strings keeps the
    retrieval-only path even on a machine whose `.env` has a key configured.
    """
    from api.config import reset_settings_cache

    for name in ("ANSWER_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.setenv(name, "")
    # The calibrated refusal thresholds are pinned to their code defaults: env vars beat `.env` in
    # pydantic-settings, so a developer's `.env` (which may predate the calibration) cannot change
    # what these tests assert. A test that wants different bands sets them itself.
    monkeypatch.setenv("REFUSAL_MIN_SCORE", "0.05")
    monkeypatch.setenv("REFUSAL_CONFIDENT_SCORE", "0.95")
    monkeypatch.setenv("REFUSAL_MIN_OVERLAP", "0.40")
    # Numeric/bool settings: unset them so `.env` (or the default) applies. Setting a float
    # setting to "" would be a validation error, not "no value".
    for name in (
        "FTS_WEIGHT",
        "RETRIEVAL_CANDIDATES",
        "RETRIEVAL_TOP_K",
        "RERANK_CANDIDATES",
        "QUOTE_MIN_RATIO",
        "TORCH_THREADS",
        "RERANKER_ENABLED",
        "EMBEDDING_MODEL",
        "RERANKER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture(scope="session")
def fixture_chunks() -> list[dict[str, Any]]:
    records = [
        json.loads(line)
        for line in SYNTHETIC_CHUNKS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 6, "the fixture is documented as six chunks; update the README if not"
    return records


def require_database() -> None:
    from api import db

    if not db.available():
        pytest.fail(DEV_DATABASE_HINT, pytrace=False)


@pytest.fixture(scope="session")
def indexed_corpus(fixture_chunks: list[dict[str, Any]]):
    """Load the synthetic fixture into Postgres once per session and remove it afterwards.

    Only subjects starting with `fixture-` are touched, so this is safe to run against a
    development database that also holds a student's real ingested corpus.
    """
    from api import db

    require_database()
    db.init_schema()
    db.delete_subjects(FIXTURE_SUBJECT_PREFIX)
    counts = db.load_chunks([SYNTHETIC_CHUNKS])
    loaded = db.count_chunks("fixture-science") + db.count_chunks("fixture-maths")
    assert loaded == len(fixture_chunks), f"expected {len(fixture_chunks)} fixture chunks, got {loaded}"
    try:
        yield {"counts": counts, "chunks": loaded}
    finally:
        db.delete_subjects(FIXTURE_SUBJECT_PREFIX)
        db.close_pool()


@pytest.fixture(scope="session")
def syllabus_path() -> Path:
    from api.config import get_settings

    return Path(get_settings().syllabus_path)


def env_database_url() -> str:
    return os.environ.get("DATABASE_URL", "")
