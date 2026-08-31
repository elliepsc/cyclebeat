"""The transactional store: Postgres in compose and production, SQLite on a bare clone.

ADR-009 separates the roles. **Postgres is OLTP** — `sessions`, `feedback`, app state, small
frequent writes that must not be lost. **DuckDB stays OLAP** — lake → dbt → marts → copilot,
read here by `track.py` and `quality.py`. Nothing in this module touches DuckDB.

`DATABASE_URL` picks the engine:

    unset                      -> SQLite at data/cyclebeat_app.db   (clean clone, unit tests)
    postgresql://... / postgres://...  -> Postgres via psycopg      (compose, Neon)

The SQLite fallback exists because E.8 requires the project to run with no key and no service
on a clean clone, and criterion 14 is tested from one. Making Postgres a hard prerequisite for
reading the demo would break both — the risk ADR-009 flagged and left to this phase.

**Why a thin adapter and not an ORM.** The SQL below is deliberately at the common denominator
of the two engines, so exactly one thing differs: the parameter marker. SQLite wants `?`,
psycopg wants `%s`. `INSERT ... ON CONFLICT DO UPDATE` is native to both (SQLite >= 3.24;
Python 3.11 bundles 3.45), and every timestamp is supplied from Python rather than by `now()`,
which SQLite does not have under that name. That is the whole incompatibility surface, and it
is not worth a dependency the size of SQLAlchemy.
"""

from __future__ import annotations

import datetime as dt
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol


def _register_sqlite_datetime_handlers() -> None:
    """Teach sqlite3 to round-trip `datetime` the way psycopg already does.

    Registered explicitly rather than relying on the built-in adapters: those are deprecated
    from Python 3.12 and emit a warning under `-W error`. The repo is pinned to 3.11 today, so
    this is about not planting a failure for whoever unpins it.

    ISO-8601 in, aware `datetime` out — so a repository reads the same type from either engine
    and never has to branch on which store it is talking to.
    """
    sqlite3.register_adapter(dt.datetime, lambda value: value.isoformat())
    sqlite3.register_converter(
        "TIMESTAMP", lambda raw: dt.datetime.fromisoformat(raw.decode("utf-8"))
    )


_register_sqlite_datetime_handlers()

# Both tables are OLTP. `fct_session` is deliberately NOT here: ADR-009 makes it a dbt model
# built in the warehouse from `raw.sessions`, which the pipeline ingests from this store. The
# API writing a fact table directly was the ADR-008 mistake.
DDL_SESSIONS = """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id     VARCHAR PRIMARY KEY,
        level          VARCHAR NOT NULL,
        goal           VARCHAR NOT NULL,
        duration_min   INTEGER NOT NULL,
        verdict        VARCHAR NOT NULL,
        n_segments     INTEGER NOT NULL,
        duration_gap_s DOUBLE PRECISION NOT NULL,
        created_at     TIMESTAMP NOT NULL,
        plan_json      TEXT NOT NULL
    )
"""

# ADR-008 rekeyed feedback on `session_id`, and ADR-009 keeps that. `session_title` stays as a
# denormalized label because the normative dbt chain groups on it.
DDL_FEEDBACK = """
    CREATE TABLE IF NOT EXISTS feedback (
        session_id    VARCHAR NOT NULL,
        session_title VARCHAR,
        rating        VARCHAR NOT NULL,
        note          TEXT,
        created_at    TIMESTAMP NOT NULL
    )
"""

DDL = (DDL_SESSIONS, DDL_FEEDBACK)


class Cursor(Protocol):
    """The slice of DB-API both drivers implement and this package uses."""

    def execute(self, sql: str, params: Sequence[Any] = ..., /) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...


def database_url() -> str:
    """The configured DSN, or `""` when the SQLite fallback applies."""
    return os.environ.get("DATABASE_URL", "").strip()


def is_postgres() -> bool:
    return database_url().startswith(("postgresql://", "postgres://"))


def sqlite_path() -> Path:
    """Where the fallback store lives. Beside the DuckDB warehouse, and gitignored like it."""
    configured = os.environ.get("APP_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "cyclebeat_app.db"


class Database:
    """A connection plus the one dialect difference that matters.

    Short-lived by design: opened per operation, closed straight after. Postgres would tolerate
    a pool, but holding a handle buys nothing here and the symmetry keeps the SQLite path from
    locking the file between requests.
    """

    def __init__(self, connection: Any, postgres: bool) -> None:
        self._connection = connection
        self._postgres = postgres

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Cursor:
        """Run a statement, translating the parameter marker for the driver.

        The SQL in this package is written with `?`. A plain replace is safe here **because no
        statement contains a `?` inside a string literal** — if one ever does, this is the line
        that will be wrong, which is why the constraint is written down rather than assumed.
        """
        statement = sql.replace("?", "%s") if self._postgres else sql
        cursor: Cursor = self._connection.cursor()
        cursor.execute(statement, tuple(params or ()))
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


def _connect() -> Database:
    url = database_url()
    if is_postgres():
        import psycopg  # imported lazily: a bare clone never installs a server to talk to

        return Database(psycopg.connect(url), postgres=True)

    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # `detect_types` so TIMESTAMP columns come back as datetimes on both engines rather than
    # as strings on one of them — otherwise the repositories would have to know which is which.
    connection = sqlite3.connect(
        str(path), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    return Database(connection, postgres=False)


@contextmanager
def connection(*, create: bool = True) -> Iterator[Database]:
    """A transaction. Commits on success, rolls back by closing on failure.

    `create=True` applies the DDL first. It is idempotent and cheap on both engines, and it is
    what lets a clean clone answer its first request without a migration step.

    A failed write RAISES. That is the point of ADR-008/009: the v1 API swallowed the error and
    kept a JSON file as the real store, and E.2 recorded that as debt to close in phase 4.
    """
    database = _connect()
    try:
        if create:
            for statement in DDL:
                database.execute(statement)
            database.commit()
        yield database
        database.commit()
    finally:
        database.close()


def describe() -> str:
    """Which store is in use, for logs and the health of a deployed instance."""
    return "postgres" if is_postgres() else f"sqlite:{sqlite_path().name}"
