"""Postgres + pgvector storage: schema, migrations, the two search arms, and quiz history.

Schema (CONTRACTS section 2 is the chunk shape this mirrors):

    chunks(id, subject, chapter_no, chapter_title, section_no, section_title,
           page_start, page_end, math_heavy, text, embedding vector(384),
           tsv tsvector GENERATED ALWAYS AS to_tsvector('english', text) STORED)

`tsv` is a generated column rather than a trigger: there is exactly one writer (the loader
below), and a generated column cannot drift out of sync with `text`.

Migrations are numbered and applied once, recorded in `schema_migrations`; running
`python -m api.db init` twice is a no-op. This is deliberately small — one process owns this
database in v1 — but it is a real migration table, not `CREATE TABLE IF NOT EXISTS` theatre:
the embedding dimension of the existing column is checked against config and a mismatch is a
loud error instead of silent vector corruption.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from psycopg import Cursor
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

# --------------------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------------------

MIGRATION_1_CHUNKS = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id            text PRIMARY KEY,
    subject       text NOT NULL,
    chapter_no    integer NOT NULL,
    chapter_title text NOT NULL,
    section_no    text NOT NULL,
    section_title text NOT NULL,
    page_start    integer NOT NULL,
    page_end      integer NOT NULL,
    math_heavy    boolean NOT NULL DEFAULT false,
    text          text NOT NULL,
    embedding     vector({dim}),
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    ingested_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_gin
    ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_subject_chapter
    ON chunks (subject, chapter_no);
"""

MIGRATION_2_PROGRESS = """
CREATE TABLE IF NOT EXISTS quiz_attempts (
    id           bigserial PRIMARY KEY,
    student_id   text NOT NULL,
    subject      text NOT NULL,
    chapter_no   integer NOT NULL,
    section_no   text,
    question     text NOT NULL,
    expected_key text,
    answer       text,
    correct      boolean,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS quiz_attempts_student
    ON quiz_attempts (student_id, subject, chapter_no);
"""

CHUNK_FIELDS = (
    "id",
    "subject",
    "chapter_no",
    "chapter_title",
    "section_no",
    "section_title",
    "page_start",
    "page_end",
    "math_heavy",
    "text",
)


def migrations() -> list[tuple[int, str]]:
    settings = get_settings()
    return [
        (1, MIGRATION_1_CHUNKS.format(dim=int(settings.embedding_dim))),
        (2, MIGRATION_2_PROGRESS),
    ]


# --------------------------------------------------------------------------------------
# connection pool
# --------------------------------------------------------------------------------------

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=4,
            open=False,
            timeout=settings.db_connect_timeout_s,
            kwargs={
                "row_factory": dict_row,
                "connect_timeout": settings.db_connect_timeout_s,
                "application_name": "samjho-api",
            },
        )
        _pool.open(wait=False)
    return _pool


def close_pool() -> None:
    """Tests close the pool between configurations; the app never calls this."""
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        finally:
            _pool = None


@contextmanager
def cursor() -> Iterator[Cursor[DictRow]]:
    """A pooled cursor that yields dict rows, so `row["column"]` is typed and correct.

    The alternative — annotating rows as tuples and casting at each call site — would hide a real
    class of bug: a column-order change silently re-indexing every row.
    """
    with get_pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur


def available(timeout: float | None = None) -> bool:
    """Cheap liveness probe that never raises — /health depends on that."""
    settings = get_settings()
    try:
        with get_pool().connection(timeout=timeout or settings.db_connect_timeout_s) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def init_schema() -> list[int]:
    """Apply pending migrations. Returns the versions applied by this call."""
    applied: list[int] = []
    with cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {row["version"] for row in cur.execute("SELECT version FROM schema_migrations")}
        for version, sql in migrations():
            if version in done:
                continue
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied.append(version)
        _assert_embedding_dim(cur)
    return applied


def _assert_embedding_dim(cur: Cursor[DictRow]) -> None:
    """A vector(384) column cannot store a 768-dim model. Fail loudly, not silently."""
    settings = get_settings()
    row = cur.execute(
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
    ).fetchone()
    if row is not None and row["atttypmod"] not in (-1, settings.embedding_dim):
        raise RuntimeError(
            f"chunks.embedding is vector({row['atttypmod']}) but EMBEDDING_DIM="
            f"{settings.embedding_dim}. Re-ingest into a fresh database, or set EMBEDDING_DIM "
            "to match the existing column."
        )


# --------------------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------------------


def vector_literal(vector: Sequence[float]) -> str:
    """pgvector text literal. Passed as text and cast in SQL, so no adapter registration is
    needed on every pooled connection (and a missing extension cannot break the pool)."""
    return "[" + ",".join(f"{float(x):.7g}" for x in vector) + "]"


def upsert_chunks(records: Iterable[dict[str, Any]], embeddings: Sequence[Sequence[float]]) -> int:
    """Insert/replace chunk rows. `records` follow CONTRACTS section 2; embeddings are 384-dim."""
    rows = list(records)
    if len(rows) != len(embeddings):
        raise ValueError(f"{len(rows)} chunks but {len(embeddings)} embeddings")
    if not rows:
        return 0
    settings = get_settings()
    sql = """
        INSERT INTO chunks (id, subject, chapter_no, chapter_title, section_no, section_title,
                            page_start, page_end, math_heavy, text, embedding)
        VALUES (%(id)s, %(subject)s, %(chapter_no)s, %(chapter_title)s, %(section_no)s,
                %(section_title)s, %(page_start)s, %(page_end)s, %(math_heavy)s, %(text)s,
                %(embedding)s::vector)
        ON CONFLICT (id) DO UPDATE SET
            subject = EXCLUDED.subject,
            chapter_no = EXCLUDED.chapter_no,
            chapter_title = EXCLUDED.chapter_title,
            section_no = EXCLUDED.section_no,
            section_title = EXCLUDED.section_title,
            page_start = EXCLUDED.page_start,
            page_end = EXCLUDED.page_end,
            math_heavy = EXCLUDED.math_heavy,
            text = EXCLUDED.text,
            embedding = EXCLUDED.embedding,
            ingested_at = now()
    """
    params = []
    for record, embedding in zip(rows, embeddings, strict=True):
        if len(embedding) != settings.embedding_dim:
            raise ValueError(
                f"chunk {record.get('id')!r}: embedding has {len(embedding)} dims, "
                f"expected {settings.embedding_dim}"
            )
        params.append({**{k: record[k] for k in CHUNK_FIELDS}, "embedding": vector_literal(embedding)})
    with cursor() as cur:
        cur.executemany(sql, params)
    return len(rows)


def delete_subjects(prefix: str) -> int:
    """Remove every chunk whose subject starts with `prefix`. Used by tests to clean fixtures
    out of a shared development database without touching a real corpus."""
    with cursor() as cur:
        cur.execute("DELETE FROM chunks WHERE subject LIKE %s", (prefix + "%",))
        return cur.rowcount


# --------------------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------------------

_SELECT_COLS = """
    id, subject, chapter_no, chapter_title, section_no, section_title,
    page_start, page_end, math_heavy, text
"""


def count_chunks(subject: str | None = None, chapter_no: int | None = None) -> int:
    sql = "SELECT count(*) AS n FROM chunks WHERE (%(subject)s::text IS NULL OR subject = %(subject)s)"
    params: dict[str, Any] = {"subject": subject}
    if chapter_no is not None:
        sql += " AND chapter_no = %(chapter_no)s"
        params["chapter_no"] = chapter_no
    with cursor() as cur:
        row = cur.execute(sql, params).fetchone()
    return int(row["n"]) if row else 0


def chapter_counts(subject: str) -> dict[int, int]:
    """How many chunks each chapter of a subject has — the `ingested` flag on /chapters."""
    with cursor() as cur:
        rows = cur.execute(
            "SELECT chapter_no, count(*) AS n FROM chunks WHERE subject = %s GROUP BY chapter_no",
            (subject,),
        ).fetchall()
    return {int(r["chapter_no"]): int(r["n"]) for r in rows}


def section_counts(subject: str) -> dict[tuple[int, str], int]:
    """Chunk counts keyed by (chapter_no, section_no), for the section-level ingested flags."""
    with cursor() as cur:
        rows = cur.execute(
            "SELECT chapter_no, section_no, count(*) AS n FROM chunks "
            "WHERE subject = %s GROUP BY chapter_no, section_no",
            (subject,),
        ).fetchall()
    return {(int(r["chapter_no"]), str(r["section_no"])): int(r["n"]) for r in rows}


def chapter_chunks(subject: str, chapter_no: int, limit: int = 200) -> list[dict[str, Any]]:
    """Every chunk of one chapter, in reading order. This is the quiz generator's only source:
    a quiz question can never be about a chapter the corpus does not contain."""
    with cursor() as cur:
        rows = cur.execute(
            f"SELECT {_SELECT_COLS} FROM chunks "
            "WHERE subject = %(subject)s AND chapter_no = %(chapter_no)s "
            "ORDER BY page_start, section_no, id LIMIT %(limit)s",
            {"subject": subject, "chapter_no": chapter_no, "limit": limit},
        ).fetchall()
    return [dict(row) for row in rows]


def vector_search(
    subject: str,
    embedding: Sequence[float],
    chapter_no: int | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Cosine arm. Returns rows with `vector_score` (1 - cosine distance, so higher is better)."""
    sql = f"""
        SELECT {_SELECT_COLS},
               1 - (embedding <=> %(vec)s::vector) AS vector_score
        FROM chunks
        WHERE subject = %(subject)s
          AND (%(chapter_no)s::int IS NULL OR chapter_no = %(chapter_no)s)
          AND embedding IS NOT NULL
        ORDER BY embedding <=> %(vec)s::vector
        LIMIT %(limit)s
    """
    with cursor() as cur:
        rows = cur.execute(
            sql,
            {
                "subject": subject,
                "chapter_no": chapter_no,
                "vec": vector_literal(embedding),
                "limit": limit,
            },
        ).fetchall()
    return [dict(row) for row in rows]


def fts_search(
    subject: str,
    tsquery: str,
    chapter_no: int | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Full-text arm over `chunks.tsv`, ranked by `ts_rank_cd`.

    `tsquery` is a tsquery string built by `retriever.build_fts_query` — an OR of the question's
    content terms. Passing a natural-language sentence straight to `websearch_to_tsquery` ANDs
    every term and returns nothing for most questions; see that function's docstring for the
    measured evidence. An empty query means the question had no content words at all, and the arm
    correctly contributes no candidates.
    """
    if not tsquery.strip():
        return []
    sql = f"""
        SELECT {_SELECT_COLS},
               ts_rank_cd(tsv, to_tsquery('english', %(q)s)) AS fts_score
        FROM chunks
        WHERE subject = %(subject)s
          AND (%(chapter_no)s::int IS NULL OR chapter_no = %(chapter_no)s)
          AND tsv @@ to_tsquery('english', %(q)s)
        ORDER BY fts_score DESC, page_start ASC
        LIMIT %(limit)s
    """
    with cursor() as cur:
        rows = cur.execute(
            sql,
            {"subject": subject, "q": tsquery, "chapter_no": chapter_no, "limit": limit},
        ).fetchall()
    return [dict(row) for row in rows]


def chunks_by_ids(ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    with cursor() as cur:
        rows = cur.execute(
            f"SELECT {_SELECT_COLS} FROM chunks WHERE id = ANY(%(ids)s::text[])",
            {"ids": list(ids)},
        ).fetchall()
    return {str(r["id"]): dict(r) for r in rows}


def subjects_in_corpus() -> list[str]:
    with cursor() as cur:
        rows = cur.execute(
            "SELECT subject, count(*) AS n FROM chunks GROUP BY subject ORDER BY subject"
        ).fetchall()
    return [str(r["subject"]) for r in rows]


# --------------------------------------------------------------------------------------
# quiz history (CONTRACTS section 4: GET /progress/{student_id})
# --------------------------------------------------------------------------------------


def record_attempts(attempts: Sequence[dict[str, Any]]) -> int:
    if not attempts:
        return 0
    sql = """
        INSERT INTO quiz_attempts
            (student_id, subject, chapter_no, section_no, question, expected_key, answer, correct)
        VALUES (%(student_id)s, %(subject)s, %(chapter_no)s, %(section_no)s, %(question)s,
                %(expected_key)s, %(answer)s, %(correct)s)
    """
    with cursor() as cur:
        cur.executemany(sql, list(attempts))
    return len(attempts)


def progress_rows(student_id: str, subject: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT subject, chapter_no,
               count(*) AS attempts,
               count(*) FILTER (WHERE correct) AS correct,
               max(created_at) AS last_attempt
        FROM quiz_attempts
        WHERE student_id = %(student_id)s
          AND (%(subject)s::text IS NULL OR subject = %(subject)s)
        GROUP BY subject, chapter_no
        ORDER BY subject, chapter_no
    """
    with cursor() as cur:
        rows = cur.execute(sql, {"student_id": student_id, "subject": subject}).fetchall()
    out = []
    for r in rows:
        attempts = int(r["attempts"])
        correct = int(r["correct"])
        last = r["last_attempt"]
        out.append(
            {
                "subject": r["subject"],
                "chapter_no": int(r["chapter_no"]),
                "attempts": attempts,
                "correct": correct,
                "accuracy": round(correct / attempts, 4) if attempts else 0.0,
                "last_attempt": last.isoformat() if last is not None else None,
            }
        )
    return out


# --------------------------------------------------------------------------------------
# corpus loading: corpus/chunks/<subject>.jsonl -> embeddings -> Postgres
# --------------------------------------------------------------------------------------


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: not JSON — {exc}") from exc


def validate_chunk(record: dict[str, Any]) -> None:
    missing = [k for k in CHUNK_FIELDS if k not in record]
    if missing:
        raise ValueError(f"chunk {record.get('id')!r} is missing {missing}")
    if not str(record["text"]).strip():
        raise ValueError(f"chunk {record.get('id')!r} has empty text")


def load_chunks(
    paths: Sequence[Path],
    *,
    reembed_all: bool = False,
    batch_size: int = 32,
) -> dict[str, int]:
    """Embed and upsert chunk JSONL files. Returns counts per file.

    Idempotent: chunk ids are the primary key, so re-running after a partial ingest repairs
    rows instead of duplicating them.
    """
    from . import embed as embed_mod

    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    init_schema()
    counts: dict[str, int] = {}
    for path in paths:
        records = list(read_jsonl(Path(path)))
        for record in records:
            validate_chunk(record)
        if not records:
            counts[str(path)] = 0
            continue
        written = 0
        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            embeddings = embed_mod.embed_passages([str(r["text"]) for r in batch])
            written += upsert_chunks(batch, embeddings)
        counts[str(path)] = written
    return counts


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(prog="python -m api.db", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="apply pending migrations")
    sub.add_parser("status", help="show schema versions and chunk counts")

    load = sub.add_parser("load", help="embed and upsert corpus chunk JSONL into Postgres")
    load.add_argument("jsonl", nargs="+", type=Path, help="corpus/chunks/<subject>.jsonl")
    load.add_argument("--batch-size", type=int, default=32)

    args = parser.parse_args(argv)

    if args.command == "init":
        print(json.dumps({"applied_migrations": init_schema()}))
        return 0
    if args.command == "status":
        with cursor() as cur:
            versions = [
                row["version"]
                for row in cur.execute("SELECT version FROM schema_migrations ORDER BY version")
            ]
        print(
            json.dumps(
                {
                    "migrations": versions,
                    "chunks": count_chunks(),
                    "subjects": subjects_in_corpus(),
                    "db_available": available(),
                }
            )
        )
        return 0
    if args.command == "load":
        counts = load_chunks(args.jsonl, batch_size=args.batch_size)
        print(json.dumps({"loaded": counts, "chunks_total": count_chunks()}, indent=2))
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
