"""`cyclebeat-warehouse` -- MCP server (stdio) over the read-only warehouse tools.

A thin adapter: every guard lives in `api/services/warehouse_tools.py` and
`api/repositories/readonly_warehouse.py`, the same code the phase-6 copilot will call (one
implementation, two consumers, ADR-012). This file only declares the tools and turns a
`ToolError` into a structured result.

Run: `make mcp-server` (stdio; a client such as Claude Code starts it through `.mcp.json`).
The warehouse is the one `RUNTIME_DB_PATH` names, else `data/cyclebeat_runtime.duckdb`;
it is opened read-only and never created.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# `mcp-server/` is not a package (the hyphen is the grading layout), so the repo root goes on
# the path for `api.*`, exactly as pytest's `pythonpath = ["."]` does.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from api.services import warehouse_tools  # noqa: E402

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

server = FastMCP(
    "cyclebeat-warehouse",
    instructions=(
        "Read-only access to the CycleBeat DuckDB marts. query_marts runs ONE SELECT on "
        f"{', '.join(sorted(warehouse_tools.MARTS_ALLOWLIST))}; LIMIT "
        f"{warehouse_tools.MAX_ROWS} is injected and the timeout is "
        f"{warehouse_tools.TIMEOUT_S:g} s. Anything else is refused with a structured error."
    ),
)


@server.tool(annotations=READ_ONLY)
def query_marts(sql: str) -> dict[str, Any]:
    """Run one read-only SELECT on the marts allowlist (at most 200 rows, 5 s)."""
    try:
        return warehouse_tools.query_marts(sql)
    except warehouse_tools.ToolError as exc:
        return exc.as_dict()


@server.tool(annotations=READ_ONLY)
def get_quality_report() -> dict[str, Any]:
    """The data-quality summary and BPM coverage, as /v1/quality/* returns them."""
    try:
        return warehouse_tools.get_quality_report()
    except warehouse_tools.ToolError as exc:
        return exc.as_dict()


if __name__ == "__main__":
    server.run("stdio")
