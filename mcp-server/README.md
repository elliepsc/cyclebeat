# mcp-server/ — `cyclebeat-warehouse` (criterion 12)

An MCP server (stdio) that gives a coding agent **read-only** access to the CycleBeat DuckDB
marts. It is the "MCP tool/server" element of the agent extension pack (`docs/agent-extension-pack.md`).

| Tool | What it returns | Guards |
|---|---|---|
| `query_marts(sql)` | columns and rows of ONE SELECT | one statement, SELECT/WITH/set operation only, tables limited to `dim_track`, `fct_session`, `mart_bpm_coverage`, `mart_data_quality` (E.4, restricted to the marts that exist), a CTE name valid only in its own scope, ASCII table, schema, CTE and function names only, no table functions or file paths, no catalogue or configuration functions (`pg_get_viewdef`, `current_setting`, ...), `LIMIT 200` injected and at most 200 rows fetched, 5 s timeout |
| `get_quality_report()` | the quality summary and BPM coverage, the same numbers as `/v1/quality/*` | read on an exposure database holding the two quality marts only |

Both tools are annotated `readOnlyHint: true`. Errors come back as
`{"error": {"code", "message"}}`, never a stack trace.

## Where the code is

This folder is the adapter only ([`cyclebeat_warehouse.py`](cyclebeat_warehouse.py)). The guards
are shared with the future phase-6 copilot, and the SQL stays where CLAUDE.md allows it:

- [`api/repositories/readonly_warehouse.py`](../api/repositories/readonly_warehouse.py):
  `exposed()`, where the tools' SQL runs since the phase-10 audit (ADR-012 note of 13 October
  2026). An in-memory database receives copies of the allowed marts only, path settings are
  neutralised, then external access goes off, extensions off, configuration locked. A table
  off the allowlist does not exist there. It never creates the warehouse file;
- [`api/services/warehouse_tools.py`](../api/services/warehouse_tools.py): the sqlglot guard,
  now the second line: allowlist checked per scope, LIMIT, timeout, structured errors, and the
  emitted SQL guarded again.

Tests: [`tests/unit/test_copilot_guards.py`](../tests/unit/test_copilot_guards.py) (guards and
injection refusals) and [`tests/unit/test_mcp_server.py`](../tests/unit/test_mcp_server.py) (a real
stdio session).

## Run it

```bash
make mcp-server
```

It waits for a client on stdin. Claude Code starts it through [`.mcp.json`](../.mcp.json) at the
repo root, and asks once for approval of a project-scoped server. The warehouse is the file named
by `RUNTIME_DB_PATH`, else `data/cyclebeat_runtime.duckdb`. To point an agent at a copy rather
than the real file, export `RUNTIME_DB_PATH` before starting Claude Code.

## In the plugin

`make plugin` copies this server's entry from `.mcp.json` into
`plugins/cyclebeat-agent-pack/.mcp.json`. It still runs the code of the CycleBeat checkout
(`${CLAUDE_PROJECT_DIR}`), so the plugin works inside a clone of this repo only. See
`docs/agent-extension-pack.md`.
