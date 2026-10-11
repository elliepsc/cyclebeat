---
name: new-mart
description: Add a dbt mart to CycleBeat end to end, the way the existing marts were built — grain first, staging → intermediate → marts, schema.yml tests plus singular check_* tests, build on a scratch warehouse, dbt-reviewer review, and (only if asked) the read endpoint contract-first. Use when the user asks for a new mart, KPI table or analytical aggregate.
---

# new-mart — a dbt mart, end to end

Derived from how the eight existing marts were actually built, and from the corrections logged
in `docs/ai-workflow.md`. Sources are listed at the end; when this file and the code disagree,
the code wins (CLAUDE.md truth sources). `CLAUDE.md` rules apply throughout: SQL only in `dbt/`
and `api/repositories/`, no write to the real `data/` or `lake/`, one phase = one branch + one PR,
every command through `uv run` / `make`.

## 0. Before writing anything

- `git branch --show-current`: never on `main`.
- Say in one sentence the question the mart answers and its **grain** (one row per what).
  Every mart header and `schema.yml` description in this repo states its grain; if the request
  does not make it obvious, ask.
- Check it does not exist: `ls dbt/models/marts/`, `grep -n "name:" dbt/models/marts/schema.yml`.
- **Never re-derive a normative rule.** BPM normalization, zones and confidence (E.2) are computed
  once in `cyclebeat/e2.py` and materialized as `raw_resolved`; dbt only reads them. A second
  implementation in SQL is the "local heuristic" CLAUDE.md warns about.

## 1. Where the logic goes — the three layers

| Layer | Name | Materialized | Does |
|---|---|---|---|
| staging | `stg_<entity>` | view | clean and deduplicate one source (`{{ source('raw', ...) }}`): latest partition wins, invalid values nulled with the reason in a comment. No business rule |
| intermediate | `int_<subject>` | view | assemble: joins and per-key flags. "Assembles, it does not decide" |
| marts | `dim_` / `fct_` (Kimball) or `mart_<subject>` (aggregate) | table | answer one question at one grain |

A new mart reads `ref()` of staging or intermediate models, never a raw path and never another
source directly. If the join it needs does not exist, add an `int_` model rather than a long mart.
Materialization comes from `dbt/dbt_project.yml`; no per-model config unless it differs.

## 2. The model file

`dbt/models/marts/<name>.sql`:

- **Header comment** first: what it answers, its grain, what reads it, and any measured figure
  that would reveal a drift (e.g. `mart_data_quality` keeps the phase-1 distribution in its header).
- CTEs named for what they hold (`tracks`, `total`, `per_source`), then one final `select`.
- Explicit column names; `round()` only where a reader needs it; `count(*) filter (where ...)`
  for conditional counts (the house style in `int_track_resolution` and `mart_data_quality`).

## 3. Tests — `schema.yml` plus singular checks

Add the model to `dbt/models/marts/schema.yml`:

- `description:` with the grain and what reads it (an endpoint, the agent-tools allowlist);
- every column described; the grain column: `tests: [not_null, unique]`;
- enums: `accepted_values` with the **exact** values (a range would let a contract violation in);
- invariants that span rows (shares summing to 100, bounds, totals matching `dim_track`): a
  **singular test** `dbt/tests/check_<what>.sql` that returns the offending rows. This repo uses
  singular tests on purpose so no dbt package (no `dbt_utils`) has to be installed.

## 4. Build — on a scratch warehouse, never `data/`

```bash
SCRATCH="$(mktemp -d)"
cp data/cyclebeat_runtime.duckdb "$SCRATCH/mart-dev.duckdb"   # reading data/ is allowed
RUNTIME_DB_PATH="$SCRATCH/mart-dev.duckdb" make dbt
```

`make dbt` without `RUNTIME_DB_PATH` writes the real warehouse and the guardrail refuses it.
Then:

- every model and test green; **report the PASS count and explain any change** from the count
  before your change, by measurement, not by guess;
- if dbt fails on a column that the models do not reference, suspect a **stale** warehouse
  file before editing a model: compare with a freshly built one (a throwaway worktree);
- count the mart's rows and say whether the number makes sense; a gap between two counts that
  should agree is reported with its cause, not smoothed over.

## 5. Review

Invoke the **`dbt-reviewer`** subagent on the diff. Apply what it marks blocking; report the
rest to the user.

## 6. Exposure — only if the user asked for it

- **Read endpoint**, contract first, all in one PR (CLAUDE.md): `openapi.yaml` → a repository in
  `api/repositories/` that checks `table_exists` and returns `[]` before dbt has run (the
  `QualityRepository` pattern) → `api/services/` (shape) → `api/routers/` → `make front-gen`.
  Invoke **`contract-guardian`** on that diff; `make contract` green, after `make dbt`.
- **Agent tools**: adding the mart to `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py`)
  changes E.4 and needs an ADR. Ask first.

## 7. Done

`make lint typecheck test-unit` green, `RUNTIME_DB_PATH=... make dbt` green with its PASS count,
an entry in `docs/ai-workflow.md`. Report the files, the tests added, the reviewer verdicts, and
what was not done.

## Sources this workflow was derived from

- Layers and materialization: `dbt/dbt_project.yml`, `dbt/models/sources.yml`, `dbt/models/staging/`,
  `dbt/models/intermediate/`, `dbt/models/marts/` (e.g. `stg_resolutions.sql`,
  `int_track_resolution.sql`, `mart_data_quality.sql`, `dim_track.sql`).
- Tests and "no dbt package": `dbt/models/marts/schema.yml` (`dim_track.bpm_effective`,
  `confidence`), `dbt/tests/check_*.sql` (e.g. `check_data_quality_shares.sql`).
- E.2 never re-implemented in SQL: CLAUDE.md "Known pitfalls", `int_track_resolution.sql` header,
  `docs/ai-workflow.md` session 2026-08-15 (phase 2).
- Stale warehouse diagnosed by comparison, clean `RUNTIME_DB_PATH`: `docs/ai-workflow.md` session
  2026-10-01 (chore A1, README V3).
- dbt PASS count explained by measurement, not by guess: `docs/ai-workflow.md` session 2026-10-01
  (phase 4, Postgres persistence).
- Report a count gap with its cause (50 measurements vs 48 tracks), always `uv run`:
  `docs/ai-workflow.md` session 2026-08-15 (phase 2).
- Endpoint pattern: `api/repositories/quality.py`, `openapi.yaml` `/v1/quality/*`, CLAUDE.md
  (contract + backend + front client in one PR).
- Allowlist and ADR: `api/services/warehouse_tools.py`, ADR-012.
