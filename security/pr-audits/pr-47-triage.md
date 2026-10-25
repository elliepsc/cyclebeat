# PR for issue #47: triage of the contract-guardian review

The main coding agent's verdict on each finding of
[pr-47-contract-guardian.md](pr-47-contract-guardian.md) (pass 1, on 306619e). Each finding was
re-checked against the code before it was fixed.

| # | Finding | Verdict | Where |
|---|---|---|---|
| 1 | The docstring's first line said "Postgres when `DATABASE_URL` is set"; `is_postgres()` needs a `postgresql://` or `postgres://` prefix (`api/repositories/database.py:106-107`) | fixed: "when `DATABASE_URL` is a Postgres DSN" | commit 2ffe72e |
| 2 | "never `DATABASE_URL`" is true of the CI configuration, but the test fixture sets `DATABASE_URL` itself from `TEST_DATABASE_URL` (`tests/unit/test_api_repositories.py:101-103`) | fixed: CI exports only `TEST_DATABASE_URL`, and the fixture derives a per-test `DATABASE_URL` in a throwaway schema | same commit as 1 |
| 3 | README A5 pointed at `database.py:145-158`, moved by the docstring commit | fixed: `database.py:153-167` | commit 59cedd0 |
| 4 | README A9 pointed at `database.py:145-150`, same cause | fixed: `database.py:106-107`, `:153-158` | commit 59cedd0 |
| 5 | "read-only" leaves out the read-write fallback of `readable()` (`api/repositories/warehouse.py:38-42`) | fixed in the README sources table (row A6, A10). The prose ("opens read-only") is kept: the fallback is not hit with the image's warehouse | commit 59cedd0 |

**Found by the agent while fixing 3 and 4.** Following the reviewer's advice to grep for
`database.py:` pointers, `ops/incident-2026-10-15-postgres-down.md:50` cited
`database.py:150` (the `psycopg.connect` line), moved to `:158` by the same docstring commit.
Fixed in 59cedd0. The agent had not run that grep before editing the docstring, which the
"Known pitfalls" of CLAUDE.md ask for. The pointer in `docs/ai-workflow.md` (`database.py:74`)
is pinned to commit 8689d4a and was left as is.
