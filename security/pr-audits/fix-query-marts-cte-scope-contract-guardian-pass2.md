> contract-guardian, pass 2 (before merge). Diff reviewed: `ff38132..95fe0c8` (cf9e15a, 2d2f008, 95fe0c8). Raw output, unedited. Agent definition: `.claude/agents/contract-guardian.md` as on origin/main @ 14319b0 (last changed in b88070f), unchanged on this branch.

---

**Verdict: APPROVED** for the delta `ff38132..HEAD`. I checked it against the branch `fix/query-marts-cte-scope` with `git branch --show-current`.

**Violations: none.**

**Scope of the delta.** Five files changed: `api/services/warehouse_tools.py`, `tests/unit/test_copilot_guards.py`, `docs/ROADMAP.md`, the ADR-012 doc and `mcp-server/README.md`. The diff does not touch `openapi.yaml`, `frontend/src/api/` or any `api/routers` or `api/schemas` file.

**Checks:**
- **HTTP contract and atomicity:** `openapi.yaml` is unchanged and no response shape changed, so the backend and the generated front client do not need to move together here.
- **E.3 shapes:** none of the endpoints are affected. RFC 7807 errors, the 422 "no valid session possible" error, `/v1` versioning and the SSE stream are all untouched.
- **Error codes:** there is no new code. A non-ASCII identifier is refused with the existing `table_not_allowed` code, and `get_block_size` is refused through the existing forbidden-functions path.
  - `ToolError` still reaches no HTTP endpoint. Grepping `api/`, `openapi.yaml` and `frontend/src/api/` finds no consumer of `warehouse_tools` or `table_not_allowed` besides the module itself (`api/repositories/readonly_warehouse.py` only mentions it in a docstring).
  - The only caller is the MCP adapter `mcp-server/cyclebeat_warehouse.py:45-55`. It catches `ToolError` and returns it as a structured error, so its shape is unchanged.
- **Layering and SQL placement:** `_fold` is pure string handling in the service layer, with no new imports and no FastAPI import. No SQL was written outside `api/repositories/` or `dbt/`. The only SQL added is DuckDB fixture DDL in the test file (`CREATE TABLE stg_tracks`), which the earlier pass already accepted for tests.
- **Tests:** they arrived before the fix (commit cf9e15a, "red before the fix"). They cover:
  - the U+212A (Kelvin sign) `stg_tracKs` CTE, quoted and unquoted;
  - `"dim_tracK"`;
  - `get_block_size`;
  - other ways of calling the forbidden functions (catalog/schema prefix, quoted name, mixed case, method-call form, inside a lambda, CASE or ORDER BY).

**Semantic risks (not blocking):**
1. `_fold` raises on any non-ASCII schema or table name, including the `table.db` part. That is fail-closed and matches the docstring's claim that "no mart or CTE needs a non-ASCII name". If a mart ever gets a non-ASCII name, the guard will refuse it. That is acceptable, but someone renaming a mart should know.
2. Column identifiers are not folded. That is out of scope for guard 4 and creates no contract impact.

**Commands run:**
- `git diff --stat ff38132..HEAD` and `git diff ff38132..HEAD -- api/ openapi.yaml frontend/src/api/ tests/`: only the files listed above.
- Parsing `openapi.yaml` with `yaml.safe_load`: "yaml ok".
- `from api.main import app`: imports fine.
- `uv run pytest tests/test_api_contract.py tests/unit/test_copilot_guards.py -q -p no:warnings`: exit 0, all tests passed with 1 xfail. That run includes the Schemathesis contract test against the app.
  - The xfail is the strict, AssertionError-only marker for CVE-2024-41672 at `/home/ellie/projets/cyclebeat/tests/unit/test_copilot_guards.py:398`. It was added in d18339e, inside the range you already approved, and this delta doesn't touch it. It documents the DuckDB upgrade item rather than hiding a failing test.

**Files:**
- `/home/ellie/projets/cyclebeat/api/services/warehouse_tools.py`
- `/home/ellie/projets/cyclebeat/tests/unit/test_copilot_guards.py`
- `/home/ellie/projets/cyclebeat/mcp-server/cyclebeat_warehouse.py`
