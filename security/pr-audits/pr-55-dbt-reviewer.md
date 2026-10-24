> dbt-reviewer, pre-PR review of the issue #55 branch, run on 24 October 2026. Diff reviewed: `origin/main...1480f5b` (3 commits, 8e5dd52, eff11e8, 1480f5b). Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents/dbt-reviewer.md` is empty). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commits that follow this one.

---

# dbt-reviewer: `fix/55-pattern-effort-bucket` against `origin/main` (#55)

Reference branch: `fix/55-pattern-effort-bucket` @ `1480f5b`, checked against `origin/main` after a `git fetch` on 2026-10-24. Diff read in full: `git diff origin/main...HEAD`, 3 commits (`8e5dd52`, `eff11e8`, `1480f5b`), 11 files. `.claude/agents/dbt-reviewer.md` is not touched by the diff. The issue and its 3 comments were read with `gh issue view 55 --json title,body,comments`. The owner's decisions come from the last comment.

## 1. Verdict

**APPROVED WITH RESERVATIONS.**

The fix follows the owner's rule and mapping. All four new unit tests fail on the old code and pass on the new code. I reproduced the singular test failing on injected rows. The docs match the SQL.

One finding is blocking under this reviewer's checklist: B1, a changed model with no grain sentence and no key test. The gap predates this branch, and the fix is a few lines of YAML. The owner may decide to defer it to its own issue. If so, the deferral should be written down, not left implicit.

## 2. Blocking findings

**B1. `int_pattern_effort_profile` is changed but has no stated grain and no `unique` + `not_null` on its key** (checklist: "Structure & grain", "Tests — missing = blocking")
- `dbt/models/intermediate/int_pattern_effort_profile.sql` is changed by this diff (two `when ... is null then 'unknown'` branches).
- No `.yml` declares the model: `grep -rn int_pattern_effort_profile dbt/models --include=*.yml` finds only the two new entries in `dbt/models/intermediate/unit_tests.yml`. So there is no description, no grain sentence and no key test.
- Its header comment ("maps each pattern to a BPM bucket for coach decision analysis") states no grain. It also leaves out the resistance bucket.
- The new singular test `dbt/tests/check_invalid_pattern_buckets.sql` reads this model by `id`. A key test would make a fan-out here visible too.
- Proposed fix (YAML only, no SQL change):
  - add an `int_pattern_effort_profile` entry with the sentence "one row represents one pattern of `stg_patterns` (`id`)";
  - add `not_null` and `unique` on `id`;
  - show the new key test failing once on an injected duplicate, as CLAUDE.md requires.
- Related but not blocking: `stg_patterns` has its key tests (`not_null`, `unique` on `id`, in `dbt/models/staging/schema.yml`). Its description ("40-pattern knowledge base with effort_bucket derived field.") is still not a grain sentence.
- Pre-existing: on `origin/main` the model had no YAML entry either. It is blocking here only because the diff changes the model.

No E.2 contract violation: confidence, normalization, zones and E.2 schemas are not touched. No test was weakened or removed, and no expected value was changed to go green (see N1).

## 3. Non-blocking findings (by severity)

**N1 (medium, to note in the PR). `accepted_values` was extended with `unknown` on 4 columns**
- Files: `dbt/models/staging/schema.yml` (`effort_bucket`) and `dbt/models/marts/schema.yml` (`effort_bucket`, `bpm_bucket`, `resistance_bucket`).
- Taken alone, this lets a new value pass those 4 tests.
- **It is not a weakening:**
  - on `origin/main`, `unknown` could not be produced (the old CASEs always fell back to a real bucket);
  - every row that is now `unknown` is rejected by `check_invalid_pattern_buckets` (severity `error` by default), which I reproduced (section 4);
  - it follows the repo's existing pattern: `rating_scale` accepts `unknown` in `dbt/models/staging/schema.yml` and in `dbt/models/marts/schema.yml`, and `check_invalid_rating.sql` gates it.
- Net effect: the build is stricter than before. The PR should say this in one sentence, so a reader does not take the extension for a relaxed test.

**N2 (medium, docs accuracy). The new `docs/ROADMAP.md` line on `save_patterns` overstates the BPM case**
- The line says a `0.0` BPM window "serait classée `slow` … sans être signalée".
- That is wrong for BPM. A missing `bpm_range` gives `bpm_min = bpm_max = 0.0`. `dbt/tests/check_pattern_bpm_range.sql` already fails on that (`bpm_min >= bpm_max or bpm_min < 40`).
- It is correct for `resistance = 0`: bucketed `light`, and no test flags it.
- It is correct that `effort = ''` is no longer a silent case: it now comes out `unknown`.
- Proposed rewording: restrict the "sans être signalée" claim to `resistance`.

**N3 (low). The singular test passes vacuously on today's data**
- On the scratch warehouse it returns 0 rows, as expected: the pattern file has no unmapped effort and no NULL `bpm_mid` or `resistance`.
- It also passes on the old code, which never emitted `unknown`.
- It only counts as evidence because it fails on injected rows. Your 3-row injection measurement and my reproduction (section 4) both show that. This is acceptable and follows the CLAUDE.md pitfall.
- The NULL `bpm_mid` and NULL `resistance` branches cannot be reached through today's ingestion (`db/runtime.py` `save_patterns` writes 0, not NULL). The intermediate unit tests are what exercise those branches, and `dbt/models/intermediate/unit_tests.yml` says so in its header. That gap is tracked by the new ROADMAP line.

**N4 (low). The brief's count of red tests is too low**
- The brief says 3 of the 4 unit tests were run red on the old code.
- On my run all 4 fail against the `origin/main` SQL, including `stg_patterns_explicit_effort_mapping`: on the old code `very_easy` and `very_hard` come out `medium`.
- When the PR quotes the red outputs, it should say 4/4, or explain why only 3 are quoted.

**N5 (low). Grain of `mart_pattern_coverage` now includes `unknown`**
- `unknown` is now a possible value in 3 of the 5 grain columns (effort, BPM, resistance buckets).
- The grain is unchanged. `dbt/tests/check_pattern_coverage_grain.sql` (singular `GROUP BY … HAVING count(*) > 1`) still holds, and it passed on the injected copy.
- Under `make dbt` (`dbt build`), a failing `check_invalid_pattern_buckets` (attached to `int_pattern_effort_profile`) skips `mart_pattern_coverage`. Because the mart is a `table`, the **previous run's table stays in place** while the build is red. This fails closed (non-zero exit), but a reader of the stale table gets no warning.
- The `docs/metrics.md` grain sentence could add: "`unknown` in a bucket fails the build". Optional.

**N6 (low, pre-existing). Business logic in staging**
- The `effort` → `effort_bucket` CASE sits in `stg_patterns`, while the checklist says staging is 1:1 with the source and holds no business logic. The diff keeps it where it was; moving it would widen the scope.
- `select * from {{ source(...) }}` and `select * from cleaned` in `stg_patterns.sql`, and `select *` in the `patterns` CTE of `int_pattern_effort_profile.sql`, also predate this branch.
- This is a question for the owner (a possible future issue), not a fix to make in this PR.

**N7 (info). Still to do before the PR**
- The plan's step 4 is not on the branch yet: the `docs/ai-workflow.md` entry and this review committed under `security/pr-audits/`. The diff does not touch either file.
- The FR-12 line is planned for after the PR is created, as the plan says.

### Conformance to the issue and the owner's decisions: all confirmed

**Rule in the file headers and docs**
- The rule is written in the header of `dbt/models/staging/stg_patterns.sql`.
- It is written in `docs/metrics.md` and covers all three cases.
- A comment in `int_pattern_effort_profile.sql` points to it.

**Mapping**
- `very_easy` → low, `easy_moderate` → medium, `moderate_hard` → medium, `very_hard` → high, exactly as the owner decided.
- The resistance criterion and its two limits (i) and (ii) are written in both places.

**Contradicting patterns**
- Measured on the scratch warehouse, exactly 2 patterns contradict the resistance criterion: `cadence_drill_high` (`moderate`, resistance 3) and `steady_power` (`moderate_hard`, resistance 7).
- That is at most 3, so no stop was needed. Both are listed in the docs and neither was modified.

**`light`, `tempo`, `explosive`**
- They are removed, and a one-line comment gives the reason.
- Verified: 0 matches for `"effort": "light|tempo|explosive"` in both versions of `data/cycling_patterns.json` (`912e8e4`, `6a6bc5f`); `explosive` appears 9 times as a `coach_tone`.

**Other owner-requested changes**
- The NULL `resistance` and NULL `bpm_mid` cases are widened into `unknown` as asked, each with a unit test.
- The `product-spec.md` Scope paragraph matches the agreed content.
- The two `[présentable]` ROADMAP lines and the two `CLAUDE.md` lines are present. The `CLAUDE.md` lines are in their own first commit, `8e5dd52`.

**Docs against SQL**
- The `docs/metrics.md` table counts match the warehouse: low 6+6, medium 3+2+6, high 11+3+3.
- The bucket descriptions in `dbt/models/marts/schema.yml` match the CASEs.
- `docs/metrics.md` still says `avg_bpm` is "NULL if no pattern has a window"; ingestion can never produce that. This predates the branch and is covered by the new ROADMAP line.

**SQL location**
- SQL only in `dbt/`.

## 4. What was checked and how

All runs used copies of `data/cyclebeat_runtime.duckdb` in the session scratchpad. Nothing was written to `data/` or `lake/`, and no repo file was modified (`git status --short` is empty).

1. `RUNTIME_DB_PATH=<scratch>/review.duckdb make dbt`: exit 0, `Done. PASS=101 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=101`. This matches your PASS=101. All 4 new unit tests, `check_invalid_pattern_buckets` and the extended `accepted_values` tests show PASS.
2. Read-only queries on that copy:
   - `mart_pattern_coverage` has 27 rows;
   - `sum(pattern_count)` by `effort_bucket`: high 17 (11 rows), low 12 (7 rows), medium 11 (9 rows). This matches your "after" figures;
   - patterns whose resistance contradicts their bucket: `cadence_drill_high` and `steady_power` only;
   - resistance by `effort`: `very_easy` 1-2, `easy` 3-3, `easy_moderate` 4-4, `moderate` 3-5, `moderate_hard` 5-7, `hard` 7-8, `max` 7-10, `very_hard` 8-8.
3. Red run on the old code: a copy of the dbt project in the scratchpad, with `stg_patterns.sql` and `int_pattern_effort_profile.sql` replaced by their `origin/main` versions (`git show origin/main:<file>`) and the branch's tests kept.
   - `dbt run --select +mart_pattern_coverage`: exit 0.
   - `dbt test --select stg_patterns int_pattern_effort_profile mart_pattern_coverage check_invalid_pattern_buckets`: exit 1, `PASS=15 ERROR=4`. The 4 failures are `int_pattern_effort_profile_null_bpm_mid_is_rejected`, `int_pattern_effort_profile_null_resistance_is_rejected`, `stg_patterns_explicit_effort_mapping` and `stg_patterns_unknown_effort_is_rejected`, each reported as "actual differs from expected".
   - Also seen: `dbt build` on that copy stopped at the first failing unit test and skipped 21 nodes, which confirms the new `CLAUDE.md` pitfall line.
4. Injection on new code, on a third copy:
   - inserted 3 rows into `main.patterns`, cloned from `steady_power`: `effort = 'brutal'`, `resistance = NULL`, `bpm_max = NULL`;
   - `dbt run --select +mart_pattern_coverage`: exit 0;
   - `dbt test --select check_invalid_pattern_buckets check_pattern_bpm_range check_pattern_coverage_grain`: exit 1, `check_invalid_pattern_buckets` `FAIL 3`, the other two PASS.
   - Side observation: `check_pattern_bpm_range` passes with a NULL `bpm_max`, because a NULL comparison is not true. That gap is now covered by the new test, through `bpm_bucket = 'unknown'`.
5. `uv run python -m tools.check_links`: `0 dead link(s)`, exit 0.
6. `git log --all` over `data/cycling_patterns.json` plus a grep of each version for the removed effort values (results in section 3).
7. Not run: `make lint` (ruff), `typecheck`, `test-unit`, `eval` and `contract`. They are outside this dbt review and the diff touches no Python.

## 5. Downstream impact

- **Data:** `stg_patterns.effort_bucket` → `int_pattern_effort_profile` → `mart_pattern_coverage`. The mart is recomposed, from 29 rows (low 6 / medium 20 / high 14 patterns) to 27 rows (low 12 / medium 11 / high 17). The before figures are yours; I re-measured only the after figures. The column names and types of these three models are unchanged, and no E.2 schema is touched.
- **Other consumers** (read in the code, per the issue's plan comment):
  - nothing in `cyclebeat/` (planner, rules), `api/`, `frontend/src/`, `mcp-server/` or `openapi.yaml` reads patterns;
  - `mart_pattern_coverage` is not in `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py`).
  - So no endpoint, screen or agent tool is affected, and the impact is confined to the mart, as `product-spec.md` Scope now states.
- **Build behaviour:** a future unmapped `effort`, or a NULL `resistance` or `bpm_mid`, now turns `make dbt` and CI red, where it used to be silently bucketed. A new `effort` value in `data/cycling_patterns.json` will need an explicit mapping in `dbt/models/staging/stg_patterns.sql` before the build goes green.
