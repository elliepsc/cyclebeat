> dbt-reviewer, second targeted pass on the issue #60 branch, run on 25 October 2026, after a blocking finding (B1) in the first pass. Delta reviewed: `5ece6e6..c142425` (the fixes in c142425), plus `3aad233` (`--durations=10`). The question asked: are B1 and N1-N5, N7, N8 really fixed, and does the fix introduce a new defect? Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch. Raw output, unedited: the harness indents a subagent's report, and that indentation is removed.

---

dbt-reviewer, second pass on issue #60. Branch `test/60-reference-dataset` @ c142425, checked against `origin/main` @ a16fabc after `git fetch`. I read the whole delta `git diff 5ece6e6..c142425` (8 files) and `git show 3aad233`. I modified no repo file.

## 1. Verdict: APPROVED

B1 is fixed. N1, N2, N4, N5 and N7 are fixed. N3 and N8 are mostly fixed, with small leftovers listed below. The fix introduces no new defect. 3aad233 is fine.

## 2. Blocking findings

None.

## 3. Status of each finding from pass 1

- **B1, fixed.**
  - The grain sentence is at `dbt/models/intermediate/int_feedback_enriched.sql:3-5`.
  - The new singular test `dbt/tests/check_feedback_enriched_grain.sql` uses the same key as `check_stg_feedback_grain` (`created_at` becomes `feedback_at`). It is a singular test because NULL `session_id` collides under GROUP BY, which is correct.
  - **It can fail, shown two ways:**
    - **The commit's claim:** `test_grain_tests_fail_on_a_duplicated_feedback` passes on the branch with 3 FAIL lines.
    - **Mutation M1** (`having count(*) > 2` in the new test, in a scratch copy of the repo): the same test goes red with `assert 2 == 3`. Only `check_recent_activity_grain` and `check_stg_feedback_grain` failed. So the assertion really depends on the new test.
    - **Mutation M2** (the fan-out case the test's header describes): in a scratch copy, `stg_sessions` keeps `recency >= 1`, and s1 is written on DAY_1 and DAY_2 with one feedback.
      - Result: `FAIL 1 check_feedback_enriched_grain`, `PASS check_stg_feedback_grain`, plus `FAIL 1 unique_stg_sessions_session_id` and `FAIL 1 check_recent_activity_grain`.
      - So the new test catches a duplicate from the join that the staging grain test cannot see.
  - The knock-on edits are done: `tests/test_reference_warehouse.py:125-126` and `docs/metrics.md:33`.
- **N1, fixed.** `tests/test_reference_warehouse.py:5-6` now says "on a copy of the local warehouse".
- **N2, fixed.** `mart_recent_activity.sql:9-10` and `dbt/models/marts/schema.yml:281` now match `docs/metrics.md`.
- **N3, mostly fixed** (see non-blocking 1). `docs/metrics.md:42-43` now names the branch and the base a16fabc, and warns that the line numbers will drift.
- **N4, fixed.** `docs/metrics.md:62-64` now gives the right cause: a fresh container and no disk (ADR-003). The link target is tracked.
- **N5, fixed.** `docs/metrics.md:79` adds the exclusions for a NULL `session_id` and for `duration_min <= 0`, matching `stg_sessions.sql:25,50`.
- **N7, fixed.** `tests/test_data_guards_fail.py:46-51` now also asserts there is no ` ERROR creating ` line. The 3 guard tests still pass with it.
- **N8, mostly fixed** (see non-blocking 2). A test that depends on no model is now reported as `(tests no model)` instead of skipped (`tests/test_reference_warehouse.py:110-111`).
- **N6:** kept on purpose. **N9:** recorded only. Neither was reviewed again.

## 4. Non-blocking findings

1. **N3 leftover** at `docs/metrics.md:42-43`. A branch name stops meaning anything after the merge, and the base SHA a16fabc is not the commit the line numbers were checked on (b233a03/c142425). Naming the merge SHA, or switching to section anchors, would close it. This is wording only.
2. **N8 second blind spot is still unmeasured.** A non-empty model does not mean the tested column is non-empty (an all-NULL column, or `unique` over 1 row or fewer). The pass-1 column-level check found nothing affected, and that still holds since no new generic test was added. The docstring at `tests/test_reference_warehouse.py:87-89` does not mention this limit.
3. **Wording nit** at `dbt/tests/check_feedback_enriched_grain.sql:4-5`. "a duplicate here can only come from the session join fanning out" is true only while `check_stg_feedback_grain` holds. In the dedup test, this test goes red because of a `stg_feedback` duplicate, not a fan-out. Something like "beyond a duplicate already in `stg_feedback`" would be accurate.
4. **Formatting** at `dbt/models/marts/schema.yml:281`. The edited line runs past the folded-block width of the lines around it. It has no effect on the output because `>` folds it, and lint passes.

## 5. Commit 3aad233 (`pyproject.toml` addopts gains `--durations=10`)

- It adds no dependency and changes no test selection.
- `make test-integration` overrides addopts, as the existing comment says.
- The output works: my run printed the "slowest 10 durations" block. That is enough to read the CI duration of the reference fixture, which took 16.34 s setup locally.
- No defect.

## 6. What was checked and how

- **Main test run:** `uv run pytest tests/test_feedback_dedup.py tests/test_reference_warehouse.py tests/test_data_guards_fail.py --basetemp=<scratch>/pt` (`set -o pipefail`, output to a file): exit 0, 15 passed in 52.3 s.
  - This covers the 79 data-test count and "0 vacuous": `test_no_data_test_runs_over_an_empty_model` asserts `n_tests == 79` and `vacuous == []`, and it passed.
  - The 3 guard tests passed with the new ERROR assertion.
- **Mutations:** M1 and M2 ran on `git archive HEAD` copies under the scratchpad, with the repo `.venv` Python. I confirmed that `REPO_ROOT` and `cyclebeat` resolved to the copy. Results are in §3, B1.
- **Lint:** `make lint` exit 0, ruff clean, 0 dead links.
- **`make dbt` was not executed.** Reason: the brief forbids touching `data/`. The reference chain (`dbt run` + `dbt test` of the whole project on a scratch warehouse) stands in for it.
- **`data/` and `lake/`:** the fingerprint (find + sha256) was identical before and after. `git status` is clean.
- **E.2 contracts:** no change to `cyclebeat/e2.py`, the normalization, zones or confidence, or any raw/dim/fct column.

## 7. Downstream impact

- There is one more data test (79), and it runs on rows of the reference dataset.
- Model SQL is unchanged apart from comments. No output column changed.
- `mart_recent_activity` is still outside the MCP allowlist, and no API endpoint or screen reads it, so nothing downstream changes.

Relevant paths:
- /home/ellie/projets/cyclebeat/dbt/tests/check_feedback_enriched_grain.sql
- /home/ellie/projets/cyclebeat/dbt/models/intermediate/int_feedback_enriched.sql
- /home/ellie/projets/cyclebeat/tests/test_feedback_dedup.py
- /home/ellie/projets/cyclebeat/tests/test_reference_warehouse.py
- /home/ellie/projets/cyclebeat/tests/test_data_guards_fail.py
- /home/ellie/projets/cyclebeat/docs/metrics.md

Scratch outputs:
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/p2/pytest.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/p2/m1.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/p2/m2.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/p2/lint.out
