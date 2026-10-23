> dbt-reviewer, pre-PR review of the issue #46 branch, run on 23 October 2026. Diff reviewed: `origin/main...17d41f2` (one commit, 17d41f2). Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main` (last changed in a7a2ad4, unchanged on the branch). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commit that follows this one.

---

# dbt-reviewer: branch `fix/46-dbt-semantic-layer` (17d41f2) against `origin/main`

Reference: current branch `fix/46-dbt-semantic-layer`. `origin/main` was fetched before the review, and `git diff origin/main...HEAD` holds one commit, 17d41f2, touching 9 files. I read the whole diff, every mart and intermediate model, every staging model, `cyclebeat/e2.py`, the loader in `cyclebeat/warehouse.py`, the dbt tests the docs cite, and issues #46 and #54.

## 1. Verdict

**APPROVED WITH RESERVATIONS**

- **E.2 contracts:** no violations. The models' SQL leaves confidence, normalization and zones untouched. The schemas of `dim_track` and `fct_session` keep the same columns (checked against `describe`), and no test was weakened or removed.
- **Counter fix:** proven. The empty-history unit test fails on the `origin/main` mart and passes on HEAD.
- **Grain tests:** each one I mutated fails when a duplicate row is injected.
- **Reservations:** they are about doc claims the code does not support (findings 1 to 3). One of them decides which acceptance criteria the PR can tick.

## 2. Blocking findings

None. No E.2 contract is broken, no test was weakened, and every new or changed mart has a stated grain. The one mart without a grain key test, `mart_recent_activity`, is an owner decision recorded in #46 (3rd comment) and tracked in #54.

## 3. Non-blocking findings (reservations: 1-3 should be fixed before the PR, the rest can wait)

1. **Two docs claim every mart has a grain test. `mart_recent_activity` does not.**
   - `dbt/models/marts/schema.yml`, top comment (lines 42-45 of the diff): "Every mart states its grain in its description and has a test that guarantees it".
   - `docs/metrics.md`, intro: "A mart's grain is stated in its `schema.yml` description and guarded by a test (issue #46)".
   - Both contradict the `mart_recent_activity` entry in the same files ("Grain NOT guaranteed ... No key test until #54").
   - Fix: add "except `mart_recent_activity` (#54)" to both sentences.

2. **Acceptance criterion 2 of #46 is only partly met, and so is FR-12.**
   - The criterion reads "Every mart declares its grain, and a uniqueness test guarantees it". This is false for `mart_recent_activity`.
   - FR-12 in `product-spec.md` says the same: "every mart is described in `schema.yml` with its grain and a uniqueness test".
   - The owner deferred this to #54, so it is not a defect of the diff. But the PR description must leave criterion 2 unticked, or tick it with that exception spelled out, and must not mark FR-12 as delivered.
   - Conflict flagged: the spec (higher source) and the owner decision differ until #54 lands.

3. **`docs/demo.md` line 176 is now stale.** It still says in the present tense that "`mart_session_kpis` returns NULL, not 0, for two counters on an empty history", and the diff makes that false. Line 67 is framed as history ("the **original** mart") and can stay. Fix: add "fixed in #46" to line 176.

4. **Four formulas in `docs/metrics.md` are not character-for-character the SQL.** The brief asks for an exact match. The meaning is the same in each case, and the rounding is given in the Unit column.
   - `mart_feedback_summary.pct`
     - Doc: `100 * count / sum(count) over (partition by rating_scale)`
     - SQL: `round(100.0 * count(*) / sum(count(*)) over (partition by rating_scale), 2)`
   - `mart_bpm_coverage.pct_of_catalogue`
     - Doc: no `round(..., 1)`.
   - `mart_data_quality.pct_of_catalogue`
     - Doc: `100 * count(*) / total tracks`
     - SQL: `round(count(*) * 100.0 / max(total.n_tracks), 1)`
   - `mart_pattern_coverage.avg_resistance`
     - Doc: no `cast(resistance as double)`.
   - The other formulas match the SQL exactly.

5. **`mart_bpm_coverage.pct_of_catalogue` description claims "no row exists then anyway" on an empty catalogue.** The code does not guarantee that. The mart's rows come from `stg_resolutions`, independently of `stg_tracks`, and `dbt/tests/check_bpm_coverage_bounds.sql` itself says orphan track_ids are "reachable". Rewrite as: "NULL when the catalogue is empty; resolutions without tracks would then still produce rows, and `not_null` would fail".

6. **`dim_track.source_platform` description leaves out a value the code produces.** It says "`deezer` for the catalogue". `cyclebeat/sources/csv_source.py:21` writes `SOURCE_PLATFORM = "csv"`, and `track_id` in the same entry mentions `csv:` slugs. Measured on the scratch warehouse: 48 rows, all `deezer`. Fix: "`deezer`, or `csv` for a manual import".

7. **`dim_track.zone` description leaves out the rounding rule.** `cyclebeat/e2.py` `zone_for` rounds `bpm_effective` to the nearest integer before banding (its docstring calls this a DISAMBIGUATION), so 115.4 is Z2 and 115.6 is Z3. Your brief asks every description to state its computation rule; add "after rounding to the nearest integer (`cyclebeat.e2.zone_for`)". The added sentence "NULL exactly when bpm_effective is NULL" is correct (`resolve` sets both to None together).

8. **`mart_recent_activity` description promises an order the table does not keep.** "newest first" cannot hold on read: the mart is materialized as a table (`dbt_project.yml`), and a table keeps no row order. The sort key `feedback_at` is not exposed either; only `feedback_date` (day precision) is, so a consumer cannot re-sort within a day. `order by feedback_at desc limit 20` also picks an arbitrary set when timestamps tie. This is model design from before this PR. Only the doc wording is new. Suggest "selected as the 20 most recent by `feedback_at`" and a note for #54.

9. **`mart_pattern_coverage.effort_bucket` description is accurate, but the logic it describes is suspect (behaviour predates this PR, out of scope, question for the owner).**
   - The description says "an unmapped effort falls into `medium`". Measured on the scratch warehouse, 17 of 40 patterns are unmapped and land in `medium`: `very_easy` 6, `moderate_hard` 6, `very_hard` 3, `easy_moderate` 2.
   - So `very_easy` and `very_hard` patterns are bucketed `medium`. The mapping in `stg_patterns.sql` does not cover the vocabulary of `data/cycling_patterns.json`.
   - No new rule is proposed here: this needs an issue and a decision.

10. **Guards listed in `docs/metrics.md` are incomplete.** For `mart_data_quality.n_tracks` it lists only `not_null`, but `dbt/tests/check_data_quality_shares.sql` also asserts `sum(n_tracks) = count(dim_track)`. Add it.

11. **The diff adds 7 more uses of a syntax dbt 1.11 marks deprecated.** The new `accepted_values` entries pass `values:` at the top level. The build log shows `MissingArgumentsPropertyInGenericTestDeprecation: 18 occurrences`. This follows the repo's existing convention and the build is green. A later migration to the `arguments:` form is a `[présentable]` item.

12. **The new level/goal descriptions on `fct_session` are not tested at mart level.** "Never NULL" plus the E.3 enum are asserted on `stg_sessions` (`dbt/models/staging/schema.yml`). `fct_session` is a 1:1 projection, so they hold by construction. Acceptable; noted because criterion 1 asks for these tests "where the E.2 contract implies them", and E.2 (`docs/archive/CYCLEBEAT_PLAN_V3.md:434`) lists only "params user (niveau/objectif/durée)" for `fct_session`.

13. **Not vacuous, unlike the others:** the 4 data tests on `mart_session_kpis` (`check_session_kpis_one_row` and three `not_null`) run over the mart's one row, which on a 0-session warehouse is exactly the empty-history case. They therefore check the `coalesce` on real data. The coding agent's list of vacuous tests is correct (see section 4) and rightly leaves them out. Worth saying in the PR.

Descriptions, measured: all 8 marts document every column, with nothing missing or extra and in the same order as the table (`describe main.<mart>` compared with the YAML). Apart from findings 5 to 8, every new description gives a unit, what NULL means or a rule, and I checked each against the SQL or Python behind it: `has_*` (coalesce >0), `n_sources_agree` (0/1/2+ per `e2.resolve`), `review` (only the last branch of `resolve`), the `bpm_bucket` and `resistance_bucket` boundaries (`between` is inclusive, so 130 is moderate), `duration_s`, `session_title` (`api/services/session.py:190`), `session_id` (`uuid4().hex`), the UTC timestamps (`datetime.now(UTC)`, `cli.py`/`app_store.py` stamps) and `preview_url` (0 of 48 non-NULL, measured).

## 4. What was checked and how

All commands ran on copies under `/tmp/claude-1000/-home-ellie-projets-cyclebeat/a037dff7-7f79-4418-bdcf-38be7a30259b/scratchpad/review/`. I never touched `data/`, `lake/` or the coding agent's warehouse. `git status --porcelain` is empty after the review. Only the gitignored `dbt/target/` was regenerated.

- **`make dbt` on a copy of the scratch warehouse**
  - Command: `RUNTIME_DB_PATH=<scratch>/review/wh.duckdb make dbt`
  - Result: exit 0, `Done. PASS=91 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=91`
  - Contents: 17 models, 72 data tests, 2 unit tests. Matches the claim.
- **Vacuous data tests**
  - Method: read the manifest, and for each test count the rows of the models it depends on.
  - Result: 32 of 72 run only over empty models. `stg_sessions` 11, `mart_feedback_summary` 7, `stg_feedback` 5, `fct_session` 5, `mart_recent_activity` 4. Matches the claim.
- **The unit test catches the old bug**
  - Method: rebuilt a project copy (`git archive HEAD dbt`) with `mart_session_kpis.sql` taken from `origin/main`, then ran `dbt build --select mart_session_kpis`.
  - Result: `FAIL 1 mart_session_kpis::session_kpis_empty_history ... actual differs from expected`. On HEAD both unit tests pass.
- **Grain tests fail on duplicates**
  - Method: in a second copy (`wh2.duckdb`), injected a duplicate row into each of 4 marts and ran their grain tests: `mart_pattern_coverage` (29 real rows), `mart_feedback_summary`, `mart_session_kpis`, `mart_data_quality`.
  - Result: all 4 return FAIL 1: `check_pattern_coverage_grain`, `check_feedback_summary_grain`, `check_session_kpis_one_row`, `unique_mart_data_quality_confidence_method`.
  - Not re-mutated by me: `unique` on `dim_track`, `fct_session`, `mart_bpm_coverage`. Those tests existed before this PR on `origin/main`.
- **Expected values of `session_kpis_with_history`, recomputed by hand**
  - avg_duration_min: (30+45+60)/3 = 45.0
  - total_tracks_used: 8+12+15 = 35
  - sessions_flagged_review: 2
  - avg_abs_duration_gap_s: (10+20+0)/3 = 10.0
  - avg_satisfaction_pct: (100+50)/2 = 75.0
  - last_session_at: 2026-10-03 18:30
  - All correct. The fixture really does exercise `abs()` and skipping NULL satisfaction.
- **Values measured on the scratch warehouse**
  - `mart_data_quality`: single_source 27 (56.3 %), cross_validated 12, unknown 5 with `avg_confidence` NULL, librosa_arbitrated 4.
  - `mart_bpm_coverage`: deezer 48/19 (39.6 %), librosa 40/40 (83.3 %).
  - Consistent with the descriptions.
- **Ghost reference:** `check_confidence_values.sql` no longer appears in `dbt/`, and every `dbt/tests/*.sql` the diff cites exists.
- **Unit-test support:** I did not re-check the official dbt docs. The measured fact is that `rows: []` runs on the locked dbt-core 1.11.12 / dbt-duckdb 1.8.1 and fails as expected on the old SQL.
- **Not run by me:** lint (with `check_links`), typecheck, test-unit, eval, contract. These are outside this reviewer's scope and remain for the definition of done.

## 5. Downstream impact

- **`mart_session_kpis`:** the counter fix changes only `total_tracks_used` and `sessions_flagged_review` on an empty history, from NULL to 0. Their types do not change (`count(*) filter` is BIGINT, as `sum` of ints was HUGEINT/BIGINT). No consumer was found: no endpoint or screen reads this mart, and it is not on `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py:58`), so neither the copilot nor the MCP tools can read it. Mentioned only in docs: `docs/demo.md` (see finding 3), `docs/ai-workflow.md` (history), ADR-008.
- **`dim_track`, `fct_session`, `mart_bpm_coverage`, `mart_data_quality`:** descriptions only, no SQL change. Downstream `/v1/quality/*`, the planner, `query_marts` and the MCP server are unaffected.
- **No E.2 schema change**, so no breaking change and no impact analysis is required.
- **New artefacts:** `dbt/models/marts/unit_tests.yml` and three singular tests in `dbt/tests/`. They add 5 nodes to `dbt build` (2 unit tests, 3 data tests) and about 1 s on the scratch warehouse.
