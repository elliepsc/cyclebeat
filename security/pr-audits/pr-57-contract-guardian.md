<!-- Provenance: raw final report of the `contract-guardian` subagent (`.claude/agents/contract-guardian.md`, unchanged from origin/main b88070f), run on branch fix/57-lake-utc at 73dc62a on 2026-10-29. Committed verbatim; this header is the only addition. -->

# contract-guardian review: `fix/57-lake-utc` (#57)

**Reference:** I ran `git branch --show-current` and got `fix/57-lake-utc`. All claims are checked against `origin/main` at `b39a021`, which is also the merge base after `git fetch`.

## Verdict: APPROVE

The contract-first rule is respected. `openapi.yaml` and `frontend/` are byte-identical to `origin/main`. The only change under `api/` is in `api/repositories/database.py` (+7/-1), and it adds no field, no shape and no endpoint. Nothing here blocks the merge. Finding 2 below is an existing contract defect that this PR makes cheap to fix. It should become a follow-up issue, not a change to this PR's scope.

## Findings

**1. The contract is not affected, and only one endpoint shows the session time zone (informational).**

`git diff origin/main -- api/ openapi.yaml frontend/` touches only `api/repositories/database.py`, in `_connect()`, at the `SET TIME ZONE 'UTC'` lines. There are three `created_at` fields: `SessionPlan` (openapi.yaml, `components.schemas.SessionPlan`), `SessionSummary` and `Feedback`. Each one gets its value from a different place:

- `POST /v1/sessions/generate` uses `SessionPlan.created_at` from `datetime.now(UTC)` in memory (`api/services/session.py`, `generate`). The column is not read back. **Unchanged.**
- `GET /v1/sessions/{session_id}` replays `plan_json`, a text blob already serialized with its offset (`api/repositories/session.py`, `get`). The `TIMESTAMP` column is not read. **Unchanged.**
- `POST /v1/sessions/{session_id}/feedback` returns the in-memory aware `created_at` (`api/repositories/feedback.py`, `add`). **Unchanged.** `FeedbackRepository.for_session` does read the column, but no router calls it: I grepped `api/` for `for_session` and found no caller outside the repository.
- `GET /v1/sessions` (list, `api/routers/sessions.py` `list_sessions` → `api/services/session.py` `list` → `api/repositories/session.py` `list`, `select ... created_at` and `"created_at": r[7]`) **is the only endpoint that serializes the Postgres `TIMESTAMP` column.** The values are not actually different for rows written before vs after:
  - **SQLite (no `DATABASE_URL`, which includes Render production today):** the change does not apply. Nothing changes.
  - **Postgres whose session zone was already UTC:** this covers compose and CI with `postgres:16-alpine`. I ran `SHOW timezone` on the local `postgres:16-alpine` and it returned `UTC`. The stored wall time is identical before and after, so the serialized value does not change.
  - **Postgres with a non-UTC session zone** (set in the DSN `options`, `PGTZ`, or `ALTER ROLE/DATABASE ... SET timezone`): I measured this in psql. An aware `2026-07-10 22:30:00+00` is stored as `2026-07-11 00:30:00` under `Europe/Paris` and as `2026-07-10 22:30:00` under `UTC`. **Rows written before** the change keep their local wall time, because nothing migrates them, and the API serves them as `"2026-07-11T00:30:00"`. **Rows written after** are served as `"2026-07-10T22:30:00"`. The same list would then mix two meanings, and `order by created_at desc` could interleave them by up to the zone offset. No environment of this repo is known to run that configuration (production has no `DATABASE_URL`, per the CLAUDE.md pitfall). So this is a theoretical data caveat, not a contract change. It belongs in the PR description next to the "pre-#57 partitions" note.

**2. Existing defect, not introduced here: on Postgres, `GET /v1/sessions` returns `created_at` with no offset, which `format: date-time` does not allow (follow-up, non-blocking).**

psycopg 3 loads `timestamp` (without time zone) as a naive `datetime`. Pydantic serializes a naive value with no offset. I measured this through `api.schemas.SessionSummary.model_dump_json()`: a naive value gives `"2026-07-10T22:30:00"`, an aware UTC value gives `"2026-07-10T22:30:00Z"`. OpenAPI `format: date-time` is RFC 3339 `date-time`, which requires a `time-offset`. On SQLite, the converter in `_register_sqlite_datetime_handlers` (`api/repositories/database.py`) gives back an aware value, so the two engines already serialize differently. Before this PR, nothing guaranteed which zone that naive wall time was in. Now `_connect()` pins it to UTC, so a one-line fix becomes correct: in `SessionRepository.list`, return `r[7].replace(tzinfo=UTC)` when it is naive, the same rule `cyclebeat/app_store.py` now applies on the lake side. Do it in its own issue, with a Postgres-backed contract test. Adding it to this PR would widen the phase scope.

**3. The `SET TIME ZONE 'UTC'` plus commit at connect time is correct with psycopg 3.3.4 (informational).**

- `psycopg.connect(url)` opens a non-autocommit connection, which is the psycopg 3 default. `connection_pg.execute(...)` implicitly opens a transaction. `SET` without `LOCAL` is session-scoped, but PostgreSQL reverts it if its transaction rolls back. I checked this in psql: `BEGIN; SET TIME ZONE 'Asia/Tokyo'; ROLLBACK; SHOW timezone` gives back `UTC`. The explicit `commit()` makes the setting outlive any later rollback and leaves the connection IDLE before the DDL. It is required for correctness when `connection(create=False)` and the operation fails, and harmless otherwise.
- The `SET` overrides any `-ctimezone=...` passed through the DSN `options`. The new test depends on this: the fixture sets `Europe/Paris`, and the test checks with a separate raw connection that the zone really is non-UTC.
- No connection is reused. `Database` is opened per operation in `connection()` and closed in `finally`, and there is no pool. So every Postgres connection goes through `_connect()` and gets the `SET`, and none can escape it.
- A minor alternative, not required: `psycopg.connect(url, options="-c TimeZone=UTC")` would save one round trip. But psycopg merges keyword arguments over DSN parameters, so it would *replace* the caller's `options`, including the test's `search_path`. The explicit `SET` composes better. Keep it as written.

**4. SQL stays inside `api/repositories/` (informational).**

The only new SQL text under `api/` is the `SET` in `api/repositories/database.py`. I grepped the `+`/`-` lines of `git diff origin/main -- cyclebeat/app_store.py` for `select|insert|set|from|execute` and found no added or removed SQL. The `select` statements in `cyclebeat/app_store.py` already exist on `origin/main` (the pipeline's store extractor). They come from before this PR and it does not change them.

**5. Contract-first atomicity (informational).**

`openapi.yaml` is unchanged and no response model in `api/schemas.py` or `api/routers/` changed. The front client does not need regenerating, and no breaking-change analysis is needed.

## Commands run and results

- `git branch --show-current` gave `fix/57-lake-utc`. `git merge-base HEAD origin/main` and `git rev-parse origin/main` both gave `b39a021`.
- `git diff --stat origin/main -- api/ openapi.yaml frontend/`: 1 file, `api/repositories/database.py`, +7/-1.
- `uv run python -c "import yaml; yaml.safe_load(open('openapi.yaml'))"`: parses, `openapi: 3.1.0`, 7 paths.
- `uv run pytest -p no:randomly tests/test_api_contract.py tests/unit/test_api_repositories.py`: exit code 0, **54 passed, 16 skipped**. The 16 skips are the Postgres cases: `TEST_DATABASE_URL` was not set in my environment, and I did not read the credentials of the running `cyclebeat-pg57` container. **I did not run the Postgres half of `test_a_stored_row_reaches_the_lake_at_the_same_utc_instant` myself.** `security/pr-audits/pr-57-dbt-reviewer.md` reports it as 2 passed (sqlite and postgres), and I have not reproduced that.
- `docker exec cyclebeat-pg57 psql ...` (temp table only, nothing persisted): server default `TimeZone` is `UTC`. The same aware instant is stored as `2026-07-11 00:30:00` under `Europe/Paris` and as `2026-07-10 22:30:00` under `UTC`. A `SET` inside a rolled-back transaction is reverted.
- `uv run python -c` serializing `api.schemas.SessionSummary` gives `"2026-07-10T22:30:00"` for a naive value and `"2026-07-10T22:30:00Z"` for an aware UTC value (finding 2).
- `uv run ruff check api/repositories/database.py`: all checks passed. `uv run mypy --strict api/repositories/database.py`: no issues.
- `uv run python -c "import psycopg; print(psycopg.__version__)"` gave `3.3.4`.

## Relevant files

- `api/repositories/database.py`: the only change, `_connect()`.
- `api/repositories/session.py`: `SessionRepository.list`, the one read that reaches the API.
- `api/repositories/feedback.py`: `for_session`, not exposed by any endpoint.
- `api/schemas.py`: `SessionSummary.created_at`, `SessionPlan.created_at`, `Feedback.created_at`.
- `openapi.yaml`: `components.schemas.SessionSummary.created_at`, `format: date-time`.
- `tests/unit/test_api_repositories.py`: `test_a_stored_row_reaches_the_lake_at_the_same_utc_instant`.
