# Metrics — the KPIs the marts expose

Every figure a dbt mart publishes, with its definition, grain, formula, source and the tests
that guard it. The models are the reference (`dbt/models/marts/`); column-level detail is in
[`dbt/models/marts/schema.yml`](../dbt/models/marts/schema.yml). A mart's grain is stated in its
`schema.yml` description and guarded by a test (issue #46).

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
`accepted_values` test over an empty table always passes. On those marts, the guards that prove
a KPI's definition are the **unit tests**, which run the model's SQL on fixed inputs. On the
track and pattern marts, which the demo snapshot fills, the data tests run on real rows.

## Known defect: feedback counted per lake partition (#54)

`stg_feedback` does not deduplicate across lake partitions, unlike `stg_sessions`; read in the
code, not measured (the demo warehouse holds no feedback). Every indicator computed from feedback
below is marked **known defect, see [#54](https://github.com/elliepsc/cyclebeat/issues/54)**.

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
| `avg_satisfaction_pct` | Unweighted mean of each session's share of `up` ratings; sessions with no satisfaction rating are skipped. **Known defect, see [#54](https://github.com/elliepsc/cyclebeat/issues/54).** | percent, 1 dp | `round(avg(satisfaction_pct), 1)` | NULL |

## `mart_feedback_summary` — rating distribution

Grain: **one row per `(rating_scale, rating)`** (`dbt/tests/check_feedback_summary_grain.sql`).
Source: `stg_feedback`. The two scales, `satisfaction` (up/down) and `effort` (Great/Okay/Hard),
are never mixed (ADR-009). Guards: `not_null` and `accepted_values` on the key columns,
`not_null` on both measures; all vacuous on an empty warehouse.

| KPI | Definition | Unit | Formula | Empty input |
|---|---|---|---|---|
| `count` | Feedback rows with this rating on this scale. **Known defect, see [#54](https://github.com/elliepsc/cyclebeat/issues/54).** | count | `count(*)` per group | no row (a rating nobody gave has no row) |
| `pct` | This rating's share of its scale; sums to 100 within a scale, never across. **Known defect, see [#54](https://github.com/elliepsc/cyclebeat/issues/54).** | percent, 2 dp | `100 * count / sum(count) over (partition by rating_scale)` | no row |

## `mart_recent_activity` — the last 20 feedback rows

Grain: **not guaranteed**. A row is meant to be one feedback submission, but the source has no
identity: the app-store `feedback` table has no key, API rows carry `session_id` while v1 rows
carry only `session_title`, and a feedback can repeat across lake partitions; see
[#54](https://github.com/elliepsc/cyclebeat/issues/54). No key test until #54 declares the grain.
Source: `int_feedback_enriched`, ordered by `feedback_at` descending, `limit 20`. It exposes no
aggregate, only rows. **Known defect, see [#54](https://github.com/elliepsc/cyclebeat/issues/54).**
Guards: `not_null` and `accepted_values` on `rating` and `rating_scale`; vacuous on an empty
warehouse.

## `mart_bpm_coverage` — BPM coverage per source

Grain: **one row per `source`** (`unique` on `source`). Source: `stg_resolutions`, which holds
each source's raw opinion, including those that lost E.2 arbitration, and `stg_tracks` for the
denominator. Backs `GET /v1/quality/coverage`.

| KPI | Definition | Unit | Formula | Guards |
|---|---|---|---|---|
| `n_tracks` | Tracks this source gave an opinion on, usable or not | count | `count(*)` per source | `not_null`, `check_bpm_coverage_bounds` |
| `n_usable` | Of those, opinions carrying a positive BPM | count | `count(*) filter (where bpm_raw is not null)` | `not_null`, `check_bpm_coverage_bounds` |
| `pct_of_catalogue` | Usable opinions as a share of the whole catalogue, not of this source's rows | percent, 1 dp | `100 * n_usable / nullif(count(stg_tracks), 0)` | `not_null`, `check_bpm_coverage_bounds` |

## `mart_data_quality` — confidence distribution

Grain: **one row per `confidence_method`**, `unknown` for tracks no source resolved (`unique` on
`confidence_method`). Source: `int_track_resolution`.

| KPI | Definition | Unit | Formula | Guards |
|---|---|---|---|---|
| `n_tracks` | Catalogue tracks in this E.2 branch | count | `count(*)` per branch | `not_null` |
| `pct_of_catalogue` | The branch's share of the catalogue; the shares sum to 100 | percent, 1 dp | `100 * count(*) / total tracks` | `not_null`, `check_data_quality_shares` |
| `avg_confidence` | Mean E.2 confidence of the branch | score 0-1, 3 dp | `round(avg(confidence), 3)` | NULL for `unknown` (no confidence); `check_confidence_matches_method` on the source values |
| `n_with_bpm` | Tracks with a resolved BPM | count | `count(*) filter (where bpm_effective is not null)` | — |
| `n_with_deezer_bpm` | Tracks where Deezer gave a positive BPM | count | `count(*) filter (where has_deezer_bpm)` | — |
| `n_with_librosa_bpm` | Tracks where librosa gave a positive BPM | count | `count(*) filter (where has_librosa_bpm)` | — |
| `n_flagged_review` | Tracks flagged for human review | count | `count(*) filter (where review)` | — |

## `mart_pattern_coverage` — pattern knowledge-base coverage

Grain: **one row per `(phase, effort_bucket, bpm_bucket, resistance_bucket, pattern_type)`**
(`dbt/tests/check_pattern_coverage_grain.sql`). Source: `int_pattern_effort_profile`. Guards:
`not_null` and `accepted_values` on the buckets, `not_null` on `pattern_count`.

| KPI | Definition | Unit | Formula | Empty group |
|---|---|---|---|---|
| `pattern_count` | Patterns in the combination | count | `count(*)` per group | no row |
| `avg_bpm` | Mean midpoint of the patterns' BPM windows | BPM, 1 dp | `round(avg(bpm_mid), 1)` | NULL if no pattern has a window |
| `avg_resistance` | Mean resistance level | level (1-10 in the current file), 1 dp | `round(avg(resistance), 1)` | NULL if no pattern has one |

## `dim_track` and `fct_session`

They are the E.2 dimension and fact, not KPIs. Grains: `track_id` and `session_id`, each with
`unique` and `not_null`. Their columns are described in `schema.yml`.
