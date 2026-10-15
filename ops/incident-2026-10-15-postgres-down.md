# Incident diagnosis — Postgres down, API "healthy" (reproduced 15 October 2026)

**Where**: the compose project `cyclebeat-it` ONLY (the integration-test project), ports 18000
(API) and 14173 (web), on the developer machine. Never production, never the developer's own
`cyclebeat` stack. **How**: the script [`evidence/2026-10-15-postgres-down.sh`](evidence/2026-10-15-postgres-down.sh),
every command timestamped (UTC) with its output in
[`evidence/2026-10-15-postgres-down.log`](evidence/2026-10-15-postgres-down.log). Every
statement below cites the log line it rests on (`log:N`). The stack was torn down at the end.

First seen in phase 8: `make test-integration` with Postgres stopped gave 6 failed / 7 passed,
and "api stayed healthy" (`docs/ai-workflow.md`, phase 8 entry). This document reproduces it on
purpose and measures what the phase-8 run did not: the HTTP answers, the recovery, and whether
a session was half-written.

## Timeline (UTC)

| Time | Event | Evidence |
|---|---|---|
| 14:14:45 → 14:15:21 | stack built and up, all three services `(healthy)` | log:330-333 |
| 14:15:24.3 | baseline: `GET /health` 200, `POST /v1/sessions/generate` 200 in 0.16 s, 1 session stored, 0 incomplete | log:338-339, log:344, log:348 |
| 14:15:24.6 | `docker compose -p cyclebeat-it stop postgres` | log:352-354 |
| 14:15:34 | `ps`: postgres gone, **api still `(healthy)`**, web `(healthy)` | log:361-363 |
| 14:15:37.1 | `GET /health` → **200** `{"status":"ok"}` | log:367-368 |
| 14:15:37.1 | `POST /v1/sessions/generate` → **500** after 4.04 s | log:372-373 |
| 14:15:41.0 | second generate → **500** after 3.17 s | log:377-378 |
| 14:15:48.5 | `docker compose -p cyclebeat-it start postgres` | log:562 |
| +7.2 s | postgres `(healthy)` again (polled every 1 s) | log:566, log:571 |
| 14:16:05.0 | **first generate after recovery → 200** in 0.037 s; the next one too | log:578, log:583 |
| 14:16:05.1 | 3 sessions stored, 0 incomplete; each has 13 segments in the row and 13 in its JSON | log:587, log:591-593 |
| 14:16:05 → 14:16:11 | `down -v`: containers, volume and network removed; `ps -a` empty | log:599-612, log:616-617 |

## Symptoms

- The orchestrator and the health endpoint both said the API was fine: `(healthy)` with
  Postgres stopped (log:362) and `GET /health` 200 (log:367-368).
- The business endpoint failed: `POST /v1/sessions/generate` answered 500 (log:373, log:378),
  as an RFC 7807 body with a generic detail, `"The request could not be completed."`
  (log:372) — no stack trace and no connection string reached the client.
- Each failing call took 3-4 s instead of 0.16 s (log:373, log:378 vs log:344): the API waited on
  name resolution of a host that no longer existed.

## Root cause

1. **Liveness answered a readiness question.** `/health` returns `{"status": "ok"}` without
   touching any dependency (`api/routers/health.py:16-18`), and the compose healthcheck of the
   `api` service curls exactly that route (`docker-compose.yml:78`). Nothing in the stack checks
   that the API can reach Postgres, so a stopped database leaves every service "healthy".
2. **Generation writes to Postgres.** `SessionService.generate` stores the plan before returning
   it (`api/services/session.py:110`); the store opens a Postgres connection
   (`api/repositories/session.py:34`, `api/repositories/database.py:150`). With the `postgres`
   container stopped, its name no longer resolves on the compose network:
   `psycopg.OperationalError: failed to resolve host 'postgres'` (log:473, log:557), which the
   last-resort handler turns into the generic 500 (`api/errors.py:100-114`).

## Data integrity: no session was half-written

- Before the outage: 1 session, 0 incomplete (log:348). After two failed calls and two
  successful ones: 3 sessions, 0 incomplete (log:587). 1 + 0 + 2 = 3: the failed calls wrote
  nothing, the successful ones one row each.
- Why it cannot be half-written: the failure happens when the connection is opened, before any
  statement (log:473 traceback ends in `psycopg.connect`), and a session is stored by ONE
  `INSERT ... ON CONFLICT DO UPDATE` (`api/repositories/session.py:35-50`), atomic on its own.
- The three rows are consistent: `n_segments` equals the number of segments in `plan_json` for
  each (log:591-593).

## Recovery

No restart of the API was needed: 7.2 s after `start postgres` the database was healthy
(log:566), and the very first generate after that succeeded (log:578). The API opens a
connection per request, so it reconnects by itself.

## Proposed correction (recorded, not coded — it changes the HTTP contract)

A readiness endpoint that checks the dependencies (a `select 1` on the transactional store, and
that the analytical warehouse is readable), returning 503 when one is down, declared in
`openapi.yaml` with the backend and the generated client in the same PR; the compose healthcheck
of `api` then curls readiness, not liveness. Recorded in `docs/ROADMAP.md` (`[présentable]`),
next to the defect already recorded for `readable()` — the same family: when the analytical
warehouse is absent, `readable()` falls back to a writable connection on an empty DuckDB and
the API answers 422 `empty_catalogue` while staying "healthy". Both are a liveness check
standing in for readiness.

## Follow-up

- Readiness endpoint + healthcheck: ROADMAP `[présentable]`, owner decision on the contract change.
- The integration suite already has the failure proof (phase 8); a test asserting a 503 from
  readiness with Postgres stopped belongs to the readiness PR.
