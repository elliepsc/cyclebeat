"""DuckDB connection handling and the API-owned schema.

DuckDB takes exactly one writer. The whole repo is built around that (the DAGs carry
`max_active_runs=1` for the same reason), so connections here are opened per operation and
closed immediately rather than held — a long-lived write handle would lock out `make dbt` and
the Airflow `load_duckdb` task.

`RUNTIME_DB_PATH` is the same env var `db/runtime.py`, `cyclebeat/warehouse.py` and the CI
workflow already use. Reusing it rather than inventing a second one keeps one database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

# The E.2 fact table for sessions, materialized here because the API is what produces a
# session. ADR-008 records the shape and why it replaced the v1 `sessions` table.
#
# `plan_json` is the full SessionPlan, stored so a session can be replayed exactly as it was
# served. The scalar columns beside it are not a duplicate for convenience: they are what
# `GET /v1/sessions` pages over and what dbt models, and neither should have to parse JSON.
DDL_FCT_SESSION = """
    CREATE TABLE IF NOT EXISTS fct_session (
        session_id     VARCHAR PRIMARY KEY,
        level          VARCHAR,
        goal           VARCHAR,
        duration_min   INTEGER,
        verdict        VARCHAR,
        n_segments     INTEGER,
        duration_gap_s DOUBLE,
        llm_cost_usd   DOUBLE,
        latency_ms     INTEGER,
        created_at     TIMESTAMP,
        plan_json      VARCHAR
    )
"""

# ADR-008: `session_id` is the real key. `session_title` is kept as a denormalized label so
# `stg_feedback -> int_feedback_enriched -> mart_feedback_summary` and its dbt tests keep
# working untouched — E.2 declared that chain normative, and this change is additive to it.
DDL_FEEDBACK = """
    CREATE TABLE IF NOT EXISTS feedback (
        session_id    VARCHAR,
        session_title VARCHAR,
        rating        VARCHAR,
        note          VARCHAR,
        created_at    TIMESTAMP
    )
"""


def database_path() -> Path:
    """Where the runtime DuckDB lives."""
    configured = os.environ.get("RUNTIME_DB_PATH", "")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "cyclebeat_runtime.duckdb"


@contextmanager
def writable(db_path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A short-lived write connection, with the API-owned tables guaranteed to exist."""
    path = db_path or database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(DDL_FCT_SESSION)
        con.execute(DDL_FEEDBACK)
        _migrate_feedback(con)
        yield con
    finally:
        con.close()


def _migrate_feedback(con: duckdb.DuckDBPyConnection) -> None:
    """Add `session_id` to a pre-existing v1 `feedback` table (ADR-008).

    `CREATE TABLE IF NOT EXISTS` is a no-op on a database that already holds the v1 shape
    (`session_title, rating, note, created_at`), so the new column would never appear and
    every insert would fail on a binder error. Any developer machine or deployed instance
    that ran the v1 API has exactly that table.

    Idempotent, and additive: existing rows keep their `session_title` and get a NULL
    `session_id`, which is honest — that feedback genuinely was not keyed on a session.
    """
    con.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS session_id VARCHAR")


@contextmanager
def readable(db_path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A read-only connection.

    Falls back to a normal connection when read-only fails — which happens on a database that
    does not exist yet, and on Windows when another handle is open. The fallback is what keeps
    a fresh clone from 500-ing before the first `make ingest`.
    """
    path = db_path or database_path()
    try:
        con = duckdb.connect(str(path), read_only=True)
    except duckdb.Error:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(path))
    try:
        yield con
    finally:
        con.close()


def table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    """Whether a table or view is present.

    Every read repository checks this. The marts are built by `make dbt`, which a fresh clone
    has not necessarily run, and answering "no data yet" beats a 500 with a DuckDB error in
    the body.
    """
    row = con.execute(
        "select count(*) from information_schema.tables where table_name = ?", [name]
    ).fetchone()
    return bool(row and row[0])
