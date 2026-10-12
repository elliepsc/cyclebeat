"""A locked, read-only DuckDB connection for the agent tools (E.4, ADR-012).

`warehouse.readable()` is right for the API: it falls back to a writable connection so a fresh
clone does not 500 before the first `make ingest`. A tool that runs SQL written by an agent
cannot afford that fallback, so this module never opens anything but a read-only handle, and
locks the engine before the first statement:

* `read_only=True` — DuckDB refuses every write to the database file;
* `enable_external_access=false` — no file reads (`read_csv`, `glob`, replacement scans), no
  `COPY`, no `ATTACH`, no `INSTALL`/`LOAD`;
* extension auto-install and auto-load off;
* `lock_configuration=true` — a later `SET` cannot undo any of the above.

That is the "by construction" half. The other half is the SQL guard in
`api/services/warehouse_tools.py`, which refuses anything but one SELECT on the marts
allowlist before DuckDB sees it: `PRAGMA` statements still run on a locked engine.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

from api.repositories.warehouse import warehouse_path

LOCKED_CONFIG: dict[str, Any] = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "lock_configuration": True,
}


class WarehouseUnavailable(Exception):
    """The warehouse cannot be opened read-only: absent, locked by a writer, or corrupt."""


@contextmanager
def locked(db_path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A read-only, externally sealed connection. Never creates the database file."""
    path = db_path or warehouse_path()
    if not path.is_file():
        raise WarehouseUnavailable(f"no warehouse at {path.name}; run `make dbt` first")
    try:
        con = duckdb.connect(str(path), read_only=True, config=LOCKED_CONFIG)
    except duckdb.Error as exc:
        raise WarehouseUnavailable(f"cannot open the warehouse read-only: {exc}") from exc
    try:
        yield con
    finally:
        con.close()


def run_select(
    con: duckdb.DuckDBPyConnection, sql: str, max_rows: int, timeout_s: float
) -> tuple[list[str], list[tuple[Any, ...]], bool]:
    """Run one already-validated SELECT. Returns (columns, rows, truncated).

    DuckDB 0.10 has no statement timeout, so a timer interrupts the connection. One row past
    `max_rows` is fetched only to report truncation honestly.
    """
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cursor = con.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
    finally:
        timer.cancel()
    return columns, rows[:max_rows], len(rows) > max_rows
