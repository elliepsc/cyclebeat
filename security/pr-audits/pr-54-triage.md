# Triage of the dbt-reviewer review, issue #54 branch

Raw review: [pr-54-dbt-reviewer.md](pr-54-dbt-reviewer.md), on `origin/main...bb1da92`. One verdict per finding. The fixes are in the commit that adds this file.

| Finding | Severity | Verdict | What was done |
|---|---|---|---|
| F1: `stg_feedback` has no grain sentence and no key test | BLOCKING | **Fixed** | Grain sentence in the `stg_feedback.sql` header and in `dbt/models/staging/schema.yml`. New `dbt/tests/check_stg_feedback_grain.sql` on (session_id, session_title, created_at), over every row. The duplicate pytest case now expects both grain tests to fail. It runs `dbt run` then `dbt test`, because under `dbt build` the failing staging test skips the mart and its test never runs (measured: 1 FAIL line under `build`). Measured: `FAIL 1 check_recent_activity_grain`, `FAIL 1 check_stg_feedback_grain`, `ERROR=2`. The tie-break claim now rests on the key over every feedback. |
| F2: the key's justification is backwards and its assumption unstated | MEDIUM | **Fixed** | `check_recent_activity_grain.sql` and `docs/metrics.md` now state the assumption. Two inserts on one session never share a timestamp: µs `datetime.now(UTC)` for API rows, while DuckDB `now()` (the transaction start) would let v1 rows written in one transaction collide. They also give the right reason for leaving `rating`/`rating_scale`/`note` out: it catches nothing more and makes the test stricter. |
| F3: the "failed on all four figures" claim cannot be reproduced with the committed suite | LOW | **Fixed in two steps** | The first wording ("measured at 4129a70", "the build goes red on the grain tests") was still wrong; the second pass found it ([pass 2](pr-54-dbt-reviewer-pass2.md), N1). `docs/metrics.md` now says the figures were measured with the staging unit tests set aside, and that with the committed suite those unit tests fail first and skip everything downstream. |
| F4: "32 of 72" is stale (74 tests on HEAD) | LOW | **Fixed** in `docs/ROADMAP.md` ("32 sur 72, mesuré pendant #46", no "aujourd'hui"). **Recorded** for `CLAUDE.md`: the line is the owner's verbatim copy, so any date added there is the owner's call. |
| F5: the pytest writes `dbt/.user.yml` into the project's profiles dir | LOW | **Fixed** | The pytest copies `dbt/profiles.yml` into `tmp_path/profiles` and passes that dir. Measured: the cookie lands in `<tmp>/profiles/.user.yml`, and the mtime of `dbt/.user.yml` is unchanged. |
| F6: "deduplicated across `dt`" is loose wording | INFO | **Fixed** | `mart_recent_activity.sql` now says "`stg_feedback` reads only the latest `dt`". |
| F7: `select *` in the `latest` CTE | INFO | **Accepted** | It follows the staging convention (`source` CTEs), and `cleaned` lists its columns explicitly. |
| F8: SQL strings in `tests/test_feedback_dedup.py` against the "no SQL outside `api/repositories/` and `dbt/`" rule | INFO | **Owner decision: allowed** | The rule is about the layering of application code; a read-only query in a test assertion is allowed (relayed on #54). The clarification goes into CLAUDE.md in the first commit of #55, not on this branch. |
| F9: the CI run link cannot be checked before the push | INFO | **Pending** | The CI run link goes into the PR description after the push. |

## Second pass

Raw: [pr-54-dbt-reviewer-pass2.md](pr-54-dbt-reviewer-pass2.md), on `024304b..5c96c36`. Verdict: approved with reservations, nothing blocking. F1, F2, F5 and F6 are confirmed fixed, F4 fixed in scope, F3 not fixed until N1.

| Finding | Severity | Verdict | What was done |
|---|---|---|---|
| N1: the F3 rewording is still not reproducible; the same claim in `docs/ai-workflow.md` | LOW | **Fixed** | `docs/metrics.md`, `docs/ai-workflow.md` and the F3 row above now give the condition (the staging unit tests set aside). The 4129a70 commit message keeps the unconditioned wording: it is pushed history and is not rewritten. |
| N2: `docs/ai-workflow.md` says the pytest asserts `ERROR=2` | INFO | **Fixed** | Reworded: the pytest asserts two FAIL lines, one per grain test; `ERROR=2` is observed, not asserted. |
| N3: an unreadable `created_at` is replaced by the extraction time, a blind spot of the key | INFO | **Fixed** (doc) | One clause in `docs/metrics.md` names it and points to #57, which owns the fallback. |
