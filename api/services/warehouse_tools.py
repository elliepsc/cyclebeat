"""Read-only warehouse tools for agents (E.4 `[rendu]` subset, ADR-012).

One implementation, two consumers: the MCP server in `mcp-server/` today, the phase-6 copilot
later. Everything here is deterministic -- no LLM decides what runs.

`query_marts` guards, in order (E.4):

1. parse with sqlglot (DuckDB dialect); a parse failure is a refusal, never a pass-through;
2. exactly one statement, and it must be a query (SELECT, WITH ... SELECT, set operations);
3. no `SELECT ... INTO`;
4. every table referenced is a CTE of the same query or a mart on `MARTS_ALLOWLIST`, in the
   default schema; table functions (`read_csv`, `glob`, ...) and file paths are refused;
5. `LIMIT 200` injected when absent, and at most 200 rows fetched whatever the LIMIT says;
6. 5 s timeout.

The engine side (read-only file, external access off, configuration locked) is in
`api/repositories/readonly_warehouse.py`. Errors come back as `ToolError` with a code and a
one-line message -- no stack trace reaches the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from api.repositories.quality import QualityRepository
from api.repositories.readonly_warehouse import WarehouseUnavailable, locked, run_select
from api.services.quality import QualityService

# E.4's allowlist, restricted to the marts that exist: `fct_llm_calls` and `fct_agent_runs`
# arrive with the phase-6 LLM layer and join the list then (owner decision, 2026-10-11).
MARTS_ALLOWLIST: frozenset[str] = frozenset(
    {"dim_track", "fct_session", "mart_bpm_coverage", "mart_data_quality"}
)
MAX_ROWS = 200
TIMEOUT_S = 5.0
_DEFAULT_SCHEMA = "main"


@dataclass
class ToolError(Exception):
    """A structured refusal or failure, safe to hand back to an agent verbatim."""

    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


def guard_select(sql: str) -> str:
    """Validate `sql` and return the statement to run, with `LIMIT 200` when absent."""
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

    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ToolError(
                "table_not_allowed",
                f"table functions are refused: {table.this.sql(dialect='duckdb')[:80]}",
            )
        name = table.name.lower()
        schema = table.db.lower()
        if table.catalog or schema not in ("", _DEFAULT_SCHEMA):
            raise ToolError("table_not_allowed", f"{table.sql(dialect='duckdb')} is not a mart")
        if schema == "" and name in cte_names:
            continue
        if name not in MARTS_ALLOWLIST:
            allowed = ", ".join(sorted(MARTS_ALLOWLIST))
            raise ToolError("table_not_allowed", f"{name} is not on the allowlist ({allowed})")

    if statement.args.get("limit") is None:
        statement = statement.limit(MAX_ROWS)
    return statement.sql(dialect="duckdb")


def query_marts(
    sql: str, db_path: Path | None = None, timeout_s: float = TIMEOUT_S
) -> dict[str, Any]:
    """E.4 `query_marts`: one guarded SELECT on the marts, at most 200 rows."""
    safe_sql = guard_select(sql)
    try:
        with locked(db_path) as con:
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

    Same numbers as `/v1/quality/summary` and `/v1/quality/coverage`, read through the locked
    connection instead of the API's fallback one.
    """
    service = QualityService(QualityRepository(db_path, connect=locked))
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
