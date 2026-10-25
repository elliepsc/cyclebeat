> contract-guardian, second pass on the issue #47 branch, run on 25 October 2026. Diff reviewed: `306619e..ddf96b9` (the fixes for pass 1, [pr-47-contract-guardian.md](pr-47-contract-guardian.md)). Agent definition: `.claude/agents/contract-guardian.md` as on `origin/main`, unchanged on the branch. Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. Finding 6 is triaged in [pr-47-triage.md](pr-47-triage.md).

---

contract-guardian, second pass on `docs/47-finishing-touches`

I checked HEAD ddf96b9 against `origin/main` 2b2b4f0. The diff reviewed is `306619e..HEAD`: 4 commits touching 5 files (`README.md`, `api/repositories/database.py`, `ops/incident-2026-10-15-postgres-down.md` and the two audit files).

Verdict in short: all five pass-1 findings are fixed, every pointer you asked about matches HEAD, and `api/` changed only in the docstring. One non-blocking ambiguity remains (finding 6).

## (1) Pass-1 findings 1-5, checked against HEAD
1. **`api/repositories/database.py:1`: fixed.** It now reads "Postgres when `DATABASE_URL` is a Postgres DSN, SQLite otherwise". That matches `is_postgres()` at `database.py:106-107`, which checks the `postgresql://` / `postgres://` prefix.
2. **`api/repositories/database.py:16-18`: fixed.** It now says CI exports only `TEST_DATABASE_URL` and the test fixture derives a per-test `DATABASE_URL` in a throwaway schema. That matches `tests/unit/test_api_repositories.py:97-103`, where `create schema t_<uuid>` is followed by `monkeypatch.setenv("DATABASE_URL", ...search_path...)`.
3. **`README.md:109` (A5): fixed.** It now cites `database.py:153-167`, which at HEAD is `_connect()` from `def` to `return Database(connection, postgres=False)`, and includes the SQLite branch at 160-167. Pass 1 suggested 153-166; the triage's 153-167 is better because it includes the `return`.
4. **`README.md:115` (A9): fixed.** It now cites `database.py:106-107` (`is_postgres()`) and `:153-158` (`_connect()` up to `psycopg.connect`). Both are exact.
5. **`README.md:110` (A6, A10): fixed in the table.** It now cites `warehouse.py:38-42`, the `read_only=True` try plus the fallback in the except, and `track.py:27` (`with readable(...)`). Both are exact. Keeping the prose "opens read-only" is a reasonable triage call, since the image-baked warehouse never hits the fallback. One nit, not a finding: `readable()`'s own docstring (`warehouse.py:33-34`) gives a second trigger, an open handle on Windows. The README's "(a missing file)" reads as an example, so it is acceptable.

## (2) README "## Architecture" sources table, `api/` pointers at HEAD
- `api/services/session.py:68` is `plan_session(...)` and `:78` is `evaluate(plan, params)`. Both correct.
- `api/repositories/database.py:153-167`, `:106-107` and `:153-158` are correct, as described in (1).
- `api/repositories/warehouse.py:38-42` and `api/repositories/track.py:27` are correct.

## (3) `ops/incident-2026-10-15-postgres-down.md:50`
- `api/repositories/database.py:158` is `return Database(psycopg.connect(url), postgres=True)`. Correct.
- `api/repositories/session.py:34` on the same line is `with connection() as db:`. Correct, and this branch did not move it.

## (4) `git grep -n "database.py:[0-9]"`
- `README.md:109`, `README.md:115` and `ops/...:50` are all correct, as above.
- The hits in `security/pr-audits/pr-47-contract-guardian.md` and `pr-47-triage.md` are review records, correct as of the commit each one names.

6. **`docs/ai-workflow.md:14` (informational, not blocking).** The line reads "`feedback.session_id` has been `NOT NULL` since 8689d4a (`api/repositories/database.py:74`)".
   - At 8689d4a and on `origin/main`, line 74 is `session_id VARCHAR NOT NULL`, so the triage is right that the pointer is correct as of that commit.
   - At HEAD, the docstring commits moved that line to `database.py:82`, and line 74 is now `plan_json TEXT NOT NULL` in `DDL_SESSIONS`.
   - The pinning is implicit: the commit is in the sentence, but the pointer itself does not say it is read at that commit. A reader on main after merge will land on the wrong line.
   - Option A: make the pin explicit, e.g. "`database.py:74` at 8689d4a".
   - Option B: replace the line number with an anchor such as `DDL_FEEDBACK` in `database.py` (CLAUDE.md "Known pitfalls": prefer a section anchor).
   - This is not a contract issue, so it does not change the verdict. Your call.

## (5) No behaviour change in `api/`; `openapi.yaml` untouched
- Both `database.py` hunks in `306619e..HEAD` replace lines one for one inside the module docstring. No code, signature or import changed, and line numbers below did not move in this pass. Across the whole branch (`origin/main...HEAD`) the only `api/` file changed is `database.py`, and only its docstring.
- `git diff --quiet origin/main...HEAD -- openapi.yaml frontend/src/api/` exits 0: both are untouched, so the atomicity rule does not apply.

## Commands run
- `git rev-parse` gave HEAD ddf96b9 and origin/main 2b2b4f0. I also ran `git log`, `git diff --stat 306619e..HEAD`, `git diff 306619e..HEAD -- README.md api/ ops/` and `git diff origin/main...HEAD -- api/`.
- `nl`/`sed` on `database.py` lines 100-170, `warehouse.py` 34-44, `track.py` 25-29, `tests/unit/test_api_repositories.py` 95-106, and `session.py` (services 68/78, repositories 34).
- `git grep -n "database\.py:[0-9]"` and `git grep -n "api/...py:[0-9]" README.md`.
- `git show 8689d4a:api/repositories/database.py` and `git show origin/main:...`, to locate the NOT NULL line at 74 there versus 82 at HEAD.
- `uv run python`: `ast.parse` of `database.py` and `yaml.safe_load` of `openapi.yaml` both succeeded.
- `make contract`: exit 0 (checked directly, no pipe), 25 passed. Log at /tmp/claude-1000/-home-ellie-projets-cyclebeat/3b2179ca-915b-48c2-a94e-0061c3f9438c/scratchpad/contract.log
- I modified no files.

Verdict: APPROVED
