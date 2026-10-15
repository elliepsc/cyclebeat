> security-auditor, pass 4 (before merge), scope limited by the owner to FROM/JOIN source shapes, table functions and M1. Diff reviewed: `85f4d56..f7d651d` (6b102b2, f7d651d; 84025c5 skipped). Raw output, unedited. Agent new definition: `.claude/agents/security-auditor.md` @ 263ccb9; its first line, cited by the auditor: "You audit and RETURN a report as your final message." Two earlier launches of this pass were cut off by a machine shutdown and returned nothing; this is the third launch, the first to finish.

---

"You audit and RETURN a report as your final message." Tools I was given: Read, Bash, SubagentHandback.

# Security audit, pass 4 (scope limited to three topics): branch `fix/query-marts-cte-scope`

Reference: `git branch --show-current` returned `fix/query-marts-cte-scope`. I reviewed `git diff 85f4d56..HEAD` for `api/` and the tests, and skipped the raw review files from 84025c5. Engine versions: DuckDB 0.10.2, sqlglot 30.18.0, Python 3.11.9. Every probe ran on files under `/tmp/claude-1000/.../scratchpad/`: a warehouse `wh.duckdb` holding the 4 marts plus a `secret_tbl` decoy, and a harmless `probe.csv` with content `col_a,col_b\nhello,1`. I called no MCP tool and wrote no file in the repo (`git status --short` is empty).

## Executive summary
- **Overall risk: Low.** I could not get any FROM/JOIN source or table function past the guard, and C1 and L1 are closed.
- **Reads:** neither `query_marts` nor `get_quality_report` can read anything outside the copied marts, as far as I measured.
- **Two new findings, neither is a read:**
  - **Medium:** the scalar `range`/`generate_series`, which are exempt from the name list, go past the 512 MB `memory_limit` and can kill the server process.
  - **Low:** M1 has one remaining path. A `PermissionError` that is not caught returns the absolute warehouse path through the MCP error text.
- **Action #1:** cap or refuse very large scalar `range`/`generate_series`/`repeat` calls, or put an OS memory limit on the tool process.

Tests: `uv run pytest tests/unit/test_copilot_guards.py tests/unit/test_exposure_warehouse.py -q` exited 0. From the progress lines, 82 passed and 2 were strict xfails. Both xfails are the known, ticketed sniff_csv CVE-2024-41672 tests (`test_the_locked_connection_refuses_sniff_csv`, `test_the_exposure_database_refuses_sniff_csv`).

## Topic 1: FROM / JOIN source shapes. No bypass found

I sent 70+ shapes through `guard_select` and, when the guard passed one, through `query_marts` on the temporary warehouse. Each attack used `sniff_csv('<probe.csv>')` as the payload. Every one was refused:
- **Join kinds:** comma join; JOIN LATERAL; `, LATERAL`; CROSS JOIN LATERAL (subquery); LEFT, POSITIONAL, ASOF, NATURAL, SEMI and ANTI joins.
- **FROM-first:** `from X` and `from dim_track, X`.
- **Parentheses:** parenthesised join, double parentheses, `(X) as x`, nested join inside a join.
- **Inside other queries:** CTE body, UNION branch, EXISTS subquery, scalar subquery.
- **Name variants:** quoted `"sniff_csv"(...)`, `main.` and `system.main.` qualified, upper-case.
- **Statement wrappers:** subqueries over PIVOT, UNPIVOT, SUMMARIZE, DESCRIBE and SHOW.
- **Other sources:**
  - `ROWS FROM (...)` is now a clean `table_not_allowed`, so L1 is closed.
  - `from [1,2]` and `from {'a':1}` fail with a parse error.
  - A string-literal source with a file path is refused (`_check_table`).
  - `unnest`, `range`, `generate_series`, `json_each`, `repeat_row`, `test_all_types`, `getvariable`, `query`, `read_csv_auto` and `parquet_scan` in FROM are refused (got Table/Unnest).
  - A bare `from sniff_csv` or `from duckdb_tables` is refused (not on the allowlist).

What the guard lets through is only allowed tables, `(subquery)`, `LATERAL (subquery)`, `VALUES` and `PIVOT (...)` on a mart. All of these ran on the copies only.

**Comment differential:** I sent `select 1 -- */ , (select columns from sniff_csv(...)) /*`. sqlglot re-emits the comment with `*/` turned into `* /`, so DuckDB returned `[[1]]` and nothing from the file. The nested-comment variants fail with a parse error.

**Exposure check:** if the guard were bypassed, `from 'dim_track'` and `from secret_tbl` would still not reach other tables. `secret_tbl` gives `Catalog Error: Table with name secret_tbl does not exist!` on the exposure database.

**Usability note, not security:** some harmless shapes are refused. `select * from (dim_track join fct_session on true)` gives "got Subquery". `select * from table dim_track` is read as a table named `table`.

## Topic 2: table functions. No path missed by the name list or the source check

- **The list:** `table_function_names()` on 0.10.2 returns 67 names:
  - all the `read_*` functions, `sniff_csv`, `glob`, `parquet_*` and `duckdb_*`;
  - the `pragma_*` functions, including `pragma_platform` and `pragma_database_size`;
  - `checkpoint` and `force_checkpoint`, plus `json_execute_serialized_sql`, `summary` and the tpch/tpcds functions.
  It checks `force_checkpoint` and `json_execute_serialized_sql` too, because only scalar/macro/aggregate types are subtracted and pragma is not.
- **Names left out:** `range`, `generate_series`, `repeat` (also scalar) and `unnest` (exempted by the code). They generate rows; none of them reads data (measured on the exposure database).
- **Scalar positions:** for each of the 67 names I tried four forms: `select n('x')`, quoted, upper-case, and nested in a WHERE subquery. All 268 were refused with `function_not_allowed` (script `names.py`, result `passed or odd: []`).
- **What the exposure database itself allows** (measured directly on `exposed()`, without the guard). This is the reach a guard bypass would have:
  - `sniff_csv` reads the file (the known CVE). It returned the path and the header struct `{'col_a': 'VARCHAR', 'col_b': 'BIGINT'}`.
  - The engine refuses `read_text`, `read_blob`, `read_csv`, `glob` and `from '<file>'` with "Permission Error ... disabled through configuration".
  - `duckdb_settings()` values containing a `/`: `home_directory` and `secret_directory` are `/nonexistent`, plus `TimeZone=Europe/Paris`.
  - `pragma_platform()` returns `linux_amd64_gcc4`.
  - `duckdb_tables()` lists the copies only.
  All of these are already refused by name.
- **Scalars that pass the guard:** `version()` (`v0.10.2`), `current_database()` (`memory`), `current_query()` (echoes the caller's own SQL) and `which_secret()` (`''`). None of them exposes a path, a setting or another table.

### NEW-M1 (Medium): scalar `range`/`generate_series`/`repeat` go past the exposure `memory_limit`. Availability only, NOT a read
- **What:** the three names left out because they are also scalar build their result list outside DuckDB's buffer manager. The 512 MB cap (`api/repositories/readonly_warehouse.py:68,135`, `SET memory_limit = '{EXPOSURE_MEMORY_LIMIT}'`) does not bound them. The 5 s timer does not stop them either, because the allocation finishes first.
- **Evidence:**
  - `query_marts("select len(range(100000000))")` passed the guard and returned `[[100000000]]` in 1.1 s with max RSS **1666 MB**, under `ulimit -v 4000000`.
  - Without a ulimit, `query_marts("select count(*) from (select unnest(range(300000000)) x)")` ended the probe process with **exit 137 (SIGKILL)**. I infer a kernel OOM kill; I did not check dmesg.
  - Under the 4 GB ulimit, `len(range(300000000))` failed cleanly as `query_failed: std::bad_alloc`.
- **Reach:** nothing is read outside the copies. The guard lets it through by design (`warehouse_tools.py:138` checks only names in `table_function_names()`), and the exposure database does not stop it.
- **Impact:** one tool call can kill the MCP server process, and under WSL2 it can put memory pressure on the whole VM.
- **Fix, two options:**
  - (a) Refuse the scalar `range`/`generate_series`/`repeat`, or refuse them when an argument is a literal above about 1e6, with a test.
  - (b) Run the tool body under `resource.setrlimit(RLIMIT_AS, ...)` or in a subprocess.
  Option (a) is a quick win.
- **Effort:** small.

## Topic 3: M1, machine details in errors

**Measured** with the result dict printed as `query_marts` / `get_quality_report` return it, each case run for both tools:
- **Fixed message only:** absent file, directory in place of the file, corrupt file, file with mode 000, and the lock held by a writer in a second process. All return `{'code': 'warehouse_unavailable', 'message': 'warehouse unavailable: absent or locked by a writer'}`. No path, executable or PID appears; the detail goes to the logger.
- **Timeout:** `{'code': 'timeout', 'message': 'the query exceeded 5 s'}`, after 5.2 s.
- **`query_failed`:**
  - Binder: `Binder Error: Referenced column "nope" not found in FROM clause!`
  - Conversion: `Could not convert string 'x' to INT32`
  - Runtime: `Invalid Input Error: boom`
  - Allocation: `std::bad_alloc`
  None of them carries a machine detail. Refusal messages can echo a path the caller wrote itself (`from '<path>'`), which is not a machine detail.

### NEW-L1 (Low): a parent directory without the search permission raises an uncaught `PermissionError` carrying the absolute path. Path disclosure, NOT a read
- **What:** `Path.is_file()` re-raises EACCES.
  - Where it is raised: `api/repositories/readonly_warehouse.py:105` (`if not path.is_file():` in `exposed()`), and the same at `:85` in `locked()`.
  - Why nothing catches it: `query_marts` (`warehouse_tools.py:230,234`) and `get_quality_report` (`:256,258`) catch only `WarehouseUnavailable` and `duckdb.Error`.
- **Evidence:**
  - With the directory chmodded to 0600, both tools raised `UNCAUGHT PermissionError [Errno 13] Permission denied: '/tmp/claude-1000/.../scratchpad/locked_dir/wh.duckdb'`.
  - FastMCP turns an uncaught exception into the client's error text: `.venv/.../mcp/server/fastmcp/tools/base.py:116-117` `raise ToolError(f"Error executing tool {self.name}: {e}")` → `lowlevel/server.py:589-590` `return self._make_error_result(str(e))`. I traced this from the source, not end-to-end, because MCP calls were not allowed.
- **Reach:** this reads no data. The caller gets the absolute warehouse path (`RUNTIME_DB_PATH` or the home-based `data/` path). Triggering it depends on the environment (directory permissions), not on the caller.
- **Fix:**
  - Wrap `path.is_file()` in `try/except OSError` → `_unavailable(...)` in both `locked()` and `exposed()`.
  - Optionally, add a final `except Exception` → `ToolError("internal_error", <fixed text>)` in both tools.
  - Add a test with a 0600 parent directory.
- **Effort:** small; a quick win.

## Unable to verify
- The cause of exit 137 (OOM killer, presumably); I did not read dmesg.
- That every DuckDB error a guarded query can produce is free of machine detail. I only covered the classes listed above.
- MCP end-to-end error text, which was not allowed; I inferred it from the FastMCP source above.
- Behaviour after a DuckDB upgrade. The list follows the installed engine, but on 0.10.2 extensions are not autoloaded, so extension table functions are absent both from the list and from the exposure database.

## Prioritized action plan
1. NEW-M1: refuse or cap the scalar `range`/`generate_series`/`repeat`, or set an OS memory limit on the tool process, with a test (quick win).
2. NEW-L1: catch `OSError` around `is_file()` in `locked()` and `exposed()` and add a catch-all fixed error in both tools, with a test (quick win).
3. Optional usability fix: accept a parenthesised join of named tables in `_allowed_source`.
4. Keep the DuckDB upgrade ticket (CVE-2024-41672). sniff_csv is still the only measured file read on the exposure database, and only the guard stops it.

Probe scripts, outside the repo: `/tmp/claude-1000/-home-ellie-projets-cyclebeat/a9cbe024-f471-4889-870b-6b7972d6a184/scratchpad/{mk,engine,guard,guard2,names,m1,m1b,mem}.py`
