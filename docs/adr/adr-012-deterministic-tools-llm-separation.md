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

The security audit of that fix branch, before merge, found the same class once more: the guard
folded names with Python's Unicode-aware `str.lower()`, which maps U+212A KELVIN SIGN to ASCII
`k`, while DuckDB folds ASCII only. A CTE named `stg_trac\u212as` was taken for `stg_tracks`
by the guard and DuckDB read the real table (reproduced end to end). Identifiers are now
folded ASCII-only and a non-ASCII table or CTE name is refused; `get_block_size` (a macro over
`pragma_database_size()`) joined the refused functions. Call shapes the locked engine executes
(schema-qualified, quoted, mixed case, method syntax, lambda, `CASE`, `ORDER BY`) are pinned as
refusals in `test_copilot_guards.py`.

The function list is a denylist measured on DuckDB 0.10.2's built-ins. A macro defined IN the
warehouse would run unchecked (the audit showed it with a probe macro); none exists today (no
`CREATE MACRO` in `dbt/`, `cyclebeat/`, `api/`, `dags/`), and the tools cannot create one.

The second pre-merge pass of the same audit found a third bypass of the same family. sqlglot
re-emits function names with Python's Unicode-aware `upper()`: `current_sett\u0131ng` (U+0131)
was unknown to the guard, then emitted as `CURRENT_SETTING`, and returned the OS user's home
through `query_marts` (reproduced end to end). The guard now refuses non-ASCII function names
and guards its own output again: what runs must be what was checked.

**Structural correction (owner decision, 13 October 2026).** Three bypasses in one phase had one
cause: the guard inferred from SQL text which tables would be read. The tools therefore no
longer run on the warehouse. `readonly_warehouse.exposed()` builds, per call, an in-memory
database holding COPIES of the allowed marts only (ATTACH the warehouse `READ_ONLY`, `CREATE
TABLE ... AS SELECT`, `DETACH`), sets the path settings to neutral values, caps memory, then
locks the engine as point 1 describes. A table off the allowlist does not exist where the SQL
runs, the catalogue functions find nothing to leak, and `current_setting` returns neutral
values; the SQL guard becomes the second line. Measured on a copy of the warehouse: 31.8 ms per
`query_marts` call, connection and copy included. `get_quality_report` runs on the same kind of
database, holding the two quality marts only.

Residual, engine side: on 0.10.2, `sniff_csv` still reads a file header on the locked
connection and on the exposure database (CVE-2024-41672); only the guard refuses it. Recorded
as two `xfail(strict=True)` tests and the first `[présentable]` roadmap line (DuckDB upgrade).

The third pre-merge pass showed how thin that line was (C1, reproduced, and present on
`origin/main` too): `JOIN LATERAL sniff_csv('<file>') ON true` is an `exp.Lateral`, not an
`exp.Table`, so the table check never saw it, and the first line of a file came back through
`query_marts`. The guard now allows only three FROM / JOIN source shapes (a named table, a
subquery, `VALUES`; `LATERAL` only over a subquery) and refuses everything else by default;
the names DuckDB knows only as table functions are read from the installed engine and refused
anywhere in the query. The same pass found that `warehouse_unavailable` carried DuckDB's lock
error (the file path, the lock holder's executable under the home directory, its PID; M1) and
that `ROWS FROM` crashed the guard (L1): the caller now gets one fixed message, the detail
goes to the server log, and any internal guard error is a structured refusal.

The fourth pass, limited to source shapes, table functions and M1, found no read. It found
an unreadable parent directory turning `Path.is_file()` into a `PermissionError` that carried
the absolute path out of both tools (NEW-L1), and scalar `range` / `generate_series` /
`repeat` allocating past the exposure database's memory limit (NEW-M1, 1666 MB RSS measured;
availability, not confidentiality). Both are fixed (fixed message and a last-resort
`internal_error`; the three builders refused); the process-level memory limit is the real fix
for NEW-M1 and is a `[présentable]` roadmap line. The audit loop stopped there by owner
decision: the tests of the last two fixes are their proof.

**The stop rule, as the owner applied it (15 October 2026).** A "read" outside the allowed
marts is what an agent obtains through the CONTENT of its query: another table, a file, a
setting of the machine. A failure that depends on the environment and reads no data (NEW-L1,
like M1) is a disclosure to fix, not a read; it does not trigger the switch to fixed,
parameterised tools that a further read would have triggered. The full triage of the four
passes is in `security/pr-audits/fix-query-marts-cte-scope-triage.md`.
