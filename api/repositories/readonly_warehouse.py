"""Locked DuckDB connections for the agent tools (E.4, ADR-012).

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

`exposed()` is what the tools run on since the phase-10 audit (ADR-012 note, 13 October
2026). Three bypasses of the guard had one cause -- the guard inferred from SQL text which
tables would be read -- so the tools no longer open the warehouse itself: an in-memory
database receives COPIES of the allowed marts only, then path settings are neutralised and
the engine is locked as above. A table off the allowlist does not exist where their SQL
runs, and the guard becomes the second line. Known residual on DuckDB 0.10.2: `sniff_csv`
still reads a file there (CVE-2024-41672); the guard refuses it, as a source of any shape
(LATERAL included) and as a function name anywhere in the query.

`locked()` has no production caller since then; it is kept because the engine-level tests of
`test_copilot_guards.py` pin what a locked file connection refuses.

Neither ever tells the caller WHY the warehouse is unavailable: DuckDB's error names the file,
the executable holding the lock and its PID. The caller gets `UNAVAILABLE_MESSAGE`; the
detail goes to this module's logger (stderr), for whoever runs the server.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from typing import Any

import duckdb

from api.repositories.warehouse import warehouse_path

log = logging.getLogger(__name__)

UNAVAILABLE_MESSAGE = "warehouse unavailable: absent or locked by a writer"

LOCKED_CONFIG: dict[str, Any] = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "lock_configuration": True,
}


# Settings whose value is a path on this machine (`secret_directory` carries the OS user's
# home): set to neutral values on the exposure database before the configuration is locked.
NEUTRAL_SETTINGS: dict[str, str] = {
    "secret_directory": "/nonexistent",
    "home_directory": "/nonexistent",
    "temp_directory": "",
}
EXPOSURE_MEMORY_LIMIT = "512MB"


class WarehouseUnavailable(Exception):
    """The warehouse cannot be opened read-only: absent, locked by a writer, or corrupt."""


def _unavailable(detail: str) -> WarehouseUnavailable:
    """Log the machine-specific detail; hand the caller the fixed message only."""
    log.warning("warehouse unavailable: %s", detail)
    return WarehouseUnavailable(UNAVAILABLE_MESSAGE)


def _is_file(path: Path) -> bool:
    """`Path.is_file()`, minus the OSError it re-raises (EACCES on an unsearchable parent).

    That PermissionError carried the absolute path out of both tools (pass-4 audit, NEW-L1).
    """
    try:
        return path.is_file()
    except OSError as exc:
        raise _unavailable(f"cannot stat {path}: {exc}") from exc


@contextmanager
def locked(db_path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A read-only, externally sealed connection. Never creates the database file."""
    path = db_path or warehouse_path()
    if not _is_file(path):
        raise _unavailable(f"no warehouse file at {path}; run `make dbt` first")
    try:
        con = duckdb.connect(str(path), read_only=True, config=LOCKED_CONFIG)
    except duckdb.Error as exc:
        raise _unavailable(f"cannot open {path} read-only: {exc}") from exc
    try:
        yield con
    finally:
        con.close()


@contextmanager
def exposed(db_path: Path | None, tables: Iterable[str]) -> Iterator[duckdb.DuckDBPyConnection]:
    """An in-memory, locked database holding copies of `tables` only. Never creates a file.

    A table of `tables` the warehouse does not have is simply absent, like on a fresh clone.
    Built per call (about 13 ms on the demo warehouse, measured): a write dies with the call.
    """
    path = db_path or warehouse_path()
    if not _is_file(path):
        raise _unavailable(f"no warehouse file at {path}; run `make dbt` first")
    names = sorted(set(tables))
    if not all(name.isascii() and name.isidentifier() for name in names):
        raise ValueError(f"not a plain table name: {names}")
    con = duckdb.connect(
        ":memory:",
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
    )
    try:
        try:
            literal = str(path).replace("'", "''")
            con.execute(f"ATTACH '{literal}' AS source (READ_ONLY)")
            present = {
                row[0]
                for row in con.execute(
                    "select table_name from information_schema.tables "
                    "where table_catalog = 'source' and table_schema = 'main' "
                    # a view's SQL would run here, while external access is still on
                    "and table_type = 'BASE TABLE'"
                ).fetchall()
            }
            for name in names:
                if name in present:
                    con.execute(f'create table main."{name}" as select * from source.main."{name}"')
            con.execute("DETACH source")
        except duckdb.Error as exc:
            raise _unavailable(f"cannot expose {path}: {exc}") from exc
        for setting, value in NEUTRAL_SETTINGS.items():
            con.execute(f"SET {setting} = '{value}'")
        con.execute(f"SET memory_limit = '{EXPOSURE_MEMORY_LIMIT}'")
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        yield con
    finally:
        con.close()


@cache
def table_function_names() -> frozenset[str]:
    """Names DuckDB knows ONLY as table functions (read_*, sniff_csv, glob, duckdb_*, ...).

    Read from the installed engine, so the list follows a DuckDB upgrade. Names that are also
    scalar, macro or aggregate functions (`range`, `generate_series`, `repeat`) are left out,
    and so is `unnest`, everyday scalar syntax on a list column that reads no data. The guard
    refuses every name returned here wherever it appears in a query.
    """
    con = duckdb.connect(
        ":memory:",
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
    )
    try:
        rows = con.execute(
            "select function_name from duckdb_functions() "
            "where function_type in ('table', 'table_macro') "
            "except "
            "select function_name from duckdb_functions() "
            "where function_type in ('scalar', 'macro', 'aggregate')"
        ).fetchall()
    finally:
        con.close()
    return frozenset(str(row[0]).lower() for row in rows) - {"unnest"}


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
