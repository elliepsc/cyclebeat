"""The MCP server over a real stdio session (criterion 12).

Starts `mcp-server/cyclebeat_warehouse.py` as a subprocess with the official client, the way
Claude Code does through `.mcp.json`, against a temp warehouse. It checks the wiring only --
the guards themselves are proven in `test_copilot_guards.py`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import duckdb
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "mcp-server" / "cyclebeat_warehouse.py"


@pytest.fixture()
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE dim_track AS SELECT i AS track_id FROM range(3) t(i)")
    return path


def _session(warehouse: Path, calls: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER)],
        env={**os.environ, "RUNTIME_DB_PATH": str(warehouse)},
    )

    async def run() -> dict[str, Any]:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            results = []
            for name, arguments in calls:
                result = await session.call_tool(name, arguments)
                results.append(json.loads(result.content[0].text))  # type: ignore[union-attr]
            return {"tools": tools, "results": results}

    return anyio.run(run)


def test_the_server_exposes_exactly_the_two_read_only_tools(warehouse: Path) -> None:
    out = _session(warehouse, [])
    assert sorted(tool.name for tool in out["tools"]) == ["get_quality_report", "query_marts"]
    for tool in out["tools"]:
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False


def test_a_select_is_answered_and_a_drop_is_refused_over_stdio(warehouse: Path) -> None:
    out = _session(
        warehouse,
        [
            ("query_marts", {"sql": "SELECT count(*) AS n FROM dim_track"}),
            ("query_marts", {"sql": "DROP TABLE dim_track"}),
        ],
    )
    ok, refused = out["results"]
    assert ok["rows"] == [[3]]
    assert refused == {
        "error": {"code": "not_a_select", "message": "only SELECT queries are allowed, got DROP"}
    }
    with duckdb.connect(str(warehouse), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM dim_track").fetchone() == (3,)
