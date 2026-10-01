"""Sessions in the transactional store (ADR-009).

Writes to Postgres, or to SQLite on a bare clone. **Not to DuckDB** — that was the ADR-008
mistake this supersedes. The warehouse gets these rows by ingestion, and `fct_session` is a dbt
model built from `raw.sessions`, not something the API writes.

The public interface is unchanged from the DuckDB version on purpose: `api/services/session.py`
and its tests know nothing about the store, so swapping engines touched neither.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from api.repositories.database import connection


class SessionRepository:
    """`sessions` read/write.

    A failed write raises. E.2 recorded the v1 API's `try/except pass` as debt, and closing it
    is the point: a session the caller was told exists must exist.
    """

    def save(self, plan: dict[str, Any]) -> None:
        """Store a generated session. `plan` is the serialized wire SessionPlan.

        `ON CONFLICT DO UPDATE` rather than a plain insert so a retry replaces instead of
        duplicating — the same idempotency the lake partitions have. Native to both engines
        (SQLite >= 3.24), which is why no dialect branch is needed here.
        """
        with connection() as db:
            db.execute(
                """
                insert into sessions (
                    session_id, level, goal, duration_min, verdict,
                    n_segments, duration_gap_s, created_at, plan_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (session_id) do update set
                    level          = excluded.level,
                    goal           = excluded.goal,
                    duration_min   = excluded.duration_min,
                    verdict        = excluded.verdict,
                    n_segments     = excluded.n_segments,
                    duration_gap_s = excluded.duration_gap_s,
                    created_at     = excluded.created_at,
                    plan_json      = excluded.plan_json
                """,
                [
                    plan["session_id"],
                    plan["level"],
                    plan["goal"],
                    int(plan["duration_min"]),
                    plan["verdict"],
                    len(plan.get("segments", [])),
                    float(plan.get("duration_gap_s", 0.0)),
                    _parse_ts(plan.get("created_at")),
                    json.dumps(plan, ensure_ascii=False),
                ],
            )

    def get(self, session_id: str) -> dict[str, Any] | None:
        """The stored plan, replayed exactly as it was served."""
        with connection() as db:
            row = db.execute(
                "select plan_json from sessions where session_id = ?", [session_id]
            ).fetchone()
        if not row or row[0] is None:
            return None
        loaded: dict[str, Any] = json.loads(row[0])
        return loaded

    def exists(self, session_id: str) -> bool:
        with connection() as db:
            row = db.execute(
                "select 1 from sessions where session_id = ?", [session_id]
            ).fetchone()
        return row is not None

    def list(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """A page of summaries, newest first, plus the unpaged total.

        Read from the scalar columns rather than by parsing `plan_json` — which is why those
        columns sit beside the blob at all.
        """
        with connection() as db:
            total_row = db.execute("select count(*) from sessions").fetchone()
            total = int(total_row[0]) if total_row else 0
            rows = db.execute(
                """
                select session_id, level, goal, duration_min, verdict,
                       n_segments, duration_gap_s, created_at
                from sessions
                order by created_at desc, session_id desc
                limit ? offset ?
                """,
                [limit, offset],
            ).fetchall()

        return [
            {
                "session_id": str(r[0]),
                "level": r[1],
                "goal": r[2],
                "duration_min": int(r[3]),
                "verdict": r[4],
                "n_segments": int(r[5]),
                "duration_gap_s": float(r[6]),
                "created_at": r[7],
            }
            for r in rows
        ], total


def _parse_ts(value: Any) -> datetime:
    """Accept an ISO string or a datetime; fall back to now."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
