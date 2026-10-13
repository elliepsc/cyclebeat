# ADR-012 — Deterministic warehouse tools first, the LLM layer on top

- **Status**: Accepted
- **Date**: 2026-10-11
- **Owner**: Ellie

## Context

Appendix E.4 of `docs/archive/CYCLEBEAT_PLAN_V3.md` specifies the Warehouse Copilot as one
block: tool signatures (`query_marts`, `get_quality_report`, `explain_track`,
`list_review_queue`, `trigger_resolve`), run caps that only make sense with an LLM loop (6 tool
calls, 500-character question, 60 s, LiteLLM budget), and nine guard tests to ship in the same
commit as the tools.

The roadmap split phase 6 into a `[rendu]` part with no LLM and a `[présentable]` LLM layer, and
recorded the owner's decision of 9 October 2026 (ROADMAP, "Décisions et points ouverts" 1): the
six guard tests that need no LLM ship with the tools, the three that need the agent loop or
`trigger_resolve` ship with the LLM layer, and this change to the E.4 contract is formalized by
an ADR. Criterion 12 (phase 7) needs those tools now, behind an MCP server; the LLM layer stays
out of the submission scope.

## Decision

1. **The tools are a deterministic library, with no LLM anywhere in their path.** No model
   decides what runs: a parser and an engine configuration do.
   - `api/services/warehouse_tools.py`: the SQL guard (sqlglot, DuckDB dialect): one statement;
     SELECT, `WITH ... SELECT` or a set operation only; no `SELECT ... INTO`; every table a CTE of
     the query or a mart on the allowlist, in the default schema; table functions and file paths
     refused; `LIMIT 200` injected when absent and at most 200 rows fetched; 5 s timeout;
     structured errors without stack.
   - `api/repositories/readonly_warehouse.py`: the connection, `read_only=True`, external access
     off, extension auto-install and auto-load off, configuration locked; it never falls back to a
     writable handle and never creates the file.
   Both layers are needed: a locked DuckDB 0.10.2 still runs `PRAGMA` statements (measured), and
   the SQL guard alone would trust a parser.
2. **One implementation, two consumers.** The MCP server (`mcp-server/`) calls this library
   today; the phase-6 copilot will call the same functions. The LLM layer adds planning, the run
   caps and the budget around the tools; it does not get its own path to the warehouse.
3. **Scope of this phase**: `query_marts` and `get_quality_report` (which reuses the API's
   `QualityService` through the locked connection). `list_review_queue` was cut by the owner on
   2026-10-11; `explain_track` and `trigger_resolve` come with the LLM layer.
4. **Allowlist**: E.4's list restricted to the marts that exist — `dim_track`, `fct_session`,
   `mart_bpm_coverage`, `mart_data_quality`. `fct_llm_calls` and `fct_agent_runs` join it when the
   LLM layer creates them. Adding any other mart changes E.4 and needs an ADR.
5. **The nine E.4 tests.** In `tests/unit/test_copilot_guards.py` now, under their E.4 names:
   `test_rejects_multi_statement`, `test_rejects_non_select`, `test_rejects_table_outside_allowlist`,
   `test_limit_injected_when_absent`, and two adapted to SQL (no natural-language question exists
   without the LLM): `test_rejects_prompt_injection_drop` (a `DROP TABLE` statement is refused and
   the table is intact) and `test_legit_question_with_delete_word_passes` (a SELECT containing the
   word "delete" is not blocked). With the LLM layer: `test_max_tool_calls_cap`,
   `test_trigger_resolve_requires_confirm`, `test_trigger_resolve_caps_track_list`.

## Consequences

- The guards are tested without a model, an API key or a network: 65 tests in
  `test_copilot_guards.py`, including 39 injection refusals and engine-level tests that bypass the
  SQL guard on purpose.
- The LLM layer cannot widen what the tools can do; it can only call them. A prompt injection
  that convinces the model still meets the same parser and the same locked connection.
- E.4 is amended in three places (test split, two tests adapted, allowlist restricted); the
  archived plan is not edited, this ADR is the record.
- `sqlglot` becomes a runtime dependency (`api/`), and the MCP SDK a dev one (`mcp-server/` is a
  developer tool, kept out of the API image).

## Note, 13 October 2026 — what the phase-10 audit found in the guard

Decision point 1 said "every table a CTE of the query or a mart on the allowlist". As built in
PR #38, that was not enforced: CTE names were collected from the whole statement, so a CTE
defined in any subquery whitelisted its name everywhere, and an outer `FROM` of that name read
the real table. The phase-10 audit of PR #38 found it (finding H1) and it was reproduced in five
shapes on a temporary warehouse (derived table, scalar subquery, set-operation branch, sibling
CTE, `EXISTS`): a table off the allowlist was returned. The locked connection was never the
issue (still read-only, no disk); the allowlist was.

Fixed on `fix/query-marts-cte-scope`: tables are checked per sqlglot scope, against the CTEs
visible from that scope only, and a table no scope accounts for is refused. The same probe
found scalar calls the table-function check cannot see, which DuckDB 0.10.2 runs on the locked
engine: `pg_get_viewdef` (returned the SQL of a view off the allowlist), `pg_get_constraintdef`,
`format_type` (macros over the `duckdb_*` catalogue functions) and `current_setting` (absolute
paths, the OS user's home). They are refused by name (`function_not_allowed`).

Residual, engine side: on 0.10.2 the locked connection itself still lets `sniff_csv` read a
file header (CVE-2024-41672); only the guard refuses it. Recorded as an `xfail(strict=True)`
test and a `[présentable]` roadmap line (DuckDB upgrade). The two layers of point 1 are
therefore not independent on this version: each covers a hole of the other.
