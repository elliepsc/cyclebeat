> contract-guardian, pass 1 (before merge). Diff reviewed: `origin/main..ff38132` (d18339e, 4ac9ed8, ff38132). Raw output, unedited. Agent definition: `.claude/agents/contract-guardian.md` as on origin/main @ 14319b0 (last changed in b88070f), unchanged on this branch.

---

## contract-guardian verdict: APPROVED

I checked the diff against `origin/main` (fetched) on branch `fix/query-marts-cte-scope`, commits d18339e, 4ac9ed8 and ff38132. Five files change: `api/services/warehouse_tools.py`, `tests/unit/test_copilot_guards.py`, `docs/ROADMAP.md`, `docs/adr/adr-012-deterministic-tools-llm-separation.md` and `mcp-server/README.md`.

### Violations (blocking)
None.

### Contract checks
- **Atomicity (E.0.5):** `git diff --quiet origin/main..HEAD -- openapi.yaml frontend api/routers api/schemas api/repositories` exits 0. The diff doesn't touch the contract, the generated front client, any router, any schema or any repository, so no atomicity rule applies.
- **No change to HTTP response shapes:** `ToolError`, the existing `table_not_allowed` code and the new `function_not_allowed` code are only produced in `api/services/warehouse_tools.py`. No router imports this module: `api/routers/sessions.py` imports only `SessionService` and `api/routers/quality.py` imports only `QualityService`. Nothing under `frontend/src` references it either.
- **The new error code only reaches the MCP tools:** its single consumer is `mcp-server/cyclebeat_warehouse.py:42-47`, which turns `ToolError` into `exc.as_dict()` as a tool result. That is not an HTTP response, so the RFC 7807 rule doesn't apply. The tool's output shape is unchanged (`code` plus `message`). Only one more possible value for `code` is added, and that is an additive change.
- **E.3 shapes:** nothing affected. `openapi.yaml` (3.1.0, 7 paths) parses. Its header comment (`openapi.yaml:16-20`) still records that `/v1/copilot/ask` and the other copilot endpoints are deliberately absent until phase 6.
- **Layering and "SQL only in `api/repositories/` and `dbt/`":** consistent. The service adds no SQL text. It only inspects the parsed sqlglot tree (`traverse_scope`, `scope.cte_sources`, `scope.tables`, `exp.Func`). It still runs queries through `api/repositories/readonly_warehouse.py` (`locked`, `run_select`), and that file is unchanged. No FastAPI import was added. The SQL strings in `tests/unit/test_copilot_guards.py` are test fixtures, as in earlier phases.

### Semantic risks (not blocking, for the owner)
1. **The contract becomes exposed in phase 6.** When `/v1/copilot/ask` is added, the copilot will call these tools and may report a refusal over HTTP or SSE. At that point `openapi.yaml` must list the tool error codes, including `function_not_allowed`, either as an enum or a documented set. It must also say whether a refusal is a step/token event in the SSE stream or an RFC 7807 error. Otherwise the code will be a silent addition to the contract. It's best noted now so phase 6 writes it into the contract before the backend.
2. **Refusing functions by name is a denylist, so the list is incomplete by nature.** It is measured on DuckDB 0.10.2 and tracked in the ROADMAP line. This matters for security rather than the contract; `security-auditor` should look at it. One example: whether other `pg_*` or `duckdb_*` scalar macros that read the catalogue (for instance `pg_get_expr`, `obj_description`, `col_description` or `has_*_privilege`) also run on the locked engine was not probed, as far as the diff shows.
3. **The strictly expected failure is tied to a ticket.** `test_the_locked_connection_refuses_sniff_csv` is marked `xfail(strict=True, raises=AssertionError)`, and its reason points to the ROADMAP "DuckDB upgrade" line. That meets CLAUDE.md's rule of "no xfail without a ticket". The guard-side refusal of `sniff_csv` is covered by a test that passes, so the guard is not bypassed.

### Commands run and results
- `git branch --show-current`: `fix/query-marts-cte-scope`. `git fetch origin` was run, and the diff base is `origin/main`.
- Parsing `openapi.yaml` with `yaml.safe_load`: OK (openapi 3.1.0, 7 paths).
- `uv run pytest tests/test_api_contract.py tests/unit/test_copilot_guards.py tests/unit/test_mcp_server.py -q -p no:warnings`: exit 0, 121 passed and 1 xfailed (the strict `sniff_csv` test above).
- `uv run pytest tests/test_api_contract.py -q` (what `make contract` runs): exit 0, checked with `PIPESTATUS`.
- `uv run mypy api`: "Success: no issues found in 21 source files", exit 0.
- `uv run ruff check api tests mcp-server`: "All checks passed!", exit 0.
- I didn't run the full `make test-unit`, `make lint` (including `check_links`), `eval` or `dbt`, so they still need running before merge.

Relevant files:
- /home/ellie/projets/cyclebeat/api/services/warehouse_tools.py
- /home/ellie/projets/cyclebeat/mcp-server/cyclebeat_warehouse.py
- /home/ellie/projets/cyclebeat/openapi.yaml
- /home/ellie/projets/cyclebeat/tests/unit/test_copilot_guards.py
- /home/ellie/projets/cyclebeat/docs/adr/adr-012-deterministic-tools-llm-separation.md
