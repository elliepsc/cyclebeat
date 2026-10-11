---
name: new-mart
description: Add a dbt mart to CycleBeat end to end — model, schema.yml with grain and tests, build on a scratch warehouse, dbt-reviewer review, and (only if asked) the read endpoint contract-first. Use when the user asks for a new mart, KPI table or analytical aggregate.
---

# new-mart — a dbt mart, end to end

The repetitive analytics-engineering gesture of this repo, done the same way every time.
`CLAUDE.md` rules apply throughout: SQL only in `dbt/` and `api/repositories/`, no write to the
real `data/` or `lake/`, one phase = one branch + one PR.

## 0. Before writing anything

- `git branch --show-current`: never on `main`.
- State, in one sentence: the question the mart answers, its **grain** (one row per what), and
  its upstream models. If the grain is not obvious from the request, ask.
- Check it does not exist: `ls dbt/models/marts/` and `grep -n "name:" dbt/models/marts/schema.yml`.
- Normative contracts are not re-derived: BPM, zones and confidence come from `dim_track`
  (E.2, `cyclebeat/e2.py`), never recomputed in the mart.

## 1. The model

`dbt/models/marts/<name>.sql`, named `mart_<subject>` (aggregate) or `fct_`/`dim_` (Kimball).

- A header comment: what it answers, its grain, why it exists.
- `ref()` to staging or intermediate models only, never a raw path.
- Materialized as a table by the `marts:` block of `dbt/dbt_project.yml`; no per-model config
  unless it differs.
- Explicit column names; `round()` only where a reader needs it.

## 2. `schema.yml`

Add the model to `dbt/models/marts/schema.yml`:

- `description:` with the grain and what reads it (an endpoint, the copilot allowlist).
- every column described;
- the grain column(s): `not_null` + `unique` (or `dbt_utils.unique_combination_of_columns`);
- enums: `accepted_values`; foreign keys: `relationships`;
- a singular test in `dbt/tests/` for any business invariant (bounds, shares summing to 100).

## 3. Build it — on a scratch warehouse, never `data/`

```bash
SCRATCH="$(mktemp -d)"
cp data/cyclebeat_runtime.duckdb "$SCRATCH/mart-dev.duckdb"   # reading data/ is allowed
RUNTIME_DB_PATH="$SCRATCH/mart-dev.duckdb" make dbt
```

`make dbt` without `RUNTIME_DB_PATH` writes the real warehouse and the guardrail refuses it.
All dbt tests green, or fix before going on.

## 4. Review

Invoke the **`dbt-reviewer`** subagent on the diff. Apply what it marks blocking; report the
rest to the user.

## 5. Exposure — only if the user asked for it

- **Read endpoint**: contract first. `openapi.yaml`, then `api/repositories` (the SQL),
  `api/services`, `api/routers`, then `make front-gen` — all in the same PR (CLAUDE.md).
  Invoke the **`contract-guardian`** subagent on that diff. `make contract` green.
- **Agent tools**: adding the mart to `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py`)
  changes E.4 and needs an ADR. Ask first.

## 6. Done

`make lint typecheck test-unit` green, `RUNTIME_DB_PATH=... make dbt` green, an entry in
`docs/ai-workflow.md`. Report: files created, tests added, reviewer verdicts, what was not done.
