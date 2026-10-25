> dbt-reviewer, pre-PR review of the issue #60 branch, run on 25 October 2026. Diff reviewed: `origin/main...b233a03` (6 commits, f9cfeb5, 3489113, a4d4d4f, 4f0e1a1, dcc1b3a, b233a03). Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents/` is empty). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The "someone else moved HEAD to 3aad233" in the report is the main coding agent pushing its `--durations=10` commit during the review. The fixes it led to are in the commits that follow this one.

---

dbt-reviewer report: issue #60, branch `test/60-reference-dataset` @ b233a03, reviewed against `origin/main` @ a16fabc (after `git fetch`). I read all 6 commits of the diff in full (f9cfeb5, 3489113, a4d4d4f, 4f0e1a1, dcc1b3a, b233a03).

**Concurrency warning.** While I was reviewing, someone else in the repo moved HEAD to 3aad233 ("test: print the 10 slowest tests in every pytest run (#60)", only `pyproject.toml` `addopts += --durations=10`). That commit is outside the reviewed range and I did not review it. CLAUDE.md warns that two agents running commands at once mix their effects. My dbt runs used their own target and log paths under the scratchpad, so they did not touch `dbt/target`.

**Hook refusal (reported, not worked around).** `grep -rn ... .` was refused because it reaches `.env`. I searched the named subfolders instead (dbt, api, cyclebeat, db, dags, tools, mcp_server, frontend/src, docs, tests, openapi.yaml), as the hook message itself suggests.

## 1. Verdict: CHANGES REQUIRED

There is one blocking item, required by my checklist. It already existed on main and is small to fix. Everything else checked out.

## 2. Blocking findings

**B1. `int_feedback_enriched` is a changed model with no stated grain and no grain test.**
- **Where:** `dbt/models/intermediate/int_feedback_enriched.sql:1-11`. The header explains the join but has no "Grain:" sentence. `dbt/models/intermediate/schema.yml` has no entry for the model (only `int_pattern_effort_profile`), so no grain-key test exists.
- **Rule broken:** "Grain of each new/changed model stated in 1 sentence … No stated grain = model not finished", and "`unique` + `not_null` on the grain key of every new/changed model" (missing = blocking).
- **Mitigation:** this was already true on a16fabc. The change narrows the join, so it can only reduce fan-out. R5 (`tests/test_reference_warehouse.py:227-230`) checks no fan-out, but only on the reference dataset.
- **Proposed fix:**
  - add a grain sentence to the header: one row per feedback of `stg_feedback`, key `(session_id, session_title, feedback_at)`;
  - add a singular `dbt/tests/check_feedback_enriched_grain.sql` (`GROUP BY session_id, session_title, feedback_at HAVING count(*) > 1`). This follows the CLAUDE.md rule for composite keys with NULLs; plain `unique`/`not_null` would be wrong here because `session_id` is NULL on v1 rows.
- **Knock-on edits:** `tests/test_reference_warehouse.py:121` (`n_tests == 78` becomes 79) and `docs/metrics.md:33` ("0 of 78").
- **Alternative:** if the owner sees this as widening the scope, record it as a `[présentable]` ROADMAP line. That is the owner's call, not mine.

## 3. Non-blocking findings

- **N1. Wrong attribution in a test docstring.** `tests/test_reference_warehouse.py:5-6` says "before #60 the CI warehouse held 0 sessions and 0 feedback, and 35 of the 78 data tests ran over empty models". The issue body says the 35/78 figure was measured on a scratch copy of the local runtime warehouse, and "The CI warehouse … was not measured; its figure may differ." Suggested fix: say "a copy of the local warehouse".
- **N2. The grain is described three different ways.**
  - `docs/metrics.md` (mart_recent_activity bullet) now says "with the context of the session it rates when it carries a `session_id`".
  - `dbt/models/marts/mart_recent_activity.sql:9` and `dbt/models/marts/schema.yml:281` still say "with the context of the session it rates", with no qualifier. Since #60 that is untrue for v1 rows.
  - Suggested fix: align the SQL header and the schema.yml description with metrics.md.
- **N3. Line pointers that will break.** `docs/metrics.md:42` says "Checked on the code at #60; the line numbers are those of that commit". No SHA is named, and the section uses about 12 `file:line` pointers. CLAUDE.md says to prefer section anchors, or at least name the SHA (a16fabc / b233a03; every pointer I checked is still correct at b233a03).
- **N4. Imprecise wording.** `docs/metrics.md:61-62` says "The next image build deletes the store again." The `rm data/*.db` in `Dockerfile:40` acts on the build context, not on the running container. At runtime the store is the container's own `data/cyclebeat_app.db`. It is lost because the next deploy starts a fresh container (no disk, ADR-003), not because the build deletes it. The conclusion (it never reaches a mart) still holds.
- **N5. Window table nuance.** `docs/metrics.md:77` describes the window as "every session in any lake partition, latest copy". `stg_sessions` also drops `session_id is null` and `duration_min <= 0` rows (`stg_sessions.sql:25,50`). Worth one clause.
- **N6. Marked done before merge.** `docs/ROADMAP.md:83` marks the #60 line ✅ before the PR is merged ("Write facts after they happen"). Acceptable only if the line lands with the merge; otherwise use ⬜ until then.
- **N7. Guard assertion can miss a second failure.** `tests/test_data_guards_fail.py:98-101` (`_assert_only_failure`) counts `FAIL` lines but not `ERROR` lines. A model error next to the right guard `FAIL` would still pass. Under `build`, downstream nodes are skipped, so the risk is low. Suggested fix: also assert there is no line containing ` ERROR creating`.
- **N8. Blind spots in the vacuity method** (see §4 Q3). No test is affected today.
- **N9. SQL text in `tests/`.** `tests/test_reference_warehouse.py` contains SQL query strings, outside `api/repositories/` and `dbt/`. There is a precedent (`tests/test_feedback_dedup.py`), and the rule's scope is already an open ROADMAP line (#55). Recorded only, not a violation I would invent.

## 4. Answers to questions 1-5, what was checked and how

**Q1. Is the join change correct, and does anything else rely on the fallback?**
- The new join is `on f.session_id = s.session_id`, identical in shape to `int_session_summary.sql:45`.
- The only consumer of `int_feedback_enriched` is `mart_recent_activity`. Nothing in api/, cyclebeat/, tools/ or frontend/src reads it.
- `mart_recent_activity` is not in `MARTS_ALLOWLIST` (`api/services/warehouse_tools.py:58-60`), so no MCP or copilot tool sees the change.
- No other file describes a title fallback (the only matches are dbt.log files, which git does not track).
- Output columns are unchanged, so there is no schema break.
- Unit tests U1/U2, run by me on a copy of the dbt project:
  - fixed SQL: PASS=2;
  - base SQL (origin/main): U1 FAIL 1, U2 PASS (U1 red on base, U2 pins existing behaviour);
  - mutation `or f.session_id is null`: U1 FAIL and U2 FAIL (U2 red on the mutation).
- On the full reference warehouse with the base SQL: R4 = (7, 6), R5 = 8, and V1B appears in `mart_recent_activity` with `level='beginner'`. This confirms the defect and that the fix removes it.

**Q2. Do the hand-computed values match the dataset?**
I recomputed every value from `tests/reference_dataset.py`.
- **Sessions:** D2 holds A, B and C, with A at gap +30.
- **Feedback:** D1 holds {V1A, V1B, F1}, a subset of D2, so there are 8 distinct feedback and 6 attached.
- **`mart_session_kpis`:**
  - avg_duration_min = round(95/3, 1) = 31.7;
  - total_tracks_used = 6 + 9 + 4 = 19;
  - sessions_flagged_review = 1;
  - avg_abs_duration_gap_s = (30 + 60 + 0)/3 = 30.0;
  - last_session_at = C at 2026-10-23 08:00;
  - avg_satisfaction_pct = avg(50, 75) = 62.5 (41.7 if C's NULL counted as 0).
- **`mart_feedback_summary`:** effort Great 1 / Hard 1 at 50/50; satisfaction up 4 / down 2 at 66.67/33.33.
- **`int_session_summary`:** A (2, 50.0), B (4, 75.0), C (0, NULL).
- Every arithmetic comment in `tests/test_reference_warehouse.py:147-179` matches. The run agrees.
- Mutations I re-ran myself:
  - removing the `max(dt)` filter in `stg_feedback`: R1 = 11, R6 = 11;
  - removing `recency = 1` in `stg_sessions`: R2 = 4, R3 = 8.
  - These match the issue comments.

**Q3. Is the vacuity method sound?**
I measured it independently from the reference run's manifest:
- 78 data tests and 10 unit tests (unit tests sit outside `nodes`, so they are rightly not counted);
- 13 singular tests have no `attached_node`, and each depends only on `model.` nodes;
- 0 tests depend on a `source.`.

It is sound for this project. Two blind spots:
- a test whose dependencies include no model (a source test) is silently skipped by the `if models and …` branch at `tests/test_reference_warehouse.py:105-108`, rather than reported;
- "the model is non-empty" does not mean "the tested column is non-empty". I added a column-level check: no generic test on a column that is all NULL, and no `unique` over 1 row or fewer. So none is affected today.

**Q4. Are the provenance and window claims in `docs/metrics.md` true?**
Every `file:line` is correct at b233a03:
- `Dockerfile:40-45` (the `RUN`, including `rm data/*.db` and `extract-app`) and `Dockerfile:61` (the uvicorn-only CMD);
- `render.yaml:31-37` (no `DATABASE_URL`);
- `cyclebeat/app_store.py:89-90` (missing file returns `[]`) and `173-181` (no partition when the store is empty);
- `api/services/warehouse_tools.py:58-60` (`fct_session` allowlisted);
- `tools/deploy.py:205-207`;
- `api/services/session.py:110` (`_sessions.save`);
- `Makefile:81-82` and `92-96` (the extract partition is the current UTC day, `extract_to_lake` uses `datetime.now(UTC).date()`);
- `dags/dag_build_warehouse.py:44-77`.

The window claims also hold:
- no mart filters on a date (grep found only `filter (where …)` aggregates);
- `stg_tracks` and `stg_resolutions` keep the latest copy per key;
- `save_patterns` runs `DELETE` then `INSERT` (`db/runtime.py:68`);
- `stg_feedback` reads the latest `dt` only.

The edited mart_recent_activity bullet is true against the new SQL. The only reservations are the wording points N4 and N5.

**Q5. Does the branch make an already-delivered claim false?**
I found none. ADR-008's "the dbt feedback chain is untouched" was already outdated before this branch.

**E.2 contracts:** no change to `cyclebeat/e2.py`, normalization, zones, confidence, or any raw/dim/fct column. No violation.

**Execution (commands and results):**
- `uv run pytest tests/test_reference_warehouse.py tests/test_data_guards_fail.py --basetemp=<scratchpad>/pt`: exit 0, 13 passed in 41.5 s locally. The reference fixture setup took 17.2 s; the guard tests took 10.6 s, 6.4 s and 5.7 s.
- Same reference test with `TZ=Europe/Paris`: exit 0, 10 passed.
- U1/U2 under fixed, base and mutated SQL, and the R-mutations: results in Q1 and Q2.
- `make dbt` was not executed. Reason: the brief forbids running it against `data/`. The reference chain (`dbt run` + `dbt test` of the whole project, including unit tests, on a scratch warehouse) stands in for it.
- `data/` and `lake/` were not modified (find -newer: nothing).
- The CI duration was not measured by me.

## 5. Downstream impact

- `int_feedback_enriched` feeds `mart_recent_activity`. A v1 row whose title equals a `session_id` now gets NULL `level`, `goal`, `duration_min` and `track_count`.
- No current code path writes v1 rows, and the working warehouse holds 0 feedback, so no production or demo figure changes.
- Not affected: mart_recent_activity is outside the MCP allowlist, and no API endpoint or front screen reads it (searched api/, frontend/src).
- `int_session_summary`, `mart_session_kpis` and `mart_feedback_summary` are unchanged.
- Test runtime grows by about 40 s locally in `make test-unit`.

Relevant paths:
- /home/ellie/projets/cyclebeat/dbt/models/intermediate/int_feedback_enriched.sql
- /home/ellie/projets/cyclebeat/dbt/models/intermediate/unit_tests.yml
- /home/ellie/projets/cyclebeat/tests/test_reference_warehouse.py
- /home/ellie/projets/cyclebeat/tests/test_data_guards_fail.py
- /home/ellie/projets/cyclebeat/docs/metrics.md

Scratch artifacts:
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/pytest.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/pytest_paris.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/b7643033-e617-43c8-a50b-fb6e760c2d94/scratchpad/vac.py

I modified no file in the repo.
