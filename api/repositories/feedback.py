"""Session feedback — `raw.feedback`, rekeyed on `session_id` (ADR-008)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.repositories.connection import readable, table_exists, writable


class FeedbackRepository:
    """Writes and reads `feedback`.

    ADR-008 added `session_id` as the real key. `session_title` stays populated because the
    existing dbt chain (`stg_feedback -> int_feedback_enriched -> mart_feedback_summary`) is
    declared normative by E.2 and groups on it — the change is additive, so that chain and its
    tests keep working untouched.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def add(
        self, session_id: str, rating: str, note: str | None, session_title: str = ""
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC)
        with writable(self._db_path) as con:
            con.execute(
                """
                insert into feedback (session_id, session_title, rating, note, created_at)
                values (?, ?, ?, ?, ?)
                """,
                [session_id, session_title, rating, note or "", created_at],
            )
        return {
            "session_id": session_id,
            "rating": rating,
            "note": note,
            "created_at": created_at,
        }

    def for_session(self, session_id: str) -> list[dict[str, Any]]:
        with readable(self._db_path) as con:
            if not table_exists(con, "feedback"):
                return []
            rows = con.execute(
                """
                select session_id, rating, note, created_at
                from feedback
                where session_id = ?
                order by created_at
                """,
                [session_id],
            ).fetchall()
        return [
            {
                "session_id": str(r[0]),
                "rating": r[1],
                "note": r[2] or None,
                "created_at": r[3],
            }
            for r in rows
        ]
