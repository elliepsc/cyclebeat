"""Persists and reads sessions — the E.2 `fct_session` table (ADR-008)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.repositories.connection import readable, table_exists, writable


class SessionRepository:
    """`fct_session` read/write.

    DuckDB is the source of truth here, not a best-effort mirror of a JSON file. That was the
    residual gap E.2's dated note left to phase 4, and closing it is why a failed write now
    raises instead of being swallowed: a session the caller was told exists must exist.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def save(self, plan: dict[str, Any]) -> None:
        """Store a generated session. `plan` is the serialized wire SessionPlan."""
        with writable(self._db_path) as con:
            con.execute(
                """
                insert or replace into fct_session (
                    session_id, level, goal, duration_min, verdict,
                    n_segments, duration_gap_s, llm_cost_usd, latency_ms,
                    created_at, plan_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    plan["session_id"],
                    plan["level"],
                    plan["goal"],
                    int(plan["duration_min"]),
                    plan["verdict"],
                    len(plan.get("segments", [])),
                    float(plan.get("duration_gap_s", 0.0)),
                    # Both stay NULL until phase 6 wires LiteLLM; the columns exist now
                    # because E.2 declares them on fct_session.
                    None,
                    None,
                    _parse_ts(plan.get("created_at")),
                    json.dumps(plan, ensure_ascii=False),
                ],
            )

    def get(self, session_id: str) -> dict[str, Any] | None:
        """The stored plan, replayed exactly as it was served."""
        with readable(self._db_path) as con:
            if not table_exists(con, "fct_session"):
                return None
            row = con.execute(
                "select plan_json from fct_session where session_id = ?", [session_id]
            ).fetchone()
        if not row or row[0] is None:
            return None
        loaded: dict[str, Any] = json.loads(row[0])
        return loaded

    def exists(self, session_id: str) -> bool:
        with readable(self._db_path) as con:
            if not table_exists(con, "fct_session"):
                return False
            row = con.execute(
                "select 1 from fct_session where session_id = ?", [session_id]
            ).fetchone()
        return row is not None

    def list(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        """A page of summaries, newest first, plus the unpaged total.

        Summaries are read from the scalar columns rather than by parsing `plan_json` — the
        reason those columns exist beside the blob.
        """
        with readable(self._db_path) as con:
            if not table_exists(con, "fct_session"):
                return [], 0
            total_row = con.execute("select count(*) from fct_session").fetchone()
            total = int(total_row[0]) if total_row else 0
            rows = con.execute(
                """
                select session_id, level, goal, duration_min, verdict,
                       n_segments, duration_gap_s, created_at
                from fct_session
                order by created_at desc, session_id desc
                limit ? offset ?
                """,
                [limit, offset],
            ).fetchall()

        items = [
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
        ]
        return items, total


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
