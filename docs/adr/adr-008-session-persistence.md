# ADR-008 — Session persistence: `fct_session` materialized, feedback rekeyed on `session_id`

- **Status**: Accepted
- **Date**: 2026-08-29
- **Owner**: Ellie

## Context

Phase 4 is the first phase that has to **store** a session. E.3 routes `GET /v1/sessions/{id}`
and `POST /v1/sessions/{id}/feedback`, both keyed on a session id, and neither had anywhere to
read from:

1. **`fct_session` did not exist.** E.2 declares it — `session_id, params user, verdict,
   n_segments, duration_gap_s, llm_cost_usd, latency_ms` — but nothing ever created it. The
   `sessions` table in the warehouse is the **v1** shape (`title, playlist_url, created_at,
   duration_s, track_count, session_json`), keyed on a title, and it is empty.
2. **`raw.feedback` is keyed on `session_title`.** E.2 declares that shape, and the dbt chain
   `stg_feedback → int_feedback_enriched → mart_feedback_summary` — which E.2's 2026-08-15
   note promoted to normative — groups on it. But a title is a mutable display string and is
   not unique: two sessions called the same thing are indistinguishable, and feedback cannot
   be attached to the session the user actually rated.
3. **DuckDB was not primary.** E.2's own note recorded the residual gap: the v1 API wrote
   DuckDB best-effort and kept the JSON file as the source of truth. That note assigns the fix
   to **phase 4**, along with moving the SQL into `api/repositories/` (E.0.5).

E.2 permits this: "any deviation = breaking change with impact analysis". This is that
analysis.

## Options

### 1. How feedback is keyed

| Option | Behaviour | Cost |
|---|---|---|
| **A — add `session_id`, keep `session_title`** (chosen) | `session_id` becomes the real key; `session_title` stays as a denormalized label | Additive change to a normative table |
| B — replace `session_title` with `session_id` | Cleaner table | **Breaks the normative dbt chain**: `int_feedback_enriched` and `mart_feedback_summary` group on the title, and their dbt tests would fail |
| C — keep keying on the title | No contract change at all | Feedback cannot reliably identify a session, which is the defect being fixed |

Option A. It is the only one that fixes the defect without breaking a chain E.2 declared
normative in the same appendix. The cost is one redundant column, and redundancy that keeps a
downstream contract intact is cheap.

Sessions carry no user-facing title in E.3, so the label is **derived**
(`session-<first 8 of the id>`) rather than invented as a new contract field.

### 2. Where the session body lives

| Option | Behaviour | Cost |
|---|---|---|
| **A — scalar columns + `plan_json`** (chosen) | The E.2 columns are real columns; the full plan is stored alongside as JSON | One denormalized blob |
| B — JSON only | Simplest write | `GET /v1/sessions` would have to parse every row to page, and dbt could not model the fact table |
| C — fully normalized (a `fct_segment` child table) | Purest model | E.2 declares no such table, and phase 4 does not need per-segment SQL; it would be inventing a contract |

Option A. The scalar columns are what `GET /v1/sessions` pages over and what dbt can model;
`plan_json` is what makes a replay byte-identical to what was served.

## Decision

1. **`fct_session` is materialized** by the API, with E.2's declared columns.
   `llm_cost_usd` and `latency_ms` exist but stay NULL until phase 6 wires LiteLLM — the
   columns are declared by E.2, so they are created now rather than added later.
2. **`raw.feedback` gains `session_id`**, which becomes the key. `session_title` is retained
   and populated so the normative dbt chain is untouched.
3. **DuckDB is primary.** The JSON file is no longer the source of truth for sessions or
   feedback, and a failed write raises instead of being swallowed.
4. **All of that SQL lives in `api/repositories/`** (E.0.5).

## Consequences

- **An existing database must be migrated, and is.** `CREATE TABLE IF NOT EXISTS` is a no-op
  against the v1 `feedback` table, so the new column would never appear and every insert would
  fail with a binder error. Any machine that ran the v1 API has exactly that table.
  `api/repositories/connection.py` issues an idempotent
  `ALTER TABLE feedback ADD COLUMN IF NOT EXISTS session_id`, and
  `test_a_pre_existing_v1_feedback_table_is_migrated` is the regression test. **This was found
  by driving the endpoint, not by review.**
- **v1 rows survive with a NULL `session_id`**, which is honest: that feedback genuinely was
  not keyed on a session. Nothing back-fills a guess.
- **The dbt feedback chain is untouched.** `stg_feedback` and everything below it still read
  `session_title`; their tests pass unchanged. A future phase can migrate them to
  `session_id`, and this ADR is what will let it.
- **The v1 `sessions` table is now dead.** It is left in place rather than dropped: it is
  empty, dropping it is not needed by this phase, and `mart_session_kpis` still reads it. That
  cleanup belongs with the phase-5 work that decides what the history screen shows.
- **Not a breaking change to any shipped API.** The endpoints that used the old shapes were v1
  and are deleted in the same commit; nothing external consumes them.
- **E.2 is annotated** with a dated note pointing here, the same way ADR-006 annotated it.

## References

- `docs-notes/CYCLEBEAT_PLAN_V3.md` E.2 (`fct_session`, `raw.feedback`, and the 2026-07-28 /
  2026-08-15 notes that assigned this to phase 4), E.3 (the session endpoints), E.0.5 (SQL only
  in `api/repositories/` and `dbt/`), §7 (layering).
- `docs/adr/adr-006-e2-open-points.md` — the precedent for annotating E.2 from an ADR.
- `api/repositories/connection.py`, `api/repositories/session.py`,
  `api/repositories/feedback.py`, `tests/unit/test_api_repositories.py`.
