> dbt-reviewer, second targeted pass on the issue #54 branch, run on 23 October 2026, at the owner's request. Delta reviewed: `024304b..5c96c36` (the fixes in 78bdb58 and the ai-workflow entry in 5c96c36). The question asked: are F1 to F6 really fixed, and does the fix introduce a new defect? Agent definition: `.claude/agents/dbt-reviewer.md` as on `origin/main`, unchanged on the branch. Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commit that follows this one.

---

dbt-reviewer, second targeted pass: `fix/54-feedback-dedup` (HEAD 5c96c36), delta `git diff 024304b..HEAD`

I checked against the branch, which `git branch --show-current` reports as `fix/54-feedback-dedup` with a clean tree; `origin/main` is f6b0c9c after a fetch. I read the whole delta: 10 files, the fixes in 78bdb58 and the entry in 5c96c36. I changed no repo file. Scratch work is in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/9ccab3cb-61c4-468a-9e1d-4d5be6c5eb4e/scratchpad/review2/`. `data/` and `lake/` fingerprints were identical before and after every run.

## 1. Verdict: APPROVED WITH RESERVATIONS

There is no blocking finding. F1, F2, F5 and F6 are fixed. F4 is fixed in the repo docs, and its `CLAUDE.md` part is left to you. **F3 is not fixed**: the new wording is still not reproducible, and its second half is false (N1 below). The fixes add no new defect in code or tests.

## 2. F1 to F6: one verdict each

**F1, BLOCKING in the first review: FIXED.**
- **Grain sentence:** added in `dbt/models/staging/stg_feedback.sql:3-6` and `dbt/models/staging/schema.yml:49-51`. Both say one feedback (one insert) as held by the latest `dt`, key (session_id, session_title, created_at).
- **Key test:** `dbt/tests/check_stg_feedback_grain.sql:7-14` groups on that key over every row, `having count(*) > 1`. `make dbt` runs it: `30 of 100 PASS check_stg_feedback_grain`.
- **The two grain tests on the duplicate case.** I drove the test's own helpers from `scripts/drive.py`:
  - `dbt build`: `19 of 31 FAIL 1 check_stg_feedback_grain`, then `SKIP relation main.int_feedback_enriched`, `SKIP relation main.mart_recent_activity` and `SKIP test check_recent_activity_grain`. Summary `ERROR=1 SKIP=8`. The triage's "1 FAIL line under build" is confirmed.
  - `dbt run` (rc=0, PASS=4), then `dbt test` (rc=1): `10 of 25 FAIL 1 check_recent_activity_grain` and `11 of 25 FAIL 1 check_stg_feedback_grain`, `ERROR=2`. The triage figures are confirmed.
- **Could the pytest pass for a wrong reason?** No. It still proves both tests fail. I ran two mutations on HEAD copies:
  - m1, `check_stg_feedback_grain.sql` removed: the pytest goes RED with `assert 1 == 2`, one FAIL line (the mart test only).
  - m2, `select distinct` in `mart_recent_activity.sql`: the pytest goes RED with `assert 1 == 2`, one FAIL line (the stg test only).
  - What makes it hold (`tests/test_feedback_dedup.py:160-175`):
    - `assert built.returncode == 0` rules out a mart that was never built.
    - `len(failing) == 2` rules out any extra FAIL. On the pre-fix SQL, the two stg unit tests add 2 more and the run gives `assert 4 == 2`.
    - The two names are matched one by one, and neither name is a substring of the other.
    - A test that errors at compile time prints `ERROR`, not ` FAIL `, so it cannot be miscounted.
- **Selection:** `run` and `test` both use `+mart_recent_activity`. That covers stg_feedback, stg_sessions, int_feedback_enriched and the mart (PASS=4 on `run`).

**The tie-break claim holds.** The claim is in `mart_recent_activity.sql:12-15` and `docs/metrics.md:113-115`.
- In `int_feedback_enriched.sql`, `f.created_at as feedback_at`. `session_id` and `session_title` come from `f`.
- The join to `stg_sessions` is a left join whose two OR branches exclude each other (the second requires `f.session_id is null`). `stg_sessions` is unique on `session_id` (`unique_stg_sessions_session_id`). So each stg row gives exactly one int row.
- So stg's key, unique under GROUP BY with NULLs compared as equal, makes (feedback_at, session_id, session_title) distinct on every int row. An ORDER BY on those columns, with NULLs placed together, is then a strict total order.
- It is stronger in practice: `make dbt` (`Makefile:82`) and the DAG (`dags/dag_build_warehouse.py:68`) both run `dbt build`. A failing stg grain test skips the mart (run A above), so a mart materialized by build always sits on a unique key.
- The only case left: under a bare `dbt run` the mart is built anyway, and its test then reports the problem. The wording "the key holds over every feedback" is read as conditional on the test, which is acceptable.

**F2, MEDIUM: FIXED.**
- `dbt/tests/check_recent_activity_grain.sql:4-18` and `docs/metrics.md:104-110` state the assumption: two inserts on one session never share a timestamp.
- They give the right reason for leaving `rating`, `rating_scale` and `note` out: those columns catch nothing more and make the test stricter.
- Checked against the code:
  - `api/repositories/feedback.py:27` sets `created_at = datetime.now(UTC)` per insert.
  - The v1 `now()` writer was deleted (`db/runtime.py:8-12`). `git grep "now()"` finds no remaining SQL writer.
  - So "no current code path writes v1 rows" holds.

**F3, LOW: NOT FIXED. The new sentence is not reproducible, and its second half is false.** See N1.

**F4, LOW: FIXED in scope.**
- `docs/ROADMAP.md:83` now reads "32 sur 72, mesuré pendant #46, sur un entrepôt à 0 séance et 0 retour", dated and without "aujourd'hui".
- `CLAUDE.md:181` still says "32 of 72". That is your verbatim line and your call, as the triage records.
- For reference: `dbt ls --resource-type test` now counts 75 data tests on HEAD (plus 4 unit tests).

**F5, LOW: FIXED.**
- `_dbt` copies `dbt/profiles.yml` into `tmp_path/profiles` (`tests/test_feedback_dedup.py:84-86`) and passes `--profiles-dir` that copy.
- The right profile is still read:
  - `dbt_project.yml:5` sets `profile: cyclebeat`.
  - The profile path is `env_var('RUNTIME_DB_PATH', ...)`, and `RUNTIME_DB_PATH` is always set explicitly in `env`, so the cwd-relative default never applies. The CLI flag also overrides any `DBT_PROFILES_DIR`.
  - A wrong profile would have failed `dbt run` (rc=0, PASS=4).
- The cookie lands in the temp dir: `runA/profiles/.user.yml` and `runB/profiles/.user.yml` exist.
- `dbt/.user.yml` was left untouched: its mtime is 1791558427 before and after the repo pytest and after the full `make test-unit`. The `find` fingerprint of `data lake dbt/target dbt/logs dbt/.user.yml` was identical around the repo pytest.

**F6, INFO: FIXED.** `mart_recent_activity.sql:8` now reads "`stg_feedback` reads only the latest `dt`".

## 3. New findings (none blocking)

**N1. LOW. `docs/metrics.md:40-42` is inaccurate, and two claims in `docs/ai-workflow.md` are not reproducible.**
- The sentence: "That was measured at 4129a70, before the grain tests below existed. Today the same version fails earlier: the dbt build itself goes red on the grain tests, before the figures are read."
- Measured on HEAD with `origin/main`'s `stg_feedback.sql` (tree `old/`):
  - `dbt build` fails first on the unit test: `2 of 49 FAIL 1 stg_feedback::stg_feedback_same_feedback_in_two_partitions`.
  - Then `stg_feedback` and everything downstream is skipped (`ERROR=1 SKIP=32`). So the grain tests do not even run under build.
- Measured on the 4129a70 tree with the pre-fix `stg_feedback.sql` (tree `e4129/`): the pytest also fails at `assert result.returncode == 0`, on `Failure in unit_test stg_feedback_only_latest_partition_kept`. The unit tests came in at 2ffe681, before 4129a70. So the four figures were not reachable at 4129a70 either, with the committed suite.
- The four figures are real: I reproduced them in the first review with the staging unit tests and the grain test set aside. But "measured at 4129a70" alone does not give the conditions.
- **This is partly my fault.** My first-pass F3 removed `unit_tests.yml` in run 1 without saying it blocks too. It also implied that 4129a70 would reach the figures.
- The same unconditioned claim appears in `docs/ai-workflow.md:30` ("On the pre-fix `stg_feedback` it failed on all four indicators") and `:62` ("the pytest failed on all four indicators on the pre-fix model"). The 4129a70 commit message says the same.
- The triage row F3 ("Fixed") and `ai-workflow.md:38` therefore overstate.
- Proposed fix: "measured with the `stg_feedback` unit tests set aside; with the committed suite, the pre-fix version fails first on those unit tests, which skip `stg_feedback` and everything downstream."

**N2. INFO. `docs/ai-workflow.md:34` overstates what the pytest asserts.**
- It says the duplicate case "expects `FAIL 1 check_recent_activity_grain`, `FAIL 1 check_stg_feedback_grain`, `ERROR=2`".
- The test (`tests/test_feedback_dedup.py:166-175`) asserts `returncode != 0`, two lines containing ` FAIL `, and the two names. It asserts neither `ERROR=2` nor the `1` row count.
- Line 63, which reports a measurement, is accurate. Either reword line 34 to "observed", or add the assertions.

**N3. INFO. The key has a blind spot that the stated assumption does not name.** This is outside the delta and does not block.
- `cyclebeat/app_store.py:102-110` (`_as_datetime`) replaces a missing or unparseable `created_at` with `datetime.now(UTC)` at extraction time.
- So a doubled insert carrying such a value gets two different stamps and passes both grain tests.
- The API always writes `created_at`, so the risk is low. This is the "silent `now()` fallback" already in the lake-timestamp issue draft (owner decision 4). One clause in `docs/metrics.md:104` could point to it.

No other delta sentence contradicts the code. The ones checked:
- `schema.yml:49-51`.
- The `stg_feedback.sql` header.
- The `check_stg_feedback_grain.sql` comment: "a duplicate outside the 20 would reach `mart_feedback_summary` and `int_session_summary`" is true by the lineage.
- `docs/metrics.md:45-46` and `:99-102`.
- `mart_recent_activity.sql:7-15`.
- `docs/ROADMAP.md:83`.
- In the ai-workflow entry, all checked against what I could re-run: DoD `make dbt` PASS=96, `make test-unit` 795/15/2, lint green, the 1-FAIL-under-build finding, and the cookie location.

## 4. What was checked and how

- **Reference:** `git branch --show-current` (fix/54-feedback-dedup), `git fetch`, `origin/main` = f6b0c9c. Delta read with `git diff 024304b..HEAD`. First review and triage read in full.
- **Repo pytest:** `uv run pytest tests/test_feedback_dedup.py -v` gave `2 passed`, exit 0. `data/`, `lake/`, `dbt/target`, `dbt/logs` and `dbt/.user.yml` fingerprints were unchanged.
- **Scratch trees:** made with `git archive` into `review2/{head,m1,m2,old,e4129}`. Tests run with the repo venv's python and `PYTHONPATH=<tree>`, `DATABASE_URL` unset.
  - head: build → 1 FAIL plus mart SKIP; run + test → 2 FAIL, ERROR=2.
  - m1 (stg grain test removed) and m2 (mart `select distinct`): the pytest is red, `assert 1 == 2`.
  - old (HEAD with the pre-fix SQL) and e4129 (4129a70 with the pre-fix SQL): red on the stg unit tests before any figure.
- **Gates:**
  - `RUNTIME_DB_PATH=<scratch copy> make dbt`: exit 0, `PASS=96 WARN=0 ERROR=0 SKIP=0 TOTAL=96`. The copy has 0 feedback, so the grain tests are vacuous there. As usual for `make dbt`, it rewrote the gitignored `dbt/target` and `dbt/logs`.
  - `make lint`: exit 0, "All checks passed!", "0 dead link(s)".
  - `make test-unit`: exit 0, `795 passed, 15 skipped, 2 xfailed`.
  - Exit codes were read directly, not through a pipe.
- **Test count:** `dbt ls --resource-type test` gives 75; `--resource-type unit_test` gives 4.
- **Code read to check doc claims:** `int_feedback_enriched.sql`, `dbt/profiles.yml`, `dbt_project.yml`, `Makefile:81-82`, `dags/dag_build_warehouse.py:68`, `api/repositories/feedback.py:27`, `cyclebeat/app_store.py:102-110`, `db/runtime.py:1-12`, and `git grep "now()"`.
- **One refusal:** a `rm -rf "$S/$m"` in the scratch setup was refused by the safety check. I did not retry it. The directories did not exist yet, so I created fresh ones without any removal.

## 5. Downstream impact of the delta

- **dbt:** one new singular test on `stg_feedback`. No model logic changed: the delta in `mart_recent_activity.sql` is comments only, and `stg_feedback.sql` gained a header only.
- **Behaviour under `dbt build`:** a duplicated feedback now stops the build at `stg_feedback`, so every model downstream is skipped. Before, only the mart's test failed after the mart was built.
- **Outside dbt:** none. No endpoint, screen, `openapi.yaml` or `MARTS_ALLOWLIST` entry is touched. No E.2 contract is touched (normalization, zones, confidence, the six schemas).

Files mentioned: `/home/ellie/projets/cyclebeat/docs/metrics.md`, `/home/ellie/projets/cyclebeat/docs/ai-workflow.md`, `/home/ellie/projets/cyclebeat/security/pr-audits/pr-54-triage.md`, `/home/ellie/projets/cyclebeat/tests/test_feedback_dedup.py`, `/home/ellie/projets/cyclebeat/dbt/tests/check_stg_feedback_grain.sql`, `/home/ellie/projets/cyclebeat/cyclebeat/app_store.py`.

Logs in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/9ccab3cb-61c4-468a-9e1d-4d5be6c5eb4e/scratchpad/review2/`: `make_dbt.log`, `lint.log`, `test_unit.log`, `pytest_repo.log`, `pytest_m1.log`, `pytest_m2.log`, `pytest_old.log`, `pytest_e4129.log`.
