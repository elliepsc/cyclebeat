> dbt-reviewer, pre-PR review of the issue #54 branch, run on 23 October 2026. Diff reviewed: `origin/main...bb1da92` (6 commits, f6b0c9c..bb1da92). Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents` is empty). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commits that follow this one.

---

dbt-reviewer report: `fix/54-feedback-dedup` (HEAD bb1da92) against `origin/main` f6b0c9c

Reference: `git branch --show-current` gives `fix/54-feedback-dedup`. After `git fetch`, `origin/main` is f6b0c9c. I read the whole diff (`git diff origin/main...HEAD`: 6 commits, 10 files). I changed no repo file. All work was done under `/tmp/claude-1000/-home-ellie-projets-cyclebeat/9ccab3cb-61c4-468a-9e1d-4d5be6c5eb4e/scratchpad/review/`. I compared `data/` and `lake/` fingerprints before and after every run: no change.

## 1. Verdict: CHANGES REQUIRED

There is one blocking finding (F1). It comes from my review checklist, not from E.2: a changed model has no stated grain and no key test. The rest of the change is correct:
- The `max(dt)` filter is right.
- Both unit tests fail on the old SQL and pass on the new.
- The pytest is isolated from `data/`, `lake/` and `dbt/target`.
- The key choice holds, but its written justification is wrong (F2).

## 2. Blocking findings

**F1. BLOCKING. `stg_feedback` changed, but it has no grain sentence and no key test. The only key test covers the 20 rows of `mart_recent_activity`.**
- Files: `dbt/models/staging/stg_feedback.sql:1-26` (header, no "one row represents" sentence) and `dbt/models/staging/schema.yml:44-48` (no grain, no key test).
- Rule: "Grain of each new/changed model stated in 1 sentence" and "`unique` + `not_null` on the grain key of every new/changed model. Missing = blocking."
- What escapes today: `dbt/tests/check_recent_activity_grain.sql` reads `ref('mart_recent_activity')`, which is `limit 20`. A deduplication regression on a feedback outside the 20 most recent fails no dbt test. Yet those are the rows that `mart_feedback_summary`, `int_session_summary.feedback_count` and `mart_session_kpis.avg_satisfaction_pct` consume. Only `tests/test_feedback_dedup.py` would catch it, on its own fixture.
- The same gap weakens the tie-break claim. The 20-row cut is deterministic only if the key is unique over all of `int_feedback_enriched`. A key collision sitting across rows 20 and 21 passes the current test.
- Proposed fix:
  - Add the grain sentence to the `stg_feedback` header and its `schema.yml` description, e.g. "one row represents one feedback of the latest `dt` partition".
  - Add `dbt/tests/check_stg_feedback_grain.sql`: `select session_id, session_title, created_at, count(*) from {{ ref('stg_feedback') }} group by 1,2,3 having count(*) > 1`.
  - Use the singular form, because `session_id` is NULL on v1 rows, so `not_null` cannot apply.
  - Extend the second pytest so it expects this test to FAIL as well. It is in the `+mart_recent_activity` selection already. Today the pytest asserts exactly 1 failing line, so that assertion becomes 2.

## 3. Non-blocking findings

**F2. MEDIUM. The key choice is sound, but its justification is backwards and rests on an unstated assumption.**
- Files: `dbt/tests/check_recent_activity_grain.sql:3-10` and `docs/metrics.md` (section `mart_recent_activity`).
- My view of the owner's key `coalesce(session_id, session_title), feedback_at, rating_scale`:
  - **Dropping the `coalesce` is right.**
    - `GROUP BY` compares NULLs as equal, so v1 rows (NULL `session_id`) still collide on `session_title`.
    - For API rows, `session_title` is derived from the id (`api/services/session.py:178,183`, `session-<first 8 of the id>`). So the pair (session_id, session_title) separates exactly what `session_id` alone separates.
    - The `coalesce` would also merge an API id with a v1 title of the same text.
  - **Dropping `rating_scale` is right.** It is a function of `rating` (`stg_feedback.sql:46-52`). Keyed alone, it separates `up` from `Hard` but not `up` from `down`, which is incoherent.
- What is wrong is the wording.
  - The test says that including `rating` "would let two different ratings at the same instant on the same session pass as two rows". Under the grain the agent declared ("one insert"), two such rows ARE two inserts, so passing them is correct.
  - Excluding `rating` and `note` does not help detect exact duplicates, which are identical in every column. It makes the test stricter: it treats a (session, instant) collision as an anomaly.
  - That is defensible only under an assumption the file should state: two inserts on one session never share a `feedback_at`.
- That assumption is false for v1 rows as written.
  - The test says `feedback_at` is "DuckDB `now()` for v1 rows". DuckDB `now()` is the start time of the transaction.
  - Measured (`uv run python`, duckdb 0.10.2): two inserts with `now()` in one transaction, 10 ms apart, gave `count(distinct t) = 1`.
  - So v1 feedback written in one transaction would share `feedback_at` and fail the test. The plan on #54 says no current path produces v1 rows, so the practical risk is low.
- Fix: reword to "the key assumes no two inserts on one session share a timestamp; µs `datetime.now(UTC)` for API rows; v1 `now()` is transaction-start, so v1 rows written in one transaction would collide".

**F3. LOW. The red-run claim in `docs/metrics.md` cannot be reproduced with the committed suite.**
- The claim, in the section "Feedback is read from the latest lake partition only": "On the version that read every partition it failed on all four figures it checks".
- Run 1: `origin/main`'s `stg_feedback.sql` in the HEAD tree, staging `unit_tests.yml` removed. The pytest fails at `assert result.returncode == 0`, because dbt reports `33 of 42 FAIL 1 check_recent_activity_grain`. It never reaches the four figures.
- Run 2: the same, with the grain test also set aside. Then all four figures differ, as claimed:
  - `mart_feedback_summary` `[('down', 1, 25.0), ('up', 3, 75.0)]` instead of `[('down',1,33.33),('up',2,66.67)]`;
  - `feedback_count` `{'s1': 3, 's2': 1}` instead of `{'s1': 2, ...}`;
  - `avg_satisfaction_pct` 83.4 instead of 75.0;
  - `mart_recent_activity` rows 4 instead of 3.
- The claim was true when measured. At 4129a70 the grain test did not exist yet (1a207d8 added it).
- Fix: state the conditions ("measured at 4129a70, before the grain test"), or say that today the build itself goes red first.

**F4. LOW. "32 of 72 data tests" is now stale.**
- `dbt ls --resource-type test` counts **72** on `origin/main` and **74** on HEAD. The two new ones are `check_recent_activity_grain` and `not_null_mart_recent_activity_feedback_at`, and both run on an empty mart.
- Where it appears:
  - `CLAUDE.md`, the "A data test that passes on an empty model..." pitfall. It is a word-for-word copy the owner asked for, so only adding a date is suggested.
  - `docs/ROADMAP.md`, the new `[présentable]` line. It says "qui tournent aujourd'hui" ("that run today") while also citing "mesuré pendant #46" ("measured during #46").
- Suggest "32 of 72, measured during #46" without "aujourd'hui", or re-measure.

**F5. LOW. The pytest writes `dbt/.user.yml` into the profiles dir when that file is missing.**
- In the scratch HEAD tree, the run created `./dbt/.user.yml`. dbt writes its cookie into `--profiles-dir`, here the project's `dbt/`.
- The file is gitignored (`.gitignore:68`). It is not `data/`, `lake/` or `dbt/target`.
- So the docstring's claim ("lake, warehouse, dbt's target and logs all live under tmp_path") holds, but the test is not fully side-effect free on a clean clone.
- Info only. One option is a temp profiles dir holding a copy of `profiles.yml`. I did not check against the dbt docs whether any flag suppresses the cookie.

**F6. INFO. "deduplicated across `dt` by `stg_feedback`" is loose wording.**
- Where: `mart_recent_activity.sql` lines 7-9.
- The model selects one partition; it does not deduplicate. `schema.yml` and `docs/metrics.md` say it accurately ("reads only the most recent `dt` partition").

**F7. INFO. The new `latest` CTE uses `select *`.**
- Where: `stg_feedback.sql:32-36`.
- The checklist forbids `SELECT *`, but every staging model's `source` CTE already does this, and `cleaned` lists its columns explicitly.

**F8. INFO, question for the owner. SQL strings in `tests/test_feedback_dedup.py`.**
- The test holds `select ... from mart_feedback_summary` and similar queries.
- `CLAUDE.md:51` forbids SQL outside `api/repositories/` and `dbt/`. On `origin/main`, 6 test files already query DuckDB the same way (`test_dags.py`, `test_de_core.py`, `test_ingest_pipeline.py`, `unit/test_api_repositories.py`, `unit/test_copilot_guards.py`, `unit/test_mcp_server.py`).
- I am not flagging it as a violation. Should the rule be read as excluding test assertions?

**F9. INFO. Owner decision 2 (prove the CI suite with a run link) cannot be checked yet.**
- `git rev-parse origin/fix/54-feedback-dedup` returns "Needed a single revision": the branch is not pushed.
- The test is collected by `make test-unit` (`pyproject.toml:105` `testpaths = ["tests"]`, `.github/workflows/ci.yml:75`). It took about 9 s for both tests.

## 4. What was checked and how

- **`max(dt)` correctness:**
  - **Type:** `dt DATE` in `_FEEDBACK_DDL` (`cyclebeat/warehouse.py:74-83`). Measured in the warehouse copy via `information_schema.columns`: `('dt','DATE')`.
  - **Where dt comes from:** always the `dt=` hive directory (`lake.py:45-49`). The value is always today's UTC date (`app_store.py:170`), and nothing can pass an older dt: `cli.py:122` and `dag_build_warehouse.py:55` call `extract_to_lake()` with no dt. So an Airflow backfill cannot write an older dt.
  - **NULL dt:** measured on `(NULL, 2026-10-22, 2026-10-23, 2026-10-23)`, the filter keeps 2 rows. NULL is ignored by `max` and dropped by `=`.
  - **Empty source:** 0 rows (measured).
  - **Uncorrelated subquery:** evaluated once. Correct.
- **Unit tests are red on old code:**
  - Ran `dbt test --select "stg_feedback,test_type:unit"` with `origin/main`'s `stg_feedback.sql`. Both FAIL.
  - `same_feedback_in_two_partitions`: an extra `+++,s1,up,...123456` row, so 2 rows instead of 1.
  - `only_latest_partition_kept`: an extra `+++,s_old,down,...` row.
  - On HEAD both PASS (in `make dbt`). The second test also rules out option (b), deduplication on every column, since `s_old` would survive it. Test 1 alone would accept any deduplication method; together the two prove what their descriptions say.
  - Under `dbt build` the first failure SKIPs the second test, so `dbt test` is the right command to quote both in the PR.
- **Join fan-out:** `int_feedback_enriched.sql:43-46` joins with an OR condition to `stg_sessions`, which is unique on `session_id` (`unique_stg_sessions_session_id` PASS). Each branch matches at most one session, so no fan-out.
- **NULL ordering claim:** measured. DuckDB orders NULLs last for both `asc` and `desc`, and `feedback_at` is `not_null`-tested anyway.
- **Isolation:**
  - The pytest ran in the repo (`uv run pytest tests/test_feedback_dedup.py`, exit 0, 2 passed).
  - `find dbt/target dbt/logs dbt/.user.yml -printf '%p %s %T@'` gave the same output before and after. The `data/` and `lake/` fingerprints were also identical.
  - The second pytest (key test must fail) passes on HEAD: exactly one FAIL line, `check_recent_activity_grain`.
- **Gates:**
  - `RUNTIME_DB_PATH=<scratch>/runtime.duckdb make dbt`: exit 0, `Done. PASS=95 WARN=0 ERROR=0 SKIP=0 TOTAL=95`, including both new unit tests, `check_recent_activity_grain` and `not_null_mart_recent_activity_feedback_at`. The warehouse copy holds 0 feedback and 0 sessions, so the data tests are vacuous there, as the docs say.
  - `make lint`: exit 0, "All checks passed!", "0 dead link(s)".
  - Not run: `typecheck`, the full `test-unit`, `eval`, `contract`, because the diff does not touch `api/`.
- **Doc claims against code:**
  - `schema.yml` (mart grain, key, tie-break, guards) matches the SQL and the `make dbt` test list.
  - `sources.yml` is accurate.
  - `metrics.md` guards list matches. Its "four figures" claim: see F3.
  - The `stg_feedback` header's limit paragraph is consistent with the paths listed on #54 and with `stg_sessions.sql:14-25`.
  - ROADMAP: "PR #56" for #46 is consistent with the merge f6b0c9c.
- **E.2 contracts:** the diff does not touch `normalize_bpm`, zones, confidence, or the schemas of raw.tracks, raw.resolutions, dim_track, fct_session, fct_llm_calls or fct_agent_runs. No E.2 violation.

## 5. Downstream impact

- **Changed models:** `stg_feedback` (now reads 1 partition), and through it `int_feedback_enriched`, `int_session_summary` (`feedback_count`, per-scale counts, `satisfaction_pct`), `mart_feedback_summary`, `mart_session_kpis.avg_satisfaction_pct` and `mart_recent_activity`.
- **New column:** `mart_recent_activity.feedback_at` is additive.
- **No consumers outside dbt:**
  - `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py:58-60`) is `{dim_track, fct_session, mart_bpm_coverage, mart_data_quality}`, so none of the affected marts are reachable by `query_marts` or MCP.
  - A grep of `api/`, `frontend/src` and `mcp-server` for these marts finds only comments in `api/repositories/feedback.py:16` and `api/services/session.py:187`.
  - No endpoint or screen is affected, and the `openapi.yaml` contract is unchanged.
- **Behaviour change:** in dev, after a store reset or switch between two extractions, older sessions show `feedback_count = 0`. This is documented in the model header and `docs/metrics.md`.

Scratch artefacts are in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/9ccab3cb-61c4-468a-9e1d-4d5be6c5eb4e/scratchpad/review/`:
- `make_dbt.log`: the `make dbt` run.
- `base_unit2.log`: the red unit-test run.
- `base-model/`: HEAD with `origin/main`'s `stg_feedback.sql` (staging unit tests set aside), used for the red pytest runs.
- `head/` and `main/`: the trees used for the 72 vs 74 test count.
