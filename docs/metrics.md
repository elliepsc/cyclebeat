# Metrics — the KPIs the marts expose

Every figure a dbt mart publishes, with its definition, grain, formula, source and the tests
that guard it. The models are the reference (`dbt/models/marts/`); column-level detail is in
[`dbt/models/marts/schema.yml`](../dbt/models/marts/schema.yml). A mart's grain is stated in its
`schema.yml` description and guarded by a test (issues #46 and #54).

## The rule: a count is 0, everything else stays NULL

On an empty input (no session, no feedback):

- a **count** is `0`. "How many?" over nothing has an answer, and it is zero. A NULL count
  reads as "unknown" and breaks every consumer that adds or compares it. `count(*)` gives 0
  by itself; a count written as `sum(...)` (a sum of flags, or of per-row counts) is wrapped in
  `coalesce(..., 0)` or rewritten as `count(*) filter (where ...)`.
- an **average, a share, a minimum, a maximum or a date** stays `NULL`. There is no value to
  report, and `0` would be a false one: a 0 % satisfaction says "everyone disliked it", a 0 s
  gap says "on target".

`coalesce` applies to counts only. The rule is unit-tested on `mart_session_kpis`
([`unit_tests.yml`](../dbt/models/marts/unit_tests.yml), `session_kpis_empty_history`), which
failed on the previous `sum()` version of the mart (expected 0, got NULL).

## Which tests prove something

The demo and CI warehouses hold **0 sessions and 0 feedback**. A `unique`, `not_null` or
`accepted_values` test over an empty table always passes. Two things exercise the session and
feedback marts on rows:
- the **unit tests**, which run the model's SQL on fixed inputs;
- the **reference dataset** ([#60](https://github.com/elliepsc/cyclebeat/issues/60)):
  `tests/test_reference_warehouse.py` runs the whole dbt project on a synthetic two-partition
  lake (`tests/reference_dataset.py`) through the real loaders, in CI with `make test-unit`.
  No data test runs over an empty model there (0 of 79), the indicators are compared to values
  computed by hand, and each mart total is reconciled with the count at its source.
  `tests/test_data_guards_fail.py` shows `check_invalid_rating`, `check_invalid_duration` and
  `check_invalid_pattern_buckets` each failing on its own bad value.

On the track and pattern marts, which the demo snapshot fills, the data tests run on real rows.

## Where the data comes from, and which window it covers

Checked on commit c142425 of the #60 branch; the line numbers are those of that commit and will
drift as the files change.

**Production** (Render, `render.yaml`):
- The warehouse the API serves is built **once, at image-build time** (`Dockerfile:40-45`, the
  demo warehouse `RUN`; [ADR-003](adr/adr-003-render-no-disk.md)):
  - the patterns come from `data/cycling_patterns.json`;
  - the tracks come from the committed demo snapshot;
  - the sessions and feedback come from `cyclebeat.cli extract-app`.
- At that step the app store is empty: the same `RUN` first deletes `data/*.db`, and
  `render.yaml` sets no `DATABASE_URL` (`render.yaml:31-37`; the dashboard was not checked). So
  `read_sessions` and `read_feedback` find no store (`cyclebeat/app_store.py:89-90`) and no
  partition is written (`cyclebeat/app_store.py:173-181`).
- **`fct_session` is therefore empty in production**, and so are `mart_feedback_summary` and
  `mart_recent_activity`; `mart_session_kpis` is its one empty-history row. This follows from the
  build; it was not measured on the deployed instance. The MCP tools, and the future copilot, can query
  `fct_session` (`MARTS_ALLOWLIST`, `api/services/warehouse_tools.py:58-60`) and get 0 rows.
- **The sessions created by the post-deploy test do not reach a mart.**
  `tools/deploy.py:205-207` calls `POST /v1/sessions/generate`, which stores the session in the
  app store (`api/services/session.py:110`). Nothing re-extracts at runtime: the container runs
  uvicorn only (`Dockerfile:61`), and `render.yaml` deploys no Airflow. The store is the
  container's own SQLite file, lost when the next deploy starts a fresh container (no disk,
  [ADR-003](adr/adr-003-render-no-disk.md)); the next image is built from an empty store again.

**Locally:**
- `make ingest` (`Makefile:92-96`) extracts the local app store (SQLite `data/cyclebeat_app.db`,
  or Postgres when `DATABASE_URL` is set) into the lake partition of the current UTC day, then
  loads the lake.
- `make dbt` (`Makefile:81-82`) rebuilds the marts.
- `dag_build_warehouse` does the same three steps (`dags/dag_build_warehouse.py:44-77`).
- The marts reflect the store **as of the last extraction**, not as of now.

**Windows.** No mart filters on a date. Every indicator covers everything its staging model
keeps:

| Indicator | Window |
|---|---|
| `mart_session_kpis` (all columns but `avg_satisfaction_pct`) | Every session in any lake partition, latest copy of each (`stg_sessions`), except those with no `session_id` or a `duration_min` of 0 or less: every session extracted since the oldest partition kept |
| `avg_satisfaction_pct`, `int_session_summary` counts | Those sessions × the feedback of the **latest** partition only (`stg_feedback`, #54) |
| `mart_feedback_summary` | The feedback of the latest partition: the whole store at the last extraction, all dates |
| `mart_recent_activity` | The 20 most recent feedback of the latest partition, by `feedback_at` |
| `mart_bpm_coverage`, `mart_data_quality`, `dim_track` | Every track in any partition, latest copy per track (`stg_tracks`, `stg_resolutions`) |
| `mart_pattern_coverage` | The pattern file as last loaded (`save_patterns` deletes then inserts) |

The timestamps these windows rest on are UTC whatever the time zone of the process that wrote
the lake ([#57](https://github.com/elliepsc/cyclebeat/issues/57)). Partitions written before #57
hold local wall time. For tracks and resolutions of the demo snapshot (`dt` fixed), the
re-extraction rewrites the same `dt` and replaces them whole; for sessions and feedback, the next
extraction writes a newer `dt` that supersedes them in staging (`stg_sessions` keeps the latest
`dt` per session, `stg_feedback` reads the latest `dt` only). A past-day live ingest or `resolve`
partition is never rewritten and keeps its local wall time.

## Feedback is read from the latest lake partition only ([#54](https://github.com/elliepsc/cyclebeat/issues/54))

`extract_to_lake` writes a **full copy** of the app-store `feedback` table into each day's `dt`
partition. Reading every partition counted a feedback once per day it was extracted.
`stg_feedback` therefore reads **only the most recent `dt` partition**. The app store has no
UPDATE or DELETE path on `feedback`, so that copy holds every feedback.

Every indicator below that is computed from feedback is checked end to end by
`tests/test_feedback_dedup.py`. The test builds a two-partition lake, loads it, runs dbt and reads
the marts. On the version that read every partition, all four figures it checks came out wrong.
That was measured with the `stg_feedback` unit tests (`dbt/models/staging/unit_tests.yml`) set
aside. With the committed suite, the pre-fix version fails first on those unit tests, and dbt then
skips `stg_feedback` and everything downstream: the figures are never read.

The key `(session_id, session_title, created_at)` is asserted on every row of `stg_feedback` by
`dbt/tests/check_stg_feedback_grain.sql`, and on the mart below.

**Limit.** A row in an older partition only disappears if the store is reset or switched between
two extractions: the file is deleted, or `APP_DB_PATH` or `DATABASE_URL` changes. No make target,
script, test or compose command does that (the list is on [#54](https://github.com/elliepsc/cyclebeat/issues/54)). After such a reset:
- `stg_sessions` still keeps every session it ever saw;
- `stg_feedback` keeps only the latest copy;
- so the older sessions show `feedback_count = 0` in `int_session_summary`.

The two staging models differ on purpose:
- **a session has a key** (`session_id`), so a union over partitions, deduplicated on that key,
  is exact;
- **a feedback has none**, so the only exact copy is one whole partition. A union deduplicated on
  every column broke when the same row was extracted under two timezones: `created_at` was
  written as local wall time until #57, and the same feedback then gave two rows.

## `mart_session_kpis` — global session KPIs

Grain: **exactly one row**, empty history included (`dbt/tests/check_session_kpis_one_row.sql`).
Source: `int_session_summary` (one row per session), itself from `stg_sessions`.
Guards: the unit tests `session_kpis_empty_history` and `session_kpis_with_history`; `not_null`
on the three counts.

| KPI | Definition | Unit | Formula | Empty history |
|---|---|---|---|---|
| `total_sessions` | Sessions persisted by the API | count | `count(*)` | 0 |
| `avg_duration_min` | Mean target duration requested | minutes, 1 dp | `round(avg(duration_min), 1)` | NULL |
| `total_tracks_used` | Track slots across all sessions; a track used twice counts twice | count | `coalesce(sum(track_count), 0)` | 0 |
| `sessions_flagged_review` | Sessions the evaluator flagged `review` | count | `count(*) filter (where verdict = 'review')` | 0 |
| `avg_abs_duration_gap_s` | How far sessions land from their target, either way | seconds, 1 dp | `round(avg(abs(duration_gap_s)), 1)` | NULL |
| `last_session_at` | Most recent session | UTC timestamp | `max(created_at)` | NULL |
| `avg_satisfaction_pct` | Unweighted mean of each session's share of `up` ratings; sessions with no satisfaction rating are skipped. | percent, 1 dp | `round(avg(satisfaction_pct), 1)` | NULL |

## `mart_feedback_summary` — rating distribution

Grain: **one row per `(rating_scale, rating)`** (`dbt/tests/check_feedback_summary_grain.sql`).
Source: `stg_feedback`. The two scales, `satisfaction` (up/down) and `effort` (Great/Okay/Hard),
are never mixed (ADR-009). Guards: `not_null` and `accepted_values` on the key columns,
`not_null` on both measures; all vacuous on an empty warehouse.

| KPI | Definition | Unit | Formula | Empty input |
|---|---|---|---|---|
| `count` | Feedbacks with this rating on this scale, each counted once (latest lake partition) | count | `count(*)` per group | no row (a rating nobody gave has no row) |
| `pct` | This rating's share of its scale; sums to 100 within a scale, never across. | percent, 2 dp | `round(100.0 * count(*) / sum(count(*)) over (partition by rating_scale), 2)` | no row |

## `mart_recent_activity` — the last 20 feedback rows

Grain: **one row represents one feedback**, as held by the latest lake extraction (one insert
into the app-store `feedback` table), among the 20 most recent by `feedback_at`, with the context
of the session it rates when it carries a `session_id`. The key follows from that:
- `session_id` identifies the rated session for API rows;
- `session_title` identifies the row for v1 rows, whose `session_id` is NULL. A v1 row has no
  session context (`level`, `goal`, `duration_min`, `track_count` are NULL): it is attached by
  `session_id` only, like `int_session_summary` (ADR-008; the title fallback was removed in #60);
- `feedback_at` separates two inserts on the same session.

Key: `(session_id, session_title, feedback_at)`, asserted by
`dbt/tests/check_recent_activity_grain.sql` and, over every feedback, by
`dbt/tests/check_stg_feedback_grain.sql`; the same key holds on `int_feedback_enriched`
(`dbt/tests/check_feedback_enriched_grain.sql`, #60). `tests/test_feedback_dedup.py` shows the
three tests failing on a duplicated feedback.

The key **assumes** that two inserts on one session never share a timestamp. API rows take
`datetime.now(UTC)` at µs per insert. v1 rows took DuckDB `now()`, the transaction start, so two v1
rows written in one transaction would collide; no current code path writes v1 rows. One blind
spot closed by #57: an unreadable `created_at` used to be replaced by the extraction time; it
now fails the extraction, naming the row (`cyclebeat/app_store.py`, `_as_datetime`). `rating`,
`rating_scale` and `note` stay out of the key:
- an exact duplicate is identical in every column, so including them would catch nothing more;
- leaving them out makes the test stricter: it also flags a (session, instant) collision between
  two different ratings.

Source: `int_feedback_enriched`. The 20 rows are selected by
`order by feedback_at desc, session_id, session_title limit 20`. The key holds over every feedback
(`check_stg_feedback_grain`), so that order is total, and equal timestamps no longer leave the cut
at row 20 to the engine. `feedback_at` is
exposed, because a table keeps no row order and a reader sorts on it. The mart exposes no
aggregate, only rows. Guards: the key test, `not_null` on `feedback_at`, `rating` and
`rating_scale`, and `accepted_values` on the last two. On an empty warehouse they are vacuous;
the pytest above exercises them.

## `mart_bpm_coverage` — BPM coverage per source

Grain: **one row per `source`** (`unique` on `source`). Source: `stg_resolutions`, which holds
each source's raw opinion, including those that lost E.2 arbitration, and `stg_tracks` for the
denominator. Backs `GET /v1/quality/coverage`.

| KPI | Definition | Unit | Formula | Guards |
|---|---|---|---|---|
| `n_tracks` | Tracks this source gave an opinion on, usable or not | count | `count(*)` per source | `not_null`, `check_bpm_coverage_bounds` |
| `n_usable` | Of those, opinions carrying a positive BPM | count | `count(*) filter (where bpm_raw is not null)` | `not_null`, `check_bpm_coverage_bounds` |
| `pct_of_catalogue` | Usable opinions as a share of the whole catalogue, not of this source's rows | percent, 1 dp | `round(100.0 * n_usable / nullif(n_catalogue, 0), 1)`, `n_catalogue` = `count(*)` of `stg_tracks` | `not_null`, `check_bpm_coverage_bounds` |

## `mart_data_quality` — confidence distribution

Grain: **one row per `confidence_method`**, `unknown` for tracks no source resolved (`unique` on
`confidence_method`). Source: `int_track_resolution`.

| KPI | Definition | Unit | Formula | Guards |
|---|---|---|---|---|
| `n_tracks` | Catalogue tracks in this E.2 branch | count | `count(*)` per branch | `not_null`, `check_data_quality_shares` (sum equals the `dim_track` row count) |
| `pct_of_catalogue` | The branch's share of the catalogue; the shares sum to 100 | percent, 1 dp | `round(count(*) * 100.0 / max(total.n_tracks), 1)`, `total.n_tracks` = all catalogue tracks | `not_null`, `check_data_quality_shares` |
| `avg_confidence` | Mean E.2 confidence of the branch | score 0-1, 3 dp | `round(avg(confidence), 3)` | NULL for `unknown` (no confidence); `check_confidence_matches_method` on the source values |
| `n_with_bpm` | Tracks with a resolved BPM | count | `count(*) filter (where bpm_effective is not null)` | — |
| `n_with_deezer_bpm` | Tracks where Deezer gave a positive BPM | count | `count(*) filter (where has_deezer_bpm)` | — |
| `n_with_librosa_bpm` | Tracks where librosa gave a positive BPM | count | `count(*) filter (where has_librosa_bpm)` | — |
| `n_flagged_review` | Tracks flagged for human review | count | `count(*) filter (where review)` | — |

## `mart_pattern_coverage` — pattern knowledge-base coverage

Grain: **one row per `(phase, effort_bucket, bpm_bucket, resistance_bucket, pattern_type)`**
(`dbt/tests/check_pattern_coverage_grain.sql`). Source: `int_pattern_effort_profile`. Guards:
`not_null` and `accepted_values` on the buckets, `not_null` on `pattern_count`,
`dbt/tests/check_invalid_pattern_buckets.sql`.

The mart describes the knowledge base, not the sessions: nothing in the planner, the API, the
front or the agent tools reads it ([product-spec.md](../product-spec.md), Scope).

A bucket at `unknown` makes `dbt build` red, which skips the downstream models. In production
a red build is not deployed: the image runs `dbt build` at build time (`Dockerfile`, the demo
warehouse `RUN`; [ADR-003](adr/adr-003-render-no-disk.md)). Locally, the tables of the last
green run stay readable, and only the exit code reports the failure.

| KPI | Definition | Unit | Formula | Empty group |
|---|---|---|---|---|
| `pattern_count` | Patterns in the combination | count | `count(*)` per group | no row |
| `avg_bpm` | Mean midpoint of the patterns' BPM windows | BPM, 1 dp | `round(avg(bpm_mid), 1)` | NULL if no pattern has a window |
| `avg_resistance` | Mean resistance level | level (1-10 in the current file), 1 dp | `round(avg(cast(resistance as double)), 1)` | NULL if no pattern has one |

**Rule: an unrecognised value is never put into a default bucket (#55).** It is either mapped
explicitly or rejected as `unknown`, and `check_invalid_pattern_buckets` fails on it, the same
pattern as `rating_scale = 'unknown'` and `check_invalid_rating`. Three cases:

- `effort_bucket` (`stg_patterns`): an `effort` outside the mapping, or a missing one;
- `bpm_bucket` (`int_pattern_effort_profile`): a NULL `bpm_mid`;
- `resistance_bucket` (`int_pattern_effort_profile`): a NULL `resistance`.

**`effort_bucket` mapping and its criterion (owner decision, #55).** The criterion is
resistance, on the `resistance_bucket` thresholds: 3 or less → `low`, 4 to 6 → `medium`, 7 or
more → `high`. BPM is not an effort criterion (`very_hard` is a climb at about 92 BPM,
resistance 8).

| `effort` | patterns | `effort_bucket` |
|---|---|---|
| `easy`, `very_easy` | 6, 6 | `low` |
| `moderate`, `easy_moderate`, `moderate_hard` | 3, 2, 6 | `medium` |
| `hard`, `max`, `very_hard` | 11, 3, 3 | `high` |

Two limits: (i) it is a labelling decision over 2 to 6 patterns per value, not a measurement;
(ii) `easy_moderate` (resistance 4) is the tightest case, and `moderate_hard` loses the "hard"
nuance on a 3-level scale. The criterion labels values, not patterns: `cadence_drill_high`
(`moderate`, resistance 3) and `steady_power` (`moderate_hard`, resistance 7) contradict it and
keep their value's bucket.

## `dim_track` and `fct_session`

They are the E.2 dimension and fact, not KPIs. Grains: `track_id` and `session_id`, each with
`unique` and `not_null`. Their columns are described in `schema.yml`.
