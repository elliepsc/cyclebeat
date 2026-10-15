> security-auditor, pass 1 (before merge). Diff reviewed: `origin/main..ff38132` (d18339e, 4ac9ed8, ff38132). Raw output, unedited. Agent old definition: `.claude/agents/security-auditor.md` as on origin/main @ 14319b0 (the fix branch did not carry a8d9830 yet; agent definitions are read from the checked-out branch); its first line, cited by the auditor: "You audit and produce committable reports in `docs/security/`."

---

"You audit and produce committable reports in `docs/security/`." My tools are Read, Bash, Write and SubagentHandback.

Reference branch: `fix/query-marts-cte-scope` at ff38132, checked against `origin/main` after a fetch. You asked me not to write files in the repo, so this report is returned here rather than committed to `docs/security/`. That differs from my agent definition; your instruction took precedence.

# PR audit: fix/query-marts-cte-scope (d18339e, 4ac9ed8, ff38132)

## Executive summary
- **Overall risk: HIGH. Do not merge yet.** The per-scope CTE fix works against every scope trick I tried (about 140 probes), but the CTE whitelist can still be bypassed by Unicode case-folding.
- A CTE named with U+212A KELVIN SIGN (`"stg_tracKs"`) passes the guard, and DuckDB then reads the real `stg_tracks` table. I reproduced this end-to-end through `query_marts` on the locked engine.
- `main` has the same flaw, so the PR did not introduce it. But the PR says it closes the H1 class (a CTE name whitelisting a real table), and this is that class.
- **Action #1:** compare names the way DuckDB does (ASCII-only lowercasing), or refuse non-ASCII table and CTE identifiers, and add a test for it in this PR.

## Gates run
- `uv run pytest tests/unit/test_copilot_guards.py -q -p no:warnings -o addopts=""` gave `94 passed, 1 xfailed in 1.97s`, exit 0. The xfail is `test_the_locked_connection_refuses_sniff_csv` (strict, CVE-2024-41672), as declared.
- `uv run ruff check` on the 2 changed Python files: "All checks passed!". `uv run mypy api/services/warehouse_tools.py`: exit 0.
- E.4 normative tests (6 of 9 due now, per CLAUDE.md and ADR-012): drop injection, multi-statement, non-SELECT, table outside allowlist, "delete" false positive and LIMIT injected are present (`tests/unit/test_copilot_guards.py:86-117`). The other 3 are deferred to phase 6 as documented, so no finding.
- Versions: duckdb 0.10.2, sqlglot 30.18.0.
- Setup: probe warehouse built in my scratch directory under `/tmp`, holding the 4 marts, `stg_secret`, `"STG_UPPER"`, `stg_secret_view`, `stg_tracks`, a CHECK constraint, a scalar macro `leak()`, a table macro, a sequence and `raw.tracks`. Every probe went through `query_marts`, i.e. the locked engine.

## Findings

### HIGH 1: Unicode case-folding mismatch lets a CTE name whitelist a real off-allowlist table
- **What:** The guard lowercases names with Python `str.lower()`, which is Unicode-aware. DuckDB 0.10.2 matches identifiers case-insensitively over ASCII only. U+212A KELVIN SIGN lowercases to ASCII `k` in Python, but DuckDB treats it as a different character from `k`. So a CTE named `stg_tracKs` registers as `stg_tracks` in the guard's visible-CTE set, while DuckDB binds `FROM stg_tracks` to the real table. I enumerated every code point from U+0080 to U+10FFFF: U+212A is the only one whose `.lower()` is ASCII.
- **Where:**
  - `api/services/warehouse_tools.py:112`: `visible_ctes = {name.lower() for name in scope.cte_sources}`
  - `api/services/warehouse_tools.py:128` (`name = table.name.lower()`) and `:132` (`if schema == "" and name in visible_ctes: return`)
- **Evidence (locked engine, through `query_marts`):**
  ```
  GUARD PASS -> 'WITH "stg_tracKs" AS (SELECT 1 AS x) SELECT * FROM stg_tracks LIMIT 200'
     RESULT: [['SECRET_STG_TRACKS']]
  GUARD PASS -> 'WITH stg_tracKs AS (SELECT 1 AS x) SELECT * FROM stg_tracks LIMIT 200'
     RESULT: [['SECRET_STG_TRACKS']]
  ```
  `git show origin/main:api/services/warehouse_tools.py` line 76 has the same `.lower()` on CTE names, so this predates the PR.
- **Impact:** Any MCP client or future copilot can read any table or view on the default search path whose name contains `k`. In the tracked dbt models that is `stg_tracks`, `stg_feedback`, `int_feedback_enriched`, `int_track_resolution`, `mart_feedback_summary` and `mart_session_kpis`, all off the E.4 allowlist. It is read-only with no disk access (the engine lock holds), so this is an allowlist bypass, not an escape. Same class and severity as H1.
- **Fix (proposal, not applied):** fold names exactly like DuckDB, and fail closed on non-ASCII names.
  ```python
  def _fold(name: str) -> str:
      if not name.isascii():
          raise ToolError("table_not_allowed", "non-ASCII identifiers are refused")
      return name.lower()
  ```
  Use it for `scope.cte_sources` keys, `table.name` and `table.db`. Add a `stg_tracks` table to the test fixture and a parametrized refusal test with the Kelvin-sign CTE, plus a `"dim_tracK"` case.
- **Effort:** S (about 10 lines of code and 1 test). Quick win.

### LOW 1: The function denylist is name-based, so warehouse-defined macros run unchecked (latent)
- **What:** `_FORBIDDEN_FUNCTIONS` is a fixed list of 4 names. Any user-defined scalar macro stored in the warehouse runs on the locked engine, and its body is never seen by the table check.
- **Where:** `api/services/warehouse_tools.py:59-61` and `:94-99`.
- **Evidence:** In my probe warehouse I created `CREATE MACRO leak(x) AS (SELECT max(v) FROM stg_secret)`. Then:
  ```
  LEAK!!  SELECT leak(1) FROM dim_track       -> [["SECRET_ROW"], ...]
  LEAK!!  SELECT main.leak(1) FROM dim_track  -> [["SECRET_ROW"], ...]
  ```
- **Why latent:** `git grep -niE "CREATE (OR REPLACE )?(TEMP )?(MACRO|FUNCTION|SEQUENCE)" -- dbt cyclebeat api dags` returns nothing, and `git ls-files dbt | grep macros/` is empty. An attacker cannot create a macro, because only one SELECT is allowed and the file is read-only.
- **Impact:** None today. Any future macro in the warehouse becomes a bypass.
- **Fix:** At run time on the locked connection, refuse any call whose name is in `SELECT function_name FROM duckdb_functions() WHERE NOT internal`. Alternatively, switch to a function allowlist when the DuckDB upgrade line is done.
- **Effort:** S.

### LOW 2: The built-in macro `get_block_size` reads the catalogue and is not on the list
- **What:** In DuckDB 0.10.2 its definition is `(SELECT block_size FROM pragma_database_size() WHERE (database_name = db_name))`. It is the only built-in macro with a `FROM` that the denylist misses; I listed all of them via `duckdb_functions() WHERE function_type='macro' AND macro_definition ILIKE '%from%'`.
- **Evidence:** `SELECT get_block_size(current_database()) FROM dim_track` returned `[[262144], ...]`.
- **Impact:** Negligible: it exposes the block size and gives a yes/no test for whether a database name exists. It does contradict the stated rule (guard 5: "no scalar call to a function that reads the catalogue").
- **Fix:** Add `get_block_size` to `_FORBIDDEN_FUNCTIONS`, with a test.
- **Effort:** XS. Quick win.

### LOW 3: The docs now overstate what the guard guarantees
- **Where:** the docstring at `api/services/warehouse_tools.py:11-15`, the ADR-012 note "Fixed on `fix/query-marts-cte-scope`...", and the `mcp-server/README.md` row ("a CTE name valid only in its own scope").
- **Fix:** Correct them together with HIGH 1, recording the case-folding rule.
- **Effort:** XS.

### INFO (no action required)
- `nextval('seq1')` runs on the read-only engine (it returned 1..50). The state lives only in the session, and the repo creates no sequences.
- `current_database()`, `current_catalog()` and `current_schemas(true)` reveal the warehouse file stem. The PR deliberately allows `current_database()` (`test_harmless_scalar_functions_still_pass`).
- `which_secret('s3://bucket/x','s3')` returned `""`. See Unable to verify.

## What held (searched, with evidence)
I ran 5 probe files plus a Kelvin script. Every query below was refused, failed in DuckDB's binder or parser, or returned only CTE or mart data:
- **Case and quoting:** `"STG_SECRET"`, `"main"."stg_secret"`, `memory.main.dim_track`, `wh.main.stg_secret`.
- **Lateral and correlated subqueries:** `LATERAL (WITH stg_secret ...)` next to the real table, a correlated scalar subquery, `JOIN LATERAL`.
- **Forward references:** a later-defined CTE referenced from an earlier CTE body, including inside nested scalar, derived and EXISTS subqueries.
- **Recursive CTEs:** 14 self-reference variants. Bodies without a UNION are refused. Anchor self-references end in DuckDB "Circular reference". Nested references in the recursive term bind to the CTE: with `UNION` dedup each returned `[["x"]]` and never the real row.
- **Aliases equal to CTE names**, and a derived-table alias equal to a real table name.
- **Set operations:** WITH on each branch, unparenthesized `UNION ALL WITH ...`, `UNION BY NAME`, `EXCEPT (WITH ...)`.
- **PIVOT/UNPIVOT** in statement and subquery form, **QUALIFY** and **VALUES** with subqueries.
- **DuckDB-specific syntax:** `FROM`-first, `TABLE x`, `(SUMMARIZE|DESCRIBE|SHOW ...)`, POSITIONAL/ASOF/SEMI/ANTI joins, lambda and list-comprehension subqueries, struct literals, LIMIT/OFFSET/ORDER/HAVING/WINDOW subqueries.
- **Function-name evasion:** quoted `"pg_get_viewdef"`, `main.`, `pg_catalog.`, `system.pg_catalog.`, method syntax `(oid).pg_get_viewdef()` and `'x'.current_setting()`, and inside lambdas. All were refused with `function_not_allowed`.
- **sqlglot rename path:** `grep -rniE "current_setting|pg_get_viewdef|format_type|pg_get_constraintdef|get_block_size|which_secret"` over the installed sqlglot package returned nothing, so no generator renames another function into a forbidden one.
- **Regeneration stability:** feeding the guard its own output was stable for all 51 accepted probes (0 mismatches).
- **Built-in macro inventory:** the only catalogue-reading macros are the 3 already refused plus `get_block_size` (LOW 2). There is no `getenv`, and no scalar file reader in 0.10.2.

## Unable to verify
- **`which_secret` and `current_setting`-style leaks with persistent DuckDB secrets on the host.** Testing it would mean writing into the user's home secret directory, so I did not.
- **The real warehouse's contents** (macros, sequences, which tables exist). Not inspected, per the instruction to stay out of `data/`. LOW 1 depends on this.
- **Memory exhaustion within the 5 s timeout** (for example `repeat('x', 2e9)`). Deliberately not run on this machine.
- **SAST and dependency scans:** `semgrep`, `gitleaks` and `pip-audit` are not installed (`command -v` returned nothing), so they were not run. Not "clean". A grep of the PR diff for `api_key|secret_key|token|password|BEGIN .*PRIVATE` on added lines returned nothing.
- **`.env` history:** owner action. The owner reported no line; I did not run it.
- **`docs/security/` does not exist** (`ls: cannot access 'docs/security'`), so none of the grid's PR-audit or scan artifacts are committed. This is outside this PR's scope but is a grid gap (criterion 13).

## Prioritized action plan
1. **(Quick win, blocks merge)** Fix HIGH 1 with ASCII-only folding or refusing non-ASCII identifiers. Add a `stg_tracks` fixture table and the Kelvin tests, and correct the docs (LOW 3) in the same PR.
2. **(Quick win)** Add `get_block_size` to `_FORBIDDEN_FUNCTIONS`, with a test (LOW 2).
3. Add a runtime refusal of non-internal functions (`duckdb_functions() WHERE NOT internal`), or note it on the DuckDB upgrade roadmap line (LOW 1).
4. Install the free scanners (`semgrep`, `gitleaks`, `pip-audit`) and create `docs/security/` for the phase-10 deliverables.

All probe scripts, queries and the probe warehouse are in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/a9cbe024-f471-4889-870b-6b7972d6a184/scratchpad/probe/`. The Kelvin reproduction is `kelvin.py` there. I wrote nothing in the repo.
