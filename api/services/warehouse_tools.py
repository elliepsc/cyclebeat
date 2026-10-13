"""Read-only warehouse tools for agents (E.4 `[rendu]` subset, ADR-012).

One implementation, two consumers: the MCP server in `mcp-server/` today, the phase-6 copilot
later. Everything here is deterministic -- no LLM decides what runs.

`query_marts` guards, in order (E.4):

1. parse with sqlglot (DuckDB dialect); a parse failure is a refusal, never a pass-through;
2. exactly one statement, and it must be a query (SELECT, WITH ... SELECT, set operations);
3. no `SELECT ... INTO`;
4. every table referenced is a mart on `MARTS_ALLOWLIST`, in the default schema, or a CTE
   VISIBLE IN THAT TABLE'S OWN SCOPE (its query or an enclosing one, resolved by sqlglot's
   scope analysis): a CTE defined in some other subquery does not whitelist its name, and a
   table no scope accounts for is refused (fail closed). Identifiers are folded like DuckDB
   folds them, ASCII only; a non-ASCII table or CTE name is refused. Table functions
   (`read_csv`, `glob`, `sniff_csv`, ...) and file paths are refused;
5. no scalar call to a function that reads the catalogue or the configuration
   (`_FORBIDDEN_FUNCTIONS`), and ASCII function names only;
6. `LIMIT 200` injected when absent, and at most 200 rows fetched whatever the LIMIT says;
7. what runs is what was checked: the emitted SQL is guarded again and must come back
   unchanged (sqlglot re-emits function names with Python's Unicode-aware `upper()`, which
   once turned `current_sett\u0131ng` into `CURRENT_SETTING` after the check);
8. 5 s timeout.

Guards 4, 5 and 7 come from the phase-10 audits (PR #38, then the fix branch): CTE scope,
catalogue functions, Unicode folding. The three bypasses had one cause -- the guard inferred
from SQL text which tables would be read -- so the guard is now the SECOND line: the SQL runs
on `exposed()` (`api/repositories/readonly_warehouse.py`), an in-memory, locked database that
holds copies of the allowed marts only. Errors come back as `ToolError` with a code and a
one-line message -- no stack trace reaches the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from api.repositories.quality import QualityRepository
from api.repositories.readonly_warehouse import WarehouseUnavailable, exposed, run_select
from api.services.quality import QualityService

# E.4's allowlist, restricted to the marts that exist: `fct_llm_calls` and `fct_agent_runs`
# arrive with the phase-6 LLM layer and join the list then (owner decision, 2026-10-11).
MARTS_ALLOWLIST: frozenset[str] = frozenset(
    {"dim_track", "fct_session", "mart_bpm_coverage", "mart_data_quality"}
)
_QUALITY_MARTS: frozenset[str] = frozenset({"mart_bpm_coverage", "mart_data_quality"})
MAX_ROWS = 200
TIMEOUT_S = 5.0
_DEFAULT_SCHEMA = "main"

# Scalar calls the table-function check cannot see, measured on the locked DuckDB 0.10.2
# engine (phase-10 probe): the three macros wrap duckdb_views() / duckdb_constraints() /
# duckdb_types(), so `pg_get_viewdef(<oid>)` returns the SQL of a view off the allowlist;
# `current_setting` returns absolute paths (`secret_directory` carries the OS user's home).
# `get_block_size` wraps pragma_database_size() (audit of the fix branch, LOW 2).
_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {"current_setting", "format_type", "get_block_size", "pg_get_constraintdef", "pg_get_viewdef"}
)


@dataclass
class ToolError(Exception):
    """A structured refusal or failure, safe to hand back to an agent verbatim."""

    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


def guard_select(sql: str) -> str:
    """Validate `sql` and return the statement to run, with `LIMIT 200` when absent."""
    emitted = _guard_once(sql)
    if _guard_once(emitted) != emitted:
        raise ToolError("parse_error", "the query does not survive regeneration unchanged")
    return emitted


def _guard_once(sql: str) -> str:
    if not sql or not sql.strip():
        raise ToolError("empty_query", "the query is empty")
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except SqlglotError as exc:
        raise ToolError("parse_error", f"the query does not parse: {_first_line(exc)}") from exc
    if len(statements) != 1:
        raise ToolError("multi_statement", "exactly one statement is allowed")
    statement = statements[0]
    if not isinstance(statement, exp.Select | exp.SetOperation):
        raise ToolError(
            "not_a_select",
            f"only SELECT queries are allowed, got {statement.key.upper()}",
        )
    if statement.find(exp.Into):
        raise ToolError("not_a_select", "SELECT ... INTO writes a table and is refused")

    for func in statement.find_all(exp.Func):
        name = func.name if isinstance(func, exp.Anonymous) else func.sql_name()
        if not name.isascii():
            raise ToolError(
                "function_not_allowed", f"non-ASCII function names are refused: {name!r}"
            )
        if name.lower() in _FORBIDDEN_FUNCTIONS:
            raise ToolError(
                "function_not_allowed", f"{name.lower()} reads the catalogue or settings"
            )

    _check_tables(statement)

    if statement.args.get("limit") is None:
        statement = statement.limit(MAX_ROWS)
    return statement.sql(dialect="duckdb")


def _check_tables(statement: exp.Expression) -> None:
    """Guard 4: each table is a mart, or a CTE visible from the scope it appears in."""
    checked: set[int] = set()
    for scope in traverse_scope(statement):
        visible_ctes = {_fold(name) for name in scope.cte_sources}
        for table in scope.tables:
            checked.add(id(table))
            _check_table(table, visible_ctes)
    # Fail closed: a table sqlglot attached to no scope is never assumed to be harmless.
    for table in statement.find_all(exp.Table):
        if id(table) not in checked:
            _check_table(table, visible_ctes=set())


def _check_table(table: exp.Table, visible_ctes: set[str]) -> None:
    if not isinstance(table.this, exp.Identifier):
        raise ToolError(
            "table_not_allowed",
            f"table functions are refused: {table.this.sql(dialect='duckdb')[:80]}",
        )
    name = _fold(table.name)
    schema = _fold(table.db)
    if table.catalog or schema not in ("", _DEFAULT_SCHEMA):
        raise ToolError("table_not_allowed", f"{table.sql(dialect='duckdb')} is not a mart")
    if schema == "" and name in visible_ctes:
        return
    if name not in MARTS_ALLOWLIST:
        allowed = ", ".join(sorted(MARTS_ALLOWLIST))
        raise ToolError("table_not_allowed", f"{name} is not on the allowlist ({allowed})")


def _fold(identifier: str) -> str:
    """Fold an identifier the way DuckDB does: ASCII only, and refuse anything else.

    Python's `str.lower()` is Unicode-aware: it maps U+212A KELVIN SIGN to ASCII `k`, which
    DuckDB does not. A CTE named with it "matched" a real table in the guard while DuckDB read
    the table (audit of the fix branch, HIGH 1). No mart or CTE needs a non-ASCII name.
    """
    if not identifier.isascii():
        raise ToolError("table_not_allowed", f"non-ASCII identifiers are refused: {identifier!r}")
    return identifier.lower()


def query_marts(
    sql: str, db_path: Path | None = None, timeout_s: float = TIMEOUT_S
) -> dict[str, Any]:
    """E.4 `query_marts`: one guarded SELECT on the marts, at most 200 rows."""
    safe_sql = guard_select(sql)
    try:
        with exposed(db_path, MARTS_ALLOWLIST) as con:
            columns, rows, truncated = run_select(con, safe_sql, MAX_ROWS, timeout_s)
    except WarehouseUnavailable as exc:
        raise ToolError("warehouse_unavailable", str(exc)) from exc
    except duckdb.InterruptException as exc:
        raise ToolError("timeout", f"the query exceeded {timeout_s:g} s") from exc
    except duckdb.Error as exc:
        raise ToolError("query_failed", _first_line(exc)) from exc
    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": [list(row) for row in rows],
        "row_count": len(rows),
        "truncated": truncated,
    }


def get_quality_report(db_path: Path | None = None) -> dict[str, Any]:
    """E.4 `get_quality_report`: the two quality marts, through the API's own service.

    Same numbers as `/v1/quality/summary` and `/v1/quality/coverage`, read through an exposure
    database holding the two quality marts only, instead of the API's fallback connection.
    """
    connect = partial(exposed, tables=_QUALITY_MARTS)
    service = QualityService(QualityRepository(db_path, connect=connect))
    try:
        summary = service.summary()
        coverage = service.coverage()
    except WarehouseUnavailable as exc:
        raise ToolError("warehouse_unavailable", str(exc)) from exc
    except duckdb.Error as exc:
        raise ToolError("query_failed", _first_line(exc)) from exc
    return {
        "summary": summary.model_dump(),
        "coverage": [row.model_dump() for row in coverage],
    }


def _first_line(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[0][:300] if text else type(exc).__name__
