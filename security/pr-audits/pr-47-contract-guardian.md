> contract-guardian, pre-PR review of the issue #47 branch, run on 25 October 2026. Diff reviewed: `origin/main...306619e` (8 commits; the `api/` change is the docstring commit 7d1ddb7). Agent definition: `.claude/agents/contract-guardian.md` as on `origin/main`, unchanged on the branch (`git diff origin/main -- .claude/agents/` is empty). Raw output, unedited: the harness indents a subagent's report, and that indentation is removed. The fixes it led to are in the commits that follow this one; the triage is in `pr-47-triage.md`, next to this file.

---

I'm asking for changes. The `api/` change is only a docstring and its facts are essentially right. But that commit moved `api/repositories/database.py` down by 8 lines, and two README source pointers written in an earlier commit now point at the wrong lines.

I checked against `origin/main` at 2b2b4f0 after a fetch, on the current branch `docs/47-finishing-touches` at 306619e. The diff covers 8 commits and 6 files. `openapi.yaml` and `frontend/src/api/` are not touched, so the atomicity rule does not come into play.

## (1) No behaviour or contract change in `api/`: confirmed
- Both hunks in `api/repositories/database.py` (14 changed lines) sit inside the module docstring, which runs from line 1 to line 30. No code, signature or import changed.
- `make contract` passes: 25 passed, exit code 0 checked directly rather than through the pipe. The module still parses and `openapi.yaml` still loads as YAML.

## (2) The new docstring against the code and the repo
**Confirmed:**
- **Engine choice:** `is_postgres()` (database.py:106-107) and `_connect()` (database.py:153-166) do pick Postgres or SQLite from `DATABASE_URL`.
- **Compose:** it sets `DATABASE_URL=postgresql://...` (docker-compose.yml:69). The CI `integration` job runs `make test-integration` (ci.yml:175), which runs `docker compose up` (Makefile:54, :59). So "compose, so the CI integration job" holds.
- **Render:** `render.yaml:31-37` sets only `RUNTIME_DB_PATH` and `CORS_ALLOW_ORIGINS`, no `DATABASE_URL`.
- **ADR-009:** the "Note (2026-10-11)" exists at docs/adr/adr-009-*.md:108-112. It says decision 4 (Neon) is not what runs, `DATABASE_URL` is absent on Render, and data is lost on redeploy, restart or spin-down. The docstring says "redeploy" only, which is a subset and still true.
- **CI:** the build job exports only `TEST_DATABASE_URL` (ci.yml:32-33, :90). The test suite removes `DATABASE_URL` (tests/conftest.py:78-81).

**Findings:**
1. **api/repositories/database.py:1 (minor, accuracy).** "Postgres when `DATABASE_URL` is set, SQLite otherwise" is slightly too broad. `is_postgres()` (database.py:107) needs a `postgresql://` or `postgres://` prefix. Any other value that is set (a typo, `sqlite:///...`) silently falls back to SQLite. The table at database.py:9-12 states this correctly. Fix: "Postgres when `DATABASE_URL` is a postgres DSN, SQLite otherwise".
2. **api/repositories/database.py:16-18 (minor, accuracy).** "...run on Postgres through `TEST_DATABASE_URL`, never `DATABASE_URL`" is true of the CI configuration but not of the test code it cites. The Postgres branch of the `store` fixture sets `DATABASE_URL` itself, from `TEST_DATABASE_URL` plus a throwaway `search_path` (tests/unit/test_api_repositories.py:101-103), because that is how the app reaches the server. Suggested wording: "CI exports only `TEST_DATABASE_URL`; the fixture derives a per-test `DATABASE_URL` from it, in a throwaway schema".

## (3) README "API" table and architecture A4-A11 against `openapi.yaml` and `api/`
- **API table (README.md:282-288):** matches. It lists 7 operations, which are exactly the 7 in `openapi.yaml` (lines 51-179) and the 7 routes in `api/routers/{health,sessions,quality}.py`.
- **Pointers that hold at HEAD:**
  - planner and evaluator (`api/services/session.py:68`, `:78`)
  - A4 (`render.yaml:36-37`, `:55-56`, `frontend/src/api/client.ts:6`, CORS read in `api/main.py:32-43`)
  - A6/A10 (`warehouse.py:39`, `track.py:27`)
  - A7 (`Dockerfile:40-45`, `render.yaml:32-33`)
  - web (compose) and A8 (`docker-compose.yml:86-92`, `:90`; `frontend/Dockerfile:24-28`)
  - A11 (`docker-compose.yml:60-61`, `:76`)
  - the `Dockerfile:61` CMD

3. **README.md:109 (blocking, stale pointer caused by this branch).** A5 cites `api/repositories/database.py:145-158`. The README commit 712a165 came before the docstring commit 7d1ddb7, which added 8 lines to `database.py`. At HEAD, 145-158 covers `commit()`, `close()` and only the first lines of `_connect()`. The SQLite path (`path = sqlite_path()`, `sqlite3.connect`) now sits at 160-166. Fix: `database.py:153-166`.
4. **README.md:115 (blocking, same cause).** A9 cites `api/repositories/database.py:145-150`. At HEAD that is a blank line, `commit()` and `close()`, with nothing about Postgres. The `is_postgres()` / `psycopg.connect` branch is at 153-158. Fix: `database.py:153-158`, or point at `is_postgres()` at :106-107.
5. **README.md:110 and the prose at README.md:~92 (semantic, informational).** "the API reads the warehouse read-only" leaves out a fallback. `readable()` (api/repositories/warehouse.py:38-42) opens read-write when a read-only open fails, for example when the database file does not exist yet. With the image-baked warehouse this does not trigger in production or compose, so this is not blocking. A clause like "read-only, read-write fallback on a missing file" would make it exact.

## Commands run
- `git fetch origin`; `git diff --stat origin/main...HEAD`; `git diff origin/main...HEAD -- api/`; `git log origin/main..HEAD`
- Python parse of `database.py` and YAML load of `openapi.yaml`: both OK.
- `make contract`: 25 passed, exit 0.
- grep and sed checks of `render.yaml`, `.github/workflows/ci.yml`, `docker-compose.yml`, `Makefile`, `tests/unit/test_api_repositories.py`, `tests/conftest.py`, ADR-009, `api/routers/*`, `api/main.py`, `api/repositories/{database,warehouse,track}.py`, `api/services/session.py`, `Dockerfile`, `frontend/Dockerfile` and `frontend/src/api/client.ts`.
- No files were modified.

Pointer-checking idea: after any edit that adds lines to a file, grep for `database.py:` across the README.

Verdict: CHANGES REQUIRED. Findings 3 and 4 block; 1, 2 and 5 are wording fixes.
