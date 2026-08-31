"""Session feedback in the transactional store (ADR-008 keying, ADR-009 store)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api.repositories.database import connection


class FeedbackRepository:
    """`feedback` read/write.

    ADR-008 made `session_id` the real key and ADR-009 moved the table to Postgres/SQLite.
    `session_title` is still written: the normative dbt chain (`stg_feedback` →
    `int_feedback_enriched` → `mart_feedback_summary`) groups on it, and the warehouse gets
    these rows by ingestion, so the label has to be in the row when it is ingested.

    The `rating` written here is E.3's `up`/`down`. It is stored **verbatim** — the warehouse
    keeps the two scales apart (`rating_scale`) rather than mapping one onto the other, because
    satisfaction and perceived effort are different axes and any equivalence would be invented.
    """

    def add(
        self, session_id: str, rating: str, note: str | None, session_title: str = ""
    ) -> dict[str, Any]:
        created_at = datetime.now(UTC)
        with connection() as db:
            db.execute(
                """
                insert into feedback (session_id, session_title, rating, note, created_at)
                values (?, ?, ?, ?, ?)
                """,
                [session_id, session_title, rating, note, created_at],
            )
        return {
            "session_id": session_id,
            "rating": rating,
            "note": note,
            "created_at": created_at,
        }

    def for_session(self, session_id: str) -> list[dict[str, Any]]:
        with connection() as db:
            rows = db.execute(
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
                "note": r[2],
                "created_at": r[3],
            }
            for r in rows
        ]
