# Cold audit — CycleBeat, 27 October 2026

- **Audited reference:** `origin/main` = `f17725c` (Merge PR #63), cloned fresh from GitHub into a
  scratch directory outside the working copy. The date was read with `date +%F` (2026-10-27).
- **Stance:** a peer who wrote none of the files, following the README. The audit measures and
  reports; it changes nothing in the project.
- **Grids:** the official grid, [docs/grading-criteria.md](../grading-criteria.md) (V2: 12
  criteria, 24 points, 10 to pass), and the old draft,
  [docs/archive/grading-criteria-v1-2026-10-09.md](../archive/grading-criteria-v1-2026-10-09.md)
  (V1: 14 criteria, 30 points). **The two totals are separate and are never added.**
- **Grid copy re-checked against its source:** the fenced text of `docs/grading-criteria.md` is
  identical (`diff`, no output) to `project/README.md` of DataTalksClub/ai-dev-tools-zoomcamp
  fetched through the GitHub API on 27 October 2026. The last commit on that file is still 526d9c1
  (2026-10-16 12:14 UTC).
- **Evidence levels:** EXECUTED (run during this audit, result seen), EXECUTED-CI (seen in a CI run
  log), OBSERVED (read in the repository, not run), ABSENT (looked for, not found).
- **Auditor:** Claude Code (Opus 5.5), session of 27 October 2026.

## Summary

| Grid | Score | Pass mark |
|---|---|---|
| V2, official | **19 / 24** | 10 |
| V1, old draft | **30 / 30** | none shown |

- **Blocking for submission: 2 findings**, both public claims stronger than, or different from, the
  code (B1, B2). No documented command is broken. No criterion is below the level the repository
  announces in [docs/quality-bar.md](../quality-bar.md).
- **[présentable]: 10 findings.** The most important is P1, a security finding on the public API.
- V2 loses its 5 points on CI/CD (level 3), Observability, Alerting and the On-call agent. The
  repository already declares all four as gaps (issues #48, #49, #50).

## Commands run from the fresh clone

All of them were run in the scratch clone, never in the working copy's `data/` or `lake/`.

| Command (as written in the README) | Exit | Result |
|---|---|---|
| `git clone https://github.com/elliepsc/cyclebeat.git` | 0 | `f17725c` |
| `make setup` | 0 | environment from `uv.lock` |
| `make test` | 0 | unit 808 passed, 15 skipped, 2 xfailed (100 s); integration 13 passed (9.3 s); `make test: unit and integration suites passed`; 11 min 25 s wall clock, both images built from cold for this clone |
| `make ingest` | **not run** | refused to the agent by the PreToolUse hook: `make ingest writes lake/ and data/` (`agent-hooks/pre_tool_use.py`, the `MAKE_WRITES_LAKE` rule). The refusal was reported, not worked around. See "Owner checks" |
| `make dbt` | **not run** | needs the warehouse that `make ingest` builds. The same steps did run inside the image build: `Done. PASS=106 WARN=0 ERROR=0` in the `docker compose up --build` log |
| `docker compose up --build` | 0 | the 3 services reported `(healthy)` 29 s after start (images already built by `make test`); web `GET /` 200; `GET /health` 200; `POST /v1/sessions/generate` (demo source) 200, verdict `safe`; the dbt build inside the image: PASS=106 |
| `docker compose down -v` | 0 | volume `fresh_postgres_data` removed |
| `make front-test` | 0 | vitest: 4 files, 14 tests passed (Node 24.19.0, as in `frontend/.nvmrc`) |
| `make front-gen` | 0 | `git status` empty afterwards: the committed client matches `openapi.yaml` |
| `make api` (without `make ingest`) | killed after 25 s | `/health` 200; generate 422 `empty_catalogue`, as expected: the README runs `make ingest` and `make dbt` first |
| `make front` | not run | a long-running dev server; its build path is covered by `make front-test` and by the image build |
| `GET` on the public URLs | **not run** | refused by the Claude Code auto-mode classifier. Not retried. Public reachability is taken from CI instead (below) |

**CI on the same commit:** run [40583093914](https://github.com/elliepsc/cyclebeat/actions/runs/40583093914)
(push to `main`, `f17725c`). All 5 jobs succeeded:
- `build`: lint; unit 808 passed; repository tests on Postgres 43 passed; evals 55 passed;
  `make ingest` then `make dbt` PASS=106; contract 25 passed;
- `frontend`: 14 passed;
- `integration`: 13 passed;
- `security`: passed;
- `deploy`: `smoke health: ok`, `smoke generate: ok`, `smoke cors: ok`, `smoke web: ok`,
  `deploy ok` (21:04:39 UTC).

## V2 — official grid

| Criterion | Points | Evidence | Missing for the next level |
|---|---|---|---|
| Problem Description | 2 / 2 | OBSERVED: `README.md:3-9` (what the system does), "Why this project" (`README.md:45-50`, the BPM problem), "What it looks like" (`README.md:24-43`, the expected behaviour, with screenshots) | Ceiling |
| Product Specification | 2 / 2 | OBSERVED: [product-spec.md](../../product-spec.md) (FR/NFR tables with acceptance criteria, status, evidence). Public tracker: `gh issue list --state all` returns 12 issues, all with checkbox acceptance criteria. Comments starting "Posted by the coding agent" appear on #44, #45, #46, #47, #48, #49, #54, #55 and #60 | Ceiling |
| Agent Team Specification | 2 / 2 | OBSERVED: [docs/agent-team.md](../agent-team.md), "Roles" (owner, main agent, 4 subagents, triggers, write scope) and "The process, step by step"; `.claude/agents/` holds the 4 definitions | Ceiling |
| Context Management | 2 / 2 | OBSERVED: `AGENTS.md:3` points to `CLAUDE.md` and `AGENTS.md:7` to `docs/agent-team.md`; `CLAUDE.md` points to the ROADMAP, the ADR index, product-spec, `docs/permissions.md` and `docs/agent-team.md` | Ceiling |
| Application | 2 / 2 | EXECUTED: `docker compose up --build` gave web 200 and generate 200 against Postgres; `test_session_survives_an_api_recreate` passed under `make test`, which shows that the session lives in Postgres | Ceiling |
| Testing | 2 / 2 | EXECUTED: `make test` exit 0 (808 unit and 13 integration tests) | Ceiling |
| Containerization | 2 / 2 | EXECUTED: one command, 3 services healthy, database included (`docker-compose.yml`, `postgres:16-alpine`) | Ceiling |
| Deployment | 2 / 2 | EXECUTED-CI: smoke tests of the live API and site in run 40583093914, today. Not reached by the auditor (classifier refusal) | Ceiling |
| CI/CD | 2 / 3 | EXECUTED-CI: tests on every push and PR (`ci.yml:7-11`); `deploy` runs automatically on `main` after the 4 test jobs (`ci.yml:199-203`) | Level 3: CD to a dev environment and a **manual** deploy to production. The `production` environment has no required reviewer (`CONTRIBUTING.md`, "Deployment"). Issue #49 |
| Observability | 1 / 2 | OBSERVED: Prometheus metrics (`api/main.py:74-83`, `prometheus-fastapi-instrumentator`) and uvicorn logs. No tracing library and no trace ID (grep for `opentelemetry`, `trace_id`, `traceparent`, `structlog` over `api`, `cyclebeat`, `monitoring` and `pyproject.toml`: empty) | Traces, structured logs and metrics sharing a trace ID on the `generate` journey, no customer data, viewable in a UI (P7: Grafana has no dashboard). Issue #48 |
| Alerting on User Impact | 0 / 1 | ABSENT: no rule in `monitoring/` (grep for `alert`, `rule_files`, `alertmanager`: empty) | One alert on user impact. Issue #48 |
| On-Call Agent | 0 / 2 | ABSENT: `ops/` holds an incident diagnosed by hand | An agent woken by the alert that fixes the issue. Issue #50 |
| **Total** | **19 / 24** | | |

## V1 — old draft grid

| # | Criterion | Points | Evidence | Missing for the next level |
|---|---|---|---|---|
| 1 | Problem Description | 2 / 2 | as V2 | Ceiling |
| 2 | AI-Assisted Development Workflow | 2 / 2 | OBSERVED: [docs/ai-workflow.md](../ai-workflow.md), one section per session with prompt, iterations, "Corrected by human review", verification and role split | Ceiling |
| 3 | Technologies and System Architecture | 2 / 2 | OBSERVED: the README diagram covers CI, production, compose and the pipeline. 12 of its source rows were checked: 11 hold, 1 is inaccurate (B1) | Ceiling (B1 is a fix of accuracy, not of level) |
| 4 | Frontend Implementation | 3 / 3 | EXECUTED: `make front-test` 14 passed. OBSERVED: `frontend/src/api/sessions.ts:1` is the only network module; grep for `fetch(`, `axios` and `XMLHttpRequest` outside `frontend/src/api/` (tests excluded): empty. Instructions: `README.md:282-288` | Ceiling |
| 5 | API Contract | 2 / 2 | EXECUTED: `make front-gen`, no drift. EXECUTED-CI: `make contract` 25 passed | Ceiling |
| 6 | Backend Implementation | 3 / 3 | OBSERVED: routers → services → repositories ([backend/README.md](../../backend/README.md)). EXECUTED: 808 unit tests | Ceiling |
| 7 | Database Integration | 2 / 2 | OBSERVED: engine chosen by `DATABASE_URL` (`api/repositories/database.py:104-167`), documented at `README.md:171-179` and in ADR-009. EXECUTED-CI: repository tests on Postgres, 43 passed | Ceiling |
| 8 | Containerization | 2 / 2 | EXECUTED, as V2 | Ceiling |
| 9 | Integration Testing | 2 / 2 | EXECUTED: `tests/integration/`, run on its own (`Makefile:57-71`), documented (`README.md:244-269`), 13 passed | Ceiling |
| 10 | Deployment | 2 / 2 | EXECUTED-CI, as V2 | Ceiling |
| 11 | CI/CD Pipeline | 2 / 2 | EXECUTED-CI: tests, then deploy once they are green | Ceiling |
| 12 | Agent Extension Pack | 2 / 2 | OBSERVED: `.claude/agents/` (4), `.claude/skills/new-mart`, `mcp-server/`, `agent-hooks/pre_tool_use.py`, `plugins/cyclebeat-agent-pack/`, [docs/agent-extension-pack.md](../agent-extension-pack.md), [docs/permissions.md](../permissions.md). The hook refused this audit twice, as documented | Ceiling |
| 13 | Security, Audit, DevOps Hardening | 2 / 2 | OBSERVED: `security/pr-audits/`, `security/scans/2026-10-20.md`, `security/agent-security.md`, `security/ai-policy.md`, `ops/incident-2026-10-15-postgres-down.md`. EXECUTED-CI: job `security` | Ceiling (P1 is a new finding for `security/scans/` or an issue) |
| 14 | Reproducibility | 2 / 2 | EXECUTED: setup, test and compose from a fresh clone. EXECUTED-CI and EXECUTED in the image build: ingest and dbt. Deployment documented (`CONTRIBUTING.md`, "Deployment") | Ceiling. The host `make ingest && make dbt` path is still to be run by the owner (below) |
| | **Total** | **30 / 30** | | |

## Public claims checked against the code

### Architecture table (README, "Every box and arrow above")

The 29 rows were numbered, and 12 were drawn with
`shuf -n 12 --random-source=<(yes 20261027)`. The draw can be replayed.

| Row | Claim | Verdict |
|---|---|---|
| cyclebeat-web | Render static site built by Vite, `render.yaml:42-47` | holds |
| planner + evaluator | `api/services/session.py:68` (`plan_session`), `:78` (`evaluate`) | holds |
| A6, A10 | read-only open, read-write fallback, `api/repositories/warehouse.py:38-42`; `track.py:27` | holds |
| web (compose) | nginx serves the bundle, `docker-compose.yml:86-92`, `frontend/Dockerfile:24-28` | holds |
| api (compose), A11 | `build: .` at `docker-compose.yml:60-61`, uvicorn at `:76` | holds |
| A8 | `VITE_API_URL` at `docker-compose.yml:90`; `frontend/src/api/client.ts:6` | holds |
| A9, postgres | `docker-compose.yml:40-47`, `:69`; `database.py:106-107`, `:153-158` | holds |
| sources | demo, live, CSV at `cyclebeat/cli.py:48-67`; patterns at `ingest/ingest_pipeline.py:43` | holds |
| A12 | `_write_batch` at `cyclebeat/cli.py:69`; `Makefile:94` | holds |
| A13 | "dlt loads the patterns into DuckDB", an arrow into `data/cyclebeat_runtime.duckdb` | **inaccurate: B1** |
| A16 | `dbt/profiles.yml:8`; `Makefile:82` | holds |
| A17 | `dags/dag_ingest.py:84`; `dags/dag_resolve_bpm.py:94` | holds |

### product-spec.md, "Delivered" rows

Every test file cited by a Delivered row is tracked (`git ls-files --error-unmatch`, 23 paths, plus
`frontend/src/screens/*.test.tsx` and `dbt/tests/check_confidence_matches_method.sql`). The
acceptance criteria were checked against the code:
- FR-01: `duration_min` 20-120 at `openapi.yaml:279-280`; generate 200 executed.
- FR-03: `test_session_survives_an_api_recreate` passed.
- FR-04: `rating` enum `[up, down]` at `openapi.yaml:401`; the front's "Good" sends `up`
  (`SessionView.tsx:44-48`); the 404 test passed.
- FR-09: cold-start notice at `GenerateForm.tsx:102`; network errors at `api/sessions.ts:23`; the
  owner's note at `docs/ai-workflow.md`, "Note 2026-10-11 (owner, before merging PR #35)".
- Partial and Planned rows: issues #48, #49, #50, #51 and #57 are open.

One Delivered row carries a wrong figure: FR-06 (B2).

### Screenshots

The four README images (`docs/screenshots/form.png`, `run.png`, `rate.png`,
`rate_confirmation.png`) are tracked, not ignored (`git check-ignore` returns nothing). They are PNGs
and were opened. Each matches its alt text: the form set to beginner, endurance, 30; a 30:46
session, verdict safe, 8 tracks from Z1 to Z4; "Good" with the note "Great session"; "Thanks, your
feedback was recorded."

## Findings

### Blocking for submission

**B1 — README architecture, arrow A13: the patterns do not reach the runtime DuckDB through dlt.**
The README row says "dlt loads the patterns into DuckDB", and the diagram draws A13 into
`data/cyclebeat_runtime.duckdb`. In the code, dlt's `duckdb` destination is given no path
(`ingest/ingest_pipeline.py:51-56`). The dlt documentation says: "By default, `dlt` creates a
DuckDB database in the current working directory", named after the pipeline
(<https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb>), here `cyclebeat_ingestion`. The
runtime DuckDB receives the patterns through a plain write, `db.runtime.save_patterns`
(`ingest/ingest_pipeline.py:59-61`, `db/runtime.py:63`).
*Fix:* reword A13, for example "dlt stages the patterns; `save_patterns` mirrors them into DuckDB",
and cite `:59-61`.

**B2 — product-spec.md, FR-06: "`make dbt` (PASS=65 in CI)".**
CI on `f17725c` reports `PASS=106` (run 40583093914, job `build`, step "dbt build"). The README says
counts belong in PR descriptions.
*Fix:* drop the figure, or date it with its run.

### [présentable]

**P1 — security: the `csv` source opens a server-side path supplied by any HTTP caller.**
`POST /v1/sessions/generate` with `source.type = csv` passes `source.value` to `open()`
(`api/services/session.py:119-133`, `cyclebeat/sources/csv_source.py:42`). The path is not checked
and no authentication is needed. Executed on the local compose stack:

| Path | Response |
|---|---|
| `/nope.csv` | 422 `csv_not_found` |
| `/etc/passwd` | 422 `empty_catalogue` |
| `/app/data/cycling_patterns.json` | 422 `empty_catalogue` |
| `/app` | **500** |

So the API reveals whether a file exists, and a directory crashes the request. A readable file with
`artist` and `title` columns would have those values echoed in the session. Production runs the same
image (`render.yaml`), so it is very likely affected too. That is inferred, not run: the audit sent
no request to production. This finding does not appear in `security/`; the only hits for those
terms are about `sniff_csv` in `query_marts`.
*Owner's call:* restrict `value` to an allowlisted directory, or refuse `csv` over HTTP in
`DEMO_MODE`.

**P2 — `openapi.yaml:268`.** It says `deezer_url` "is refused with 422 under `DEMO_MODE`", which
suggests that it works otherwise. The code always refuses it, with `deezer_url_not_implemented`
(`api/services/session.py:142-145`).

**P3 — `docs/ROADMAP.md` is written in French.** The README links it as "Detailed roadmap", and
`CLAUDE.md` points to it. The official grid says "Documentation in English … Reviewers cannot be
assumed to read it", and `CLAUDE.md` asks for repo docs in English. It is the only tracked document
outside `docs/archive/` and `security/pr-audits/` that is mostly in French.

**P4 — `CONTRIBUTING.md`, "Deployment".** It says `deploy` runs "after the `build`, `frontend` and
`integration` jobs". `ci.yml:199` also waits for `security`, and the README says "the four test
jobs". The doc understates the code.

**P5 — `product-spec.md:7`.** "Status as of 22 October 2026, `main` at 9cbae8d", while FR-12 cites
PR #61 and PR #62, merged on 25 October.

**P6 — `docs/quality-bar.md:14`.** "State as of 22 October 2026, `main` at 31e2d26". The
Reproducibility row says "not re-run since" 16 October; this audit re-ran it.

**P7 — Grafana has no dashboard.** `monitoring/grafana/provisioning/dashboards/dashboard.yml`
declares a provider, but `git ls-files monitoring` lists no dashboard JSON (3 files). The
`monitoring` profile opens an empty Grafana. This is relevant to V2 Observability, level 2
("viewable in a UI").

**P8 — `product-spec.md`.** The FR numbering skips FR-11.

**P9 — process.** No issue covers this audit: CLAUDE.md asks for one per block of work. The commit
therefore cites no `#N`.

**P10 — the host pipeline path is not reproduced by the agent.** The hook refuses `make ingest` to
the agent unconditionally. This audit could not run the README's "Without Docker" `make ingest`,
then `make dbt`, from the fresh clone. The same steps passed in CI and inside the image build.

## Owner checks (not simulated)

1. In the fresh clone, `make ingest`, then `make dbt`, then `make api`, then a demo generate. Record
   each exit code. The clone is in the agent's scratch directory, outside the working copy:
   `/tmp/claude-1000/-home-ellie-projets-cyclebeat/b05001f3-3558-4acc-a53a-56c81ca79747/scratchpad/fresh`.
2. A browser check of <https://cyclebeat-web.onrender.com/>. The agent's own requests to the public
   URLs were refused.
3. A decision on P1.
