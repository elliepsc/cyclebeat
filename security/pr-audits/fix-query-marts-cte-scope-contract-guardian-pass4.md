> contract-guardian, pass 4 (before merge). Diff reviewed: `85f4d56..feae0a7`, code commits 6b102b2, f7d651d, 7d91646, feae0a7 (84025c5 and bd7d386, raw review files, skipped). Raw output, unedited. Agent definition: `.claude/agents/contract-guardian.md` as on origin/main @ 14319b0 (last changed in b88070f), unchanged on this branch.

---

## contract-guardian, pass 4: verdict APPROVED

I checked everything against the branch `fix/query-marts-cte-scope` (HEAD `feae0a7`), using the delta `git diff 85f4d56..HEAD`. I left out `security/pr-audits/` and the docs-only commits 84025c5 and bd7d386. The code commits I reviewed are 6b102b2, f7d651d, 7d91646 and feae0a7. Only four files change: `api/repositories/readonly_warehouse.py`, `api/services/warehouse_tools.py`, `tests/unit/test_copilot_guards.py` and `tests/unit/test_exposure_warehouse.py`.

### Violations
None blocking.

### Answers to your checks
- **HTTP contract and generated client:** neither changed. `git diff --stat 85f4d56..HEAD -- openapi.yaml frontend/ api/routers api/schemas` is empty, so the atomicity rule (E.0.5) doesn't apply.
- **E.3 shapes:** not affected. No route, schema, RFC 7807 handler (`api/errors.py`) or SSE code changed. `openapi.yaml` still parses.
- **Layering:**
  - The new `duckdb_functions()` SQL (`table_function_names()`) and the `table_type = 'BASE TABLE'` filter in `exposed()` are both in `api/repositories/readonly_warehouse.py`, which is allowed.
  - `api/services/warehouse_tools.py` has no new SQL. It only builds sqlglot ASTs and calls the repository.
  - `table_function_names()` opens a `:memory:` connection with autoload/autoinstall off, so it never touches the real warehouse.
  - FastAPI is only imported in `api/` and `tests/`. The delta adds no FastAPI import.
- **HTTP endpoint behaviour:** unchanged.
  - Neither `api/repositories/quality.py` nor `api/repositories/warehouse.py` is in the delta. `QualityRepository.__init__` still defaults to `connect=readable` (`api/repositories/quality.py:25`), so `/v1/quality/*` keeps its fallback connection.
  - Only `get_quality_report` swaps in `partial(exposed, tables=_QUALITY_MARTS)`.
  - `exposed()` and `locked()` changed (fixed message, `_is_file`, BASE TABLE copy), but no router calls either of them.
- **New ToolError codes (`guard_error`, `internal_error`):** they can't reach any HTTP endpoint. Nothing in `api/routers` or `api/main.py` imports `warehouse_tools` or `readonly_warehouse`. The only consumer is `mcp-server/cyclebeat_warehouse.py:43-55`, which turns every `ToolError` into `exc.as_dict()`, so the new codes pass through as structured MCP results with no code change.
  - The fallback that catches any other exception sits after the specific `except` clauses, and `guard_select` runs outside the `try` in `query_marts`. So a guard refusal keeps its own code and is not hidden as `internal_error`.

### Semantic risks (none blocking)
1. **Codes aren't in the contract yet.** When the phase-6 copilot exposes these tools over HTTP/SSE, `openapi.yaml` will have to list `guard_error`, `internal_error` and `warehouse_unavailable` (whose message is now fixed), and say whether a refusal is an SSE event or an RFC 7807 error. This is already tracked in `docs/ROADMAP.md:61`, so no action is needed in this PR.
2. **A refusal code is a breaking change for MCP clients.** `range`, `generate_series` and `repeat` are now refused even as scalars (`function_not_allowed`), so a query that used to work now gets a refusal. This only affects the MCP tool surface, not the HTTP contract, and ADR-012 (around lines 122-132) documents it with the measured reason. Acceptable.
3. **`table_function_names()` is cached with `@cache` and depends on the DuckDB version.** If the build query itself fails, `guard_select`'s broad `except` turns that into `guard_error` (refused), which fails safe.

### Commands run
- `git diff --stat 85f4d56..HEAD -- openapi.yaml frontend/ api/routers api/schemas`: empty.
- `python3 -c "import yaml; yaml.safe_load(open('openapi.yaml'))"`: yaml ok.
- `uv run pytest tests/test_api_contract.py -q` (the `make contract` target): 25 passed, exit 0.
- `uv run pytest tests/unit -q -k "quality or exposure or copilot or warehouse or mcp" -rx`: all passed, plus 2 xfails, both with a ROADMAP ticket and both from before this delta:
  - `test_the_locked_connection_refuses_sniff_csv`
  - `test_the_exposure_database_refuses_sniff_csv` (CVE-2024-41672)
  - The delta adds no xfail or skip.
- `uv run ruff check api tests/unit/test_copilot_guards.py tests/unit/test_exposure_warehouse.py`: all checks passed.
- `uv run mypy api`: no issues in 21 source files.
- Grep for FastAPI imports outside `api/` and `tests/`: none.

I did not read `.env`, call any MCP tool, or modify any file.
