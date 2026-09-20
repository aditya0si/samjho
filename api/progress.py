"""Quiz history store (CONTRACTS section 4: `GET /progress/{student_id}`).

One small class so `/progress` has a seam a test can replace with an in-memory double, and so the
"no database" case is a clear 503 rather than an empty page that looks like a student who has
never been quizzed.
"""

from __future__ import annotations

from typing import Any

from . import db


class ProgressStore:
    """Postgres-backed. `available()` decides between 200 and 503 on the endpoint."""

    name = "postgres"

    def available(self) -> bool:
        return db.available()

    def history(self, student_id: str, subject: str | None = None) -> list[dict[str, Any]]:
        return db.progress_rows(student_id, subject)

    def record(self, attempts: list[dict[str, Any]]) -> int:
        return db.record_attempts(attempts)


DEFAULT_STORE = ProgressStore()
