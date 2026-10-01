"""Read-only access to the DuckDB analytical warehouse (ADR-009).

The other half of the split: `database.py` owns the transactional store, this owns the
warehouse. Read-only on purpose — the warehouse is built by the lake and dbt, and the API has
no business writing it. That the API *did* write it is exactly what ADR-009 supersedes.

DuckDB takes one writer, so even these reads are opened and closed per operation: a handle held
open would contend with `make dbt` and with the Airflow `load_duckdb` task.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb


def warehouse_path() -> Path:
    """The runtime DuckDB. Same `RUNTIME_DB_PATH` the loader, dbt and CI already use."""
    configured = os.environ.get("RUNTIME_DB_PATH", "")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "cyclebeat_runtime.duckdb"


@contextmanager
def readable(db_path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A read-only connection.

    Falls back to a normal connection when read-only fails — which is what happens against a
    database that does not exist yet, and on Windows when another handle is open. That fallback
    is what keeps a fresh clone from 500-ing before the first `make ingest`.
    """
    path = db_path or warehouse_path()
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

    Every read here checks it. The marts are built by `make dbt`, which a fresh clone has not
    necessarily run, and answering "no data yet" beats a 500 with a DuckDB error in the body.
    """
    row = con.execute(
        "select count(*) from information_schema.tables where table_name = ?", [name]
    ).fetchone()
    return bool(row and row[0])
