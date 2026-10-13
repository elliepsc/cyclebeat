> security-auditor, pass 3 (before merge). Diff reviewed: `95fe0c8..85f4d56` (263ccb9, fa1f5a6, 2980b7f, 85f4d56). Raw output, unedited. Agent new definition: `.claude/agents/security-auditor.md` @ 263ccb9 (a8d9830 ported onto this branch); its first line, cited by the auditor: "You audit and RETURN a report as your final message."

---

First sentence of my instructions body: "You audit and RETURN a report as your final message." Tools I was given: Read, Bash, SubagentHandback.

# Security audit, pass 3: fix/query-marts-cte-scope (HEAD 85f4d56, diff 95fe0c8..HEAD)

Reference: branch `fix/query-marts-cte-scope` (`git branch --show-current`), working tree clean, checked against the branch HEAD. Scope: the exposure database (`exposed()`), the guard (ASCII function names, fixed point), and the path that reaches `query_marts`. Passes 1 and 3 (gitleaks/Semgrep/deps) were not asked for in this pre-merge pass and were not re-run.

## Executive summary
- **Overall risk: Critical. This branch should not be merged as is.**
- On its own, without the guard, the exposure database does what it claims. No source table, view, macro, sequence, schema, path, secret or setting could be reached, and no write survived the call. The one exception is the known `sniff_csv` CVE.
- But the guard, which is now said to be the only thing standing in front of that CVE, can be bypassed: `SELECT * FROM dim_track JOIN LATERAL sniff_csv('/etc/hostname') ON true` passes `guard_select` and returns the file's first line through `query_marts`. That line was the machine's hostname, `PCEllie`.
- **Action #1:** in `_check_tables`, refuse every FROM/JOIN source that is not a plain `exp.Table` or a subquery (in particular `exp.Lateral` that wraps a function), and add a test for it. Then plan the DuckDB upgrade (>= 1.1) that fixes CVE-2024-41672.

## Tests
`uv run pytest tests/unit/test_copilot_guards.py tests/unit/test_exposure_warehouse.py` -> `137 passed, 2 xfailed in 4.32s`, exit 0. The 2 xfails are the two strict `sniff_csv` CVE markers.

E.4 status:
- The 6 tests that need no LLM are present and green.
- The other 3 (6 tool-call cap, `confirm=true` on `trigger_resolve`, 10-track cap) are pending, phase 6. That is expected.

## Findings

### CRITICAL C1: guard bypass through `LATERAL`, arbitrary file read via `sniff_csv` (reachable through `query_marts` and the MCP server)
- **What:** a table function written as `JOIN LATERAL <fn>(...)` (also as `, LATERAL` or `CROSS JOIN LATERAL`, by construction) is never checked.
  - sqlglot parses it as an `exp.Lateral` node, not an `exp.Table`.
  - `_check_tables`, including its fail-closed sweep, only looks at `exp.Table` nodes.
  - `sniff_csv` is not in `_FORBIDDEN_FUNCTIONS`.
  - On DuckDB 0.10.2, `sniff_csv` ignores `enable_external_access=false` (CVE-2024-41672).
- **Where:**
  - `api/services/warehouse_tools.py:125-136`: `for table in statement.find_all(exp.Table)` is the only sweep.
  - `api/services/warehouse_tools.py:65-67`: the denylist has no table-function names.
- **Evidence** (my probe, temp warehouse in the scratchpad, through `query_marts`):
  ```
  ACCEPTED "SELECT * FROM dim_track JOIN LATERAL sniff_csv('/etc/hostname') ON true"
           emitted="SELECT * FROM dim_track JOIN LATERAL SNIFF_CSV('/etc/hostname') ON TRUE LIMIT 200"
           -> [[0, 'T0', ..., "{'PCEllie': 'VARCHAR'}"
  ```
  The same `sniff_csv` call without `LATERAL` is refused (`table_not_allowed`).
- **Impact:**
  - At minimum, the first line of any file the API/MCP process can read reaches the agent.
  - The threat model is a prompt injection planted in `dim_track.title`/`artist` (external Deezer/CSV data) that steers the agent into this query.
  - Files whose first line is a secret (a `KEY=value` file such as the repo's own `.env`) are directly at risk. I did not test this against any real secrets file.
  - How far the read goes beyond the first line was not measured: see "Unable to verify".
- **Documentation is now false on this point:**
  - `api/repositories/readonly_warehouse.py:23-24` says "only the guard refuses it".
  - The reasons of both xfail markers say "The SQL guard refuses it".
- **Fix:**
  1. In `_check_tables`, walk every source of every FROM/JOIN and allow only `exp.Table` with an `Identifier`, `exp.Subquery`, `exp.Values`, or `exp.Unnest` over a non-function argument. Refuse `exp.Lateral` unless its `this` is a subquery.
  2. Add every DuckDB table-function name (`sniff_csv`, `read_*`, `glob`, `duckdb_*`, `pragma_*`, `query`, `query_table`, ...) to the check that runs on any `exp.Func`, so they are refused wherever they appear.
  3. Better long term: an allowlist of scalar functions instead of a denylist.
  4. Add the LATERAL variants to `test_injection_is_refused`.
  5. Schedule the DuckDB >= 1.1 upgrade; the xfail will flip.
- **Effort:** S (half a day with tests). The upgrade is M.
- **Pre-existing?** Most likely: the diff did not touch `_check_tables`. But I did not run it on `origin/main`.

### MEDIUM M1: absolute paths, the lock holder's executable and its PID reach the agent in `warehouse_unavailable`
- **Where:**
  - `api/repositories/readonly_warehouse.py:110`: `raise WarehouseUnavailable(f"cannot expose the warehouse: {exc}")`. Line 70 does the same in `locked()`.
  - It is passed on verbatim by `api/services/warehouse_tools.py:177` and `:203` (not even trimmed by `_first_line`).
  - The MCP server returns it as is: `mcp-server/cyclebeat_warehouse.py:46-47, 55-56` (`exc.as_dict()`).
- **Evidence** (a second process holds the write lock, which is what happens during `make dbt` or Airflow `load_duckdb`):
  ```
  warehouse_unavailable | 'cannot expose the warehouse: IO Error: Could not set lock on file "/tmp/claude-1000/.../p3/locked.duckdb": Conflicting lock is held in /home/ellie/.local/share/uv/python/cpython-3.11.9-linux-x86_64-gnu/bin/python3.11 (PID 291147). ...'
  ```
  A SQLite file at `RUNTIME_DB_PATH` likewise produces `/home/ellie/.duckdb/extensions/...`.
- **Impact:** this is exactly the data class (the OS user's home path) that `NEUTRAL_SETTINGS` was added to hide. No bypass is needed; only timing.
- **Fix:** return a fixed message to the caller ("warehouse locked by a writer or unreadable; retry after `make dbt`") and log the detail server-side.
- **Effort:** XS. Quick win.

### LOW L1: `ROWS FROM (...)` crashes the guard with an uncaught `AttributeError`
- **Where:** `api/services/warehouse_tools.py:143`. `table.this.sql(...)` is called when `table.this` is `None`.
- **Evidence:** `CRASH AttributeError "SELECT * FROM ROWS FROM (sniff_csv('/etc/hostname'))" 'NoneType' object has no attribute 'sql'`
- **Impact:** the query is not executed (it fails closed). But it breaks the "errors come back as `ToolError`, no stack trace" contract stated at lines 29-30.
- **Fix:** handle `table.this is None` and turn any other exception inside `guard_select` into a `ToolError`.
- **Effort:** XS. Quick win.

### LOW L2: `USING SAMPLE` is broken by the LIMIT injection (functional false failure)
- **Evidence:** `SELECT * FROM dim_track USING SAMPLE 5 ROWS` is emitted as `... LIMIT 200 USING SAMPLE RESERVOIR (5 ROWS)`, and DuckDB answers `Parser Error: syntax error at or near "USING"`.
- **Cause:** the LIMIT injection, not the fixed-point check.
- **Fix:** document the limitation, or wrap the query (`SELECT * FROM (<q>) LIMIT 200`).
- **Effort:** S.

### LOW L3: `locked()` no longer has a production caller, and the module docstring still presents it as the tools' connection
- **Where:** `api/repositories/readonly_warehouse.py:1-16`, `:61-74`. Grep shows the only users are in tests.
- **Fix:** keep it (it backs the old tests) but say so in the docstring, or remove it with its tests.
- **Effort:** XS.

### INFO (no action required, recorded for the triage)
- **Facts still visible on the exposure database without the guard:** `TimeZone=Europe/Paris`, `threads=24`, `pragma_platform()` = `linux_amd64_gcc4`, `version()` = v0.10.2, `duckdb_api=python`. Through the guard, `current_setting` and the `duckdb_settings()` table function are refused. The LATERAL form was not tested (see Unable to verify).
- **ENUM labels:** a mart column of ENUM type carries all of its labels into the copy (`enum_range(m)` returned `['SECRET_ENUM_A','calm']`). The marts are dbt `table` models (`dbt/dbt_project.yml:22`, the `config(materialized='table')` lines), and none is known to use an ENUM.
- **Hardening:** `exposed()` copies the marts while external access is still ON (it has to be, for ATTACH). If a mart ever became a view, its SQL would run unlocked. Filtering `table_type = 'BASE TABLE'` in the `information_schema` query (`readonly_warehouse.py:101-103`) would close that.
- **Limits not covered:** building the exposure database is outside the 5 s timer, and `memory_limit` is set after the copy. Negligible on the demo warehouse; to watch if the marts grow.

## Verified and holding (with evidence)
**Direct probe on `exposed()`, guard off, temp warehouse that also held a secret table, view, macro, sequence, `raw` schema, ENUM type and a CHECK constraint:**
- Nothing off the allowlist is reachable:
  - `duckdb_databases()` shows only memory/system/temp, all with `path` NULL.
  - `duckdb_tables()` shows only the copied marts.
  - `duckdb_views/sequences/constraints/indexes/dependencies/types/secrets()` are empty.
  - `pg_catalog`/`information_schema` show only the marts.
  - `source.*`, `temp.main.*`, `system.main.*`, the macro, the sequence, the type and `raw.t` all fail with Catalog/Binder errors.
- **Settings:** across all 75 settings, the only path-like values are `/nonexistent` (home/secret). `extension_directory`, `temp_directory` and `profile_output` are empty, and `log_query_path` is NULL. `getenv` does not exist. `duckdb_extensions()` errors out because home is `/nonexistent`.
- **Locked configuration:** SET/RESET/PRAGMA of external access, lock_configuration, memory, threads, temp_directory, profiling output and log_query_path are all refused ("configuration has been locked").
- **Engine refuses file and extension access:**
  - `COPY TO` and `EXPORT DATABASE` are refused.
  - On-disk ATTACH (including the warehouse itself, `:memory:name`, `sqlite:`, `md:`) is refused.
  - INSTALL fails and LOAD of external extensions is refused.
  - `read_csv/json/text/blob`, `glob`, `parquet_metadata` and replacement scans are refused.
  - `CREATE [PERSISTENT] SECRET` fails (no s3 type).
  - No file appeared in the probe directory.
  - The only exception is `sniff_csv` (known CVE).
- **No persistence or sharing between calls:** a table created and a `DELETE` in one connection are not seen by a concurrent or a following one. `ATTACH ':memory:'` is allowed but private to its connection.
- **ATTACH path from `RUNTIME_DB_PATH` and the is_file/ATTACH window** (TOCTOU) all fail closed:
  - A file removed after `is_file()` gives `Cannot open database` and is not created.
  - A text file is refused.
  - A directory is refused by `is_file`.
  - A SQLite file fails (autoload off).
  - A quote in the path is escaped correctly.
  - A symlink is followed. This is operator-controlled and accepted.
- **Fixed point and ASCII rule:**
  - No false refusal on 63 legitimate analyst queries: window/QUALIFY, FILTER, GROUP/ORDER BY ALL, EXCLUDE, COLUMNS, lambdas, structs/lists, recursive CTE, set operations, `FROM`-first, comments, non-ASCII strings. Results matched a direct read-only run, except L2.
  - The comment-nesting, dollar-quote, `E''` and `U&''` differentials did not get `current_setting` through: sqlglot neutralises nested comment markers and the re-check holds.
  - All the `current_setting` call forms (quoted, schema-qualified, method form, inside lambdas, LATERAL subquery, REPLACE) are refused.

## Unable to verify
- **How far the C1 file read goes beyond the first line:** not measured. My attempt to measure it, on a fake file in the scratchpad, was stopped by a safety classifier. Per the rules I stopped there and did not retry. That interrupted call may have created a file of fake values, `/tmp/claude-1000/-home-ellie-projets-cyclebeat/a9cbe024-f471-4889-870b-6b7972d6a184/scratchpad/p5/fake.env`, outside the repo. Treat C1 as "at least the first line of any readable file".
- **Other table functions through the same LATERAL form** (`duckdb_settings()`, `pragma_*`, `duckdb_extensions()`): not run. Given the direct probe, they would expose at most the INFO-level facts above.
- **`(SUMMARIZE <query>)` / `(DESCRIBE <query>)`** as carriers of a table function: not tested. `(SUMMARIZE dim_track)` and `(DESCRIBE dim_track)` are accepted and harmless.
- **Whether C1 is reproducible on `origin/main`:** not run.
- **`.env` history:** owner action, the owner's result is "no line". I did not run or read it.

## Prioritised action plan
1. **C1, blocking before merge:** close the `exp.Lateral`/function-in-FROM path, add the table-function names to the any-`Func` check, add LATERAL tests, and correct the docstring and xfail wording. Effort S.
2. **M1, quick win:** use a fixed `warehouse_unavailable` message and log the detail server-side. Effort XS.
3. **L1, quick win:** handle `table.this is None` and catch any exception inside the guard as a `ToolError`. Effort XS.
4. **DuckDB >= 1.1 upgrade** for CVE-2024-41672 (existing ROADMAP line), on its own branch. Effort M.
5. **L2, L3 and the BASE TABLE filter.** Effort XS-S.

No repo file was written. Probes ran only on temporary DuckDB files under the session scratchpad: `/tmp/claude-1000/-home-ellie-projets-cyclebeat/a9cbe024-f471-4889-870b-6b7972d6a184/scratchpad/`.
