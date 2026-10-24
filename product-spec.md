# CycleBeat — product specification

**What this document is.** The specification says WHAT CycleBeat does and how each requirement is
accepted. It does not track work: the state of remaining work lives in the
[GitHub issues](https://github.com/elliepsc/cyclebeat/issues) (milestones "Submission" and "Complete
project"). Delivered requirements cite the pull requests and tests that prove them; planned ones cite
their issue. Status as of 22 October 2026, `main` at 9cbae8d.

Normative details stay where they are written once: BPM normalization, zones and confidence in
`cyclebeat/e2.py` and ADR-005/006/010; session construction rules in `cyclebeat/rules.py` and ADR-007;
the HTTP contract in [`openapi.yaml`](openapi.yaml).

## Problem

Indoor cycling instructors build each class by hand: a playlist whose tempo has to follow the effort
(warm-up, climbs, sprints, recovery, cool-down). A track's BPM is the link between music and cadence,
and it is hard to get: Spotify closed its audio-features endpoint to new apps, and metadata BPMs are
often missing or off by a factor of two. CycleBeat resolves a reliable BPM per track, then builds a
session whose segments match the right intensity zone with tracks of the right tempo.

## Users

| User | Need |
|---|---|
| An indoor cycling instructor | generate a session for a level, a goal and a duration, from their own tracks or a demo catalogue; replay it; rate it |
| The data owner (the project's author) | see BPM coverage and data quality; trust the confidence of each BPM |
| A coding agent working on the project | read-only access to the warehouse marts, under guardrails |

## Scope

**In:** BPM resolution from Deezer previews, Deezer metadata and a CSV floor; a Parquet lake and a
DuckDB warehouse modelled with dbt; a deterministic session planner; a contract-first HTTP API; a web
front; persistence of sessions and feedback; containers, CI/CD and a public deployment; read-only
agent tools; security guardrails and scans.

**Out:** storing audio (forbidden, ADR-010); Spotify or YouTube as BPM sources (track identity only);
user accounts and authentication; any paid service. Recorded in [docs/ROADMAP.md](docs/ROADMAP.md)
without an issue: the quality KPI screen, and the other `[présentable]` lines (a reserve, not a plan).

## Functional requirements

Status: **Delivered** (merged, with tests), **Partial** (part merged, the rest in an issue),
**Planned** (an issue). References: `PR #N` for merged work, `issue #N` for remaining work.

| ID | Requirement | Acceptance criteria | Status | Evidence |
|---|---|---|---|---|
| FR-01 | Generate a session from a level, a goal, a duration and a track source | `POST /v1/sessions/generate` with `level` ∈ {beginner, intermediate, advanced}, `goal` ∈ {endurance, intervals, recovery}, `duration_min` 20–120 and a `demo` or `csv` source returns 200 and a plan of segments, each with a zone and tracks; an impossible session returns 422 with structured `reasons`, never a partial plan | Delivered | PR #11 (engine), PR #14 (API), PR #27 (front); `tests/unit/test_planner.py`, `tests/unit/test_planner_properties.py`, `tests/test_api_contract.py`, `tests/integration/test_stack_sessions.py` |
| FR-02 | Sessions follow the construction rules | every session opens on a warm-up and closes on a cool-down; level and goal caps hold; the verdict is `safe` or `review` (ADR-007) | Delivered | PR #11; `tests/unit/test_evaluator.py`, `evals/test_mutation_check.py`, `evals/test_adversarial_playlists.py` |
| FR-03 | Store, list and replay sessions | a generated session can be read back by id and appears in `GET /v1/sessions` (paginated, `limit` 1–200); it survives a container recreate | Delivered | PR #14, PR #18, PR #35; `tests/unit/test_api_repositories.py`, `tests/integration/test_stack_persistence.py` |
| FR-04 | Rate a session | `POST /v1/sessions/{id}/feedback` with `up` or `down` returns 201 and the row is stored | Delivered | PR #14, PR #18; `tests/unit/test_api_services.py`, `tests/integration/test_stack_sessions.py` |
| FR-05 | Resolve a BPM per track with a confidence | the librosa estimate on the 30 s preview and the Deezer BPM are normalized (halve above 180, double below 70) and cross-validated (±3 BPM); the confidence and its method are recorded; a CSV value is the manual floor; no audio is stored | Delivered | PR #10, PR #12, PR #25; `tests/test_de_core.py`, `tests/unit/test_no_audio_storage.py`, dbt test `check_confidence_matches_method.sql` |
| FR-06 | A lake and a modelled warehouse | sources land as Parquet partitions; dbt builds staging, intermediate and marts on DuckDB with schema and singular tests | Delivered | PR #10; `make dbt` (PASS=65 in CI), `tests/test_ingest_pipeline.py` |
| FR-07 | Orchestrated pipeline | three Airflow DAGs (`dag_ingest`, `dag_resolve_bpm`, `dag_build_warehouse`) with no business logic in `dags/` | Delivered | PR #10; `tests/test_dags.py` |
| FR-08 | Data-quality KPIs over HTTP | `GET /v1/quality/coverage` and `/v1/quality/summary` return BPM coverage per source and the quality summary from the marts | Delivered | PR #14; `tests/test_api_contract.py`, `tests/integration/test_stack_quality.py` |
| FR-09 | A web front | a form to generate a session (level, goal, duration), the session view, visible errors (422 reasons, network error) and a cold-start notice; network calls only through the generated client | Delivered | PR #27, PR #29; `frontend/src/screens/*.test.tsx`, `frontend/src/api/contract.test.ts`, `tests/integration/test_stack_browser_access.py`; browser journey checked by the owner on 2026-10-11 (`docs/ai-workflow.md`) |
| FR-10 | Read-only warehouse tools for agents | `query_marts` (one SELECT on the allowed marts, 200 rows max, 5 s) and `get_quality_report` over MCP; they cannot write, read a file, or reach a table off the allowlist | Delivered | PR #38, PR #41; `tests/unit/test_copilot_guards.py`, `tests/unit/test_exposure_warehouse.py`, `tests/unit/test_mcp_server.py` |
| FR-12 | Warehouse KPIs are defined, documented and tested | every mart is described in `schema.yml` with its grain and a uniqueness test; a count is 0 on an empty history while averages, extrema and dates stay NULL; `docs/metrics.md` gives each KPI's definition, grain, formula, source mart and tests | Partial | PR #56, PR #58; `mart_pattern_coverage.effort_bucket`: issue #55; semantic models (MetricFlow), optional: issue #51 |

## Non-functional requirements

| ID | Requirement | Acceptance criteria | Status | Evidence |
|---|---|---|---|---|
| NFR-01 | Zero cost | no paid API, SaaS or cloud instance; demo mode needs no key; free tiers only | Delivered | PR #3, PR #19; `CLAUDE.md` "Zero cost" |
| NFR-02 | No audio stored | every preview download goes through `temporary_download` and is deleted in a `finally` | Delivered | PR #25; `tests/unit/test_no_audio_storage.py` |
| NFR-03 | Contract-first API | `openapi.yaml` written before the backend; the FastAPI schema and schemathesis agree with it; the front client is generated from it | Delivered | PR #14, PR #27; `make contract`, `frontend/src/api/contract.test.ts` |
| NFR-04 | The whole system in one command | `docker compose up --build` starts postgres, api and web with chained healthchecks | Delivered | PR #35; `make test-integration` in CI |
| NFR-05 | Unit and integration tests, one command | both suites exist and pass; one command runs both and fails when either fails (including when Docker is unavailable) | Delivered | PR #35 (both suites), PR #53 (`make test`); `tests/unit/test_agent_team_layout.py` |
| NFR-06 | CI/CD | CI runs every check on each push and pull request; CD deploys after green CI; a dev environment and a manual promotion to production | Partial | PR #30, PR #42 (CI and CD); dev environment and manual promotion: issue #49 |
| NFR-07 | Observability | the `generate` journey traced, structured logs sharing the trace ID with metrics, no customer data in telemetry, a UI | Partial | metrics on `/metrics` (PR #14); traces and logs: issue #48 |
| NFR-08 | An alert on user impact | at least one alert rule on user impact, tested | Planned | issue #48 |
| NFR-09 | An on-call agent | an agent woken by an alert diagnoses and fixes the issue, within the guardrails | Planned | issue #50 |
| NFR-10 | Agent guardrails and security scans | the PreToolUse hook and deny rules refuse writes to `data/`/`lake/`, secrets files, pushes and merges to `main`; Semgrep and gitleaks block in CI | Delivered | PR #38, PR #41, PR #42; `tests/unit/test_agent_hook.py`, `tests/unit/test_security_layout.py`, CI job `security` |

## How the work is tracked

Each block of remaining work is an issue with context, acceptance criteria as checkboxes, out of
scope, the requirement IDs it serves and a definition of done ([issue template](.github/ISSUE_TEMPLATE/work-block.md)).
The process the coding agent follows is in [CLAUDE.md](CLAUDE.md) ("Execution rules"): it reads the
issue, comments its plan there before coding, cites the issue in its commits, and the pull request
closes it.
