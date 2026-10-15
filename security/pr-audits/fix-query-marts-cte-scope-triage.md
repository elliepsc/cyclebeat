# Triage — pre-merge reviews of `fix/query-marts-cte-scope`

Written by the main agent, not by the reviewers. The raw reports sit next to this file, one per
pass, unedited: `fix-query-marts-cte-scope-security-auditor-pass{1,2,3,4}.md` and
`fix-query-marts-cte-scope-contract-guardian-pass{1,2,3,4}.md`. The audit of PR #38 that
started this branch belongs to the phase-10 branch.

Each finding is **fixed** (with its commit), **accepted** (with the reason) or **recorded**
(with its `docs/ROADMAP.md` line). "Neutralised" means the exposure database (2980b7f) makes the
finding unreachable even though the guard alone would not.

Agent definitions: security-auditor passes 1 and 2 ran on the OLD definition (origin/main @
14319b0: agent files are read from the checked-out branch, and a8d9830 was not on this branch
yet); passes 3 and 4 on the new one (263ccb9). contract-guardian ran on the same definition for
all four passes.

## security-auditor, pass 1 (diff `origin/main..ff38132`)

| Finding | Verdict | Evidence / reference |
|---|---|---|
| HIGH 1 — U+212A KELVIN SIGN folds to `k` in Python, not in DuckDB: a CTE named `stg_tracKs` whitelisted the real `stg_tracks` | **Fixed** — cf9e15a (tests, 4 failed before), 2d2f008 (ASCII-only identifiers) | reproduced end to end before the fix |
| LOW 1 — a macro defined in the warehouse runs unchecked | **Neutralised** — 2980b7f: the exposure database copies BASE TABLEs only (f7d651d), so no warehouse macro exists where the SQL runs. **Recorded** for the denylist itself: ROADMAP `[présentable]`, DuckDB upgrade line (non-internal functions or a function allowlist) | none in the repo today (`CREATE MACRO` absent from `dbt/`, `cyclebeat/`, `api/`, `dags/`) |
| LOW 2 — `get_block_size` reads the catalogue | **Fixed** — cf9e15a, 2d2f008 | |
| LOW 3 — docs overstated the guard | **Fixed** — 95fe0c8, then every later docs commit (85f4d56, fc42b1e) | |
| INFO — `nextval()` runs on the read-only engine | **Neutralised** — 2980b7f: sequences are not copied | |
| INFO — `current_database()` revealed the warehouse file stem | **Neutralised** — 2980b7f: it returns `memory` on the exposure database | measured by pass 3 |
| INFO — `which_secret()` returns `''` | **Accepted** — no secret is configured, and the path settings are neutralised (2980b7f) | |

## security-auditor, pass 2 (diff `ff38132..95fe0c8`)

| Finding | Verdict | Evidence / reference |
|---|---|---|
| NEW-H1 — sqlglot re-emits function names with Unicode `upper()`: `current_settıng` became `CURRENT_SETTING` after the check and returned the OS user's home | **Fixed** — fa1f5a6 (tests, 6 failed before), 2980b7f (ASCII function names, the guard re-checks its own output; structural fix: the exposure database) | reproduced end to end before the fix |
| NEW-L1 — two doc claims said more than the code | **Fixed** — 85f4d56 | |
| NEW-L2 — no `docs/ai-workflow.md` entry on the branch | **Fixed** — AI_WORKFLOW_COMMIT | |

## security-auditor, pass 3 (diff `95fe0c8..85f4d56`)

| Finding | Verdict | Evidence / reference |
|---|---|---|
| C1 (critical) — `JOIN LATERAL sniff_csv('<file>') ON true` is an `exp.Lateral`: it passed the table check and the first line of a file came back through `query_marts` (CVE-2024-41672); present on origin/main too | **Fixed** — 6b102b2 (tests, 18 failed before), f7d651d (only named table / subquery / VALUES sources; table-function names refused anywhere) | reproduced with a harmless file, on this branch and on origin/main's code. The engine-side hole stays: **recorded**, ROADMAP `[présentable]`, first line (DuckDB upgrade, C1 mention); two `xfail(strict)` tests |
| M1 — `warehouse_unavailable` carried the file path, the lock holder's executable under the home directory and its PID | **Fixed** — 6b102b2, f7d651d (fixed message, detail logged) | measured on `exposed()`, `locked()` and origin/main before the fix |
| L1 — `ROWS FROM (...)` crashed the guard (`AttributeError`) | **Fixed** — 6b102b2, f7d651d (any internal guard error is `guard_error`) | |
| L2 — `USING SAMPLE` broken by the LIMIT injection | **Recorded** — ROADMAP `[présentable]`, "Requêtes refusées à tort" line | functional, not security |
| L3 — `locked()` had no production caller and its docstring did not say so | **Fixed** — f7d651d | |
| INFO — settings visible on the exposure database without the guard (TimeZone, threads, platform, version) | **Accepted** — through the guard, `current_setting`, `duckdb_settings()` and `pragma_*` are refused (2d2f008, f7d651d); `version()` is the version pinned in `uv.lock` | owner decision: recorded, no fix |
| INFO — ENUM labels travel with a copied mart | **Accepted** — no mart uses an ENUM (dbt `table` models) | owner decision: recorded, no fix |
| INFO — the copy runs while external access is still on; a mart turned view would run unlocked | **Fixed** — f7d651d (BASE TABLEs only) | test `test_a_view_in_the_warehouse_is_never_copied` |
| INFO — building the exposure database is outside the 5 s timer, `memory_limit` set after the copy | **Recorded** — ROADMAP `[présentable]`, process memory limit line | |
| Process — a safety classifier stopped one probe (on a file named `fake.env`) | **Accepted** — the probe was not retried and the measurement was not resumed (owner rule) | C1's reach is "at least the first line of any readable file" |

## security-auditor, pass 4 (diff `85f4d56..f7d651d`, scope limited to sources, table functions, M1)

| Finding | Verdict | Evidence / reference |
|---|---|---|
| No read found: 70+ source shapes and 268 table-function calls refused | — | |
| NEW-M1 (medium, availability) — scalar `range` / `generate_series` / `repeat` allocate past the exposure database's memory limit (1666 MB RSS; a larger call got the process killed) | **Fixed** — 7d91646 (tests, part of 7 failed before), feae0a7 (refused, `function_not_allowed`). **Recorded** — ROADMAP `[présentable]`, process memory limit line (the real fix) | not a confidentiality risk |
| NEW-L1 (low) — an unsearchable parent directory turned `Path.is_file()` into a `PermissionError` carrying the absolute path out of both tools | **Fixed** — 7d91646, feae0a7 (OSError → fixed message; last-resort `internal_error`) | reproduced before the fix. The owner ruled it not a "read" under the stop rule (ADR-012 note) |
| Usability — a parenthesised join of named tables is refused as a source | **Recorded** — ROADMAP `[présentable]`, "Requêtes refusées à tort" line | refused by default, as the source rule intends |
| Unable to verify — the MCP end-to-end error text (MCP calls forbidden during containment) | **Accepted** — the last-resort `internal_error` (feae0a7) covers what FastMCP would otherwise stringify | traced in FastMCP's source by the auditor |

## Discrepancy between an audit and a measurement

Pass 3 counted the `PIVOT dim_track ON zone ...` statement among 63 accepted analyst queries. The
guard refused it before any change of this branch (`not_a_select`, measured). 62 of the 63
are pinned as accepted (`test_analyst_queries_pass_the_guard`); the PIVOT statement is pinned
as refused (`test_a_pivot_statement_is_not_a_select`) and recorded with the false refusals.

## contract-guardian, passes 1 to 4

All four: **APPROVED**, no violation. Semantic risks:

| Risk | Verdict | Reference |
|---|---|---|
| Phase 6 will expose the tools over HTTP/SSE: `openapi.yaml` must list the tool error codes and say whether a refusal is an SSE event or an RFC 7807 error (pass 1, repeated in pass 4) | **Recorded** — ROADMAP `[présentable]`, "Couche LLM du Warehouse Copilot" line | |
| The function list is a denylist (pass 1) | **Neutralised / recorded** — as security-auditor pass 1, LOW 1 | |
| Two strict xfails to un-mark after the DuckDB upgrade (pass 3) | **Recorded** — ROADMAP DuckDB line names both tests | |
| `get_quality_report` and `/v1/quality/*` can disagree when the warehouse is missing (pass 3) | **Accepted** — unchanged by this branch; the endpoint's fallback is the existing ROADMAP line "Base analytique absente" | |
| `range` / `generate_series` / `repeat` now refused: a change for MCP clients (pass 4) | **Accepted** — measured availability risk, documented in ADR-012 | |
| `table_function_names()` depends on the DuckDB version and is cached (pass 4) | **Accepted** — a failure becomes `guard_error`, refused | |
