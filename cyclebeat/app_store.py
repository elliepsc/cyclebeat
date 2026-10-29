"""Extract the transactional store into the lake (ADR-009).

§2.7: *"Le pipeline ingère les données transactionnelles Postgres dans l'entrepôt pour
l'analytique."* This is that step. Sessions and feedback are produced by the API into
Postgres (or SQLite on a bare clone); the pipeline copies them into `lake/raw/sessions/` and
`lake/raw/feedback/`, and `cyclebeat.warehouse` loads the lake as it already does for tracks
and resolutions.

**Why via the lake rather than dbt reading Postgres directly.** DuckDB's `postgres_scanner`
would remove this module, but it would also make `make dbt` require a reachable Postgres —
the warehouse would stop being rebuildable offline, and the lake would stop being its single
source. Both are properties phase 2 established and this phase should not spend.

Lives in `cyclebeat/` rather than `api/` because the pipeline runs without the API: a DAG
imports this, and importing `api/` would drag FastAPI into Airflow. The SQL here is read-only
`SELECT` against the app store — flagged explicitly in the PR rather than quietly stretching
E.0.5, which puts SQL in `api/repositories/` and `dbt/`.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class RawSession(BaseModel):
    """One row of `raw.sessions` — a generated session, as the warehouse sees it."""

    session_id: str
    level: str
    goal: str
    duration_min: int
    verdict: str
    n_segments: int
    duration_gap_s: float
    created_at: datetime


class RawFeedback(BaseModel):
    """One row of `raw.feedback`.

    `rating` is stored verbatim. The API speaks E.3's `up`/`down`; the v1 rows speak
    `Great`/`Okay`/`Hard`. `stg_feedback` keeps the two scales apart rather than mapping one
    onto the other — satisfaction and perceived effort are different axes, and an equivalence
    between them would be invented rather than measured.
    """

    session_id: str | None = None
    session_title: str | None = None
    rating: str
    note: str | None = None
    created_at: datetime


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def _sqlite_path() -> Path:
    configured = os.environ.get("APP_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "cyclebeat_app.db"


def _rows(sql: str) -> list[tuple[Any, ...]]:
    """Run a read-only query against whichever store is configured.

    Returns `[]` when the store is simply not there — a clean clone that has never started the
    API has no sessions, and that is data, not an error. A Postgres that is configured but
    unreachable is different: it raises, so a broken DSN in production is not silently reported
    as "no sessions yet".
    """
    url = _database_url()
    if url.startswith(("postgresql://", "postgres://")):
        import psycopg

        with psycopg.connect(url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return list(cursor.fetchall())

    path = _sqlite_path()
    if not path.exists():
        return []
    connection_sqlite = sqlite3.connect(str(path))
    try:
        try:
            return list(connection_sqlite.execute(sql).fetchall())
        except sqlite3.OperationalError:
            # The file exists but the API has never created its tables.
            return []
    finally:
        connection_sqlite.close()


class UnreadableDate(ValueError):
    """A store row whose `created_at` is not a date. It fails the extraction (#57)."""


def _as_datetime(value: Any, row: str) -> datetime:
    """The store's `created_at` as an aware UTC datetime.

    A naive value is read as UTC: the API writes `datetime.now(UTC)`, SQLite keeps it as an ISO
    string with its offset, and a Postgres `timestamp` column holds it as UTC wall time because
    the API's session is pinned to UTC (`api/repositories/database.py`). Anything that is not a
    date raises, naming the row: replacing it with the current time would give the row a new
    timestamp at every extraction (#57).
    """
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None:
        raise UnreadableDate(f"{row}: unreadable created_at {value!r}")
    if parsed.utcoffset() is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_sessions() -> list[RawSession]:
    rows = _rows(
        """
        select session_id, level, goal, duration_min, verdict,
               n_segments, duration_gap_s, created_at
        from sessions
        order by session_id
        """
    )
    return [
        RawSession(
            session_id=str(r[0]),
            level=str(r[1]),
            goal=str(r[2]),
            duration_min=int(r[3]),
            verdict=str(r[4]),
            n_segments=int(r[5]),
            duration_gap_s=float(r[6]),
            created_at=_as_datetime(r[7], f"sessions row session_id={r[0]!r}"),
        )
        for r in rows
    ]


def read_feedback() -> list[RawFeedback]:
    rows = _rows(
        """
        select session_id, session_title, rating, note, created_at
        from feedback
        order by created_at, session_id
        """
    )
    return [
        RawFeedback(
            session_id=None if r[0] is None else str(r[0]),
            session_title=None if r[1] is None else str(r[1]),
            rating=str(r[2]),
            note=None if r[3] is None else str(r[3]),
            created_at=_as_datetime(
                r[4], f"feedback row session_id={r[0]!r} session_title={r[1]!r}"
            ),
        )
        for r in rows
    ]


def extract_to_lake(dt: date | None = None, root: Path | None = None) -> dict[str, int]:
    """Write both tables into today's lake partition. Row counts per dataset.

    Full replace of the `dt=` partition, matching how `raw/tracks` and `raw/resolutions`
    behave — re-running the same day overwrites instead of appending, which is the E.5
    idempotency the DAG tests already assert.

    A row whose `created_at` is not a date raises `UnreadableDate` before anything is written.

    An empty table writes no partition rather than an empty one: `write_partition` needs a row
    to infer its schema, and an absent partition reads back as "nothing new today" while a
    previous day's data stays queryable.
    """
    from cyclebeat import lake

    stamp = dt or datetime.now(UTC).date()
    counts: dict[str, int] = {}

    # Both tables are read before either is written: an unreadable row raises here, and no
    # partition of this extraction is left half-done (#57).
    sessions = read_sessions()
    feedback = read_feedback()

    if sessions:
        lake.write_partition(sessions, lake.SESSIONS, stamp, root=root)
    counts["sessions"] = len(sessions)

    if feedback:
        lake.write_partition(feedback, lake.FEEDBACK, stamp, root=root)
    counts["feedback"] = len(feedback)

    return counts
