# 🚴 CycleBeat — music-to-workout data product

CycleBeat turns a playlist into a structured indoor-cycling session: every track gets a tempo,
a cadence, a resistance and an effort phase, and the whole session is checked for safety and
coherence before it is served.

Under the hood it is a **data-engineering project first**: a multi-source ingestion pipeline,
a Parquet lake, a DuckDB warehouse modelled with dbt, a deterministic planning engine with its
own evaluator, and a contract-first API.

> **Status (October 2026): work in progress — AI Dev Tools Zoomcamp 2026 project.**
> The data pipeline, the engine, the API and the frontend are done and tested, and both the API
> and the site are deployed. What remains is in the [Roadmap](#roadmap).
>
> **Live site:** <https://cyclebeat-web.onrender.com/> · **Live API:** <https://cyclebeat-api.onrender.com/> · interactive docs: <https://cyclebeat-api.onrender.com/docs>
> (`GET /health`, `POST /v1/sessions/generate` with the demo source). It runs on Render's free
> tier on a demo database baked into the image, which resets on every deploy ([ADR-003](docs/adr/adr-003-render-no-disk.md)); the free tier
> also spins down when idle, so the first request after a pause can be slow.
>
> CI and deployment run in GitHub Actions; Render deploys only on the pipeline's order, after green tests.

---

## What it looks like

Pick a level, a goal and a duration, then generate a session:

![The "Plan a session" form: level Beginner, goal Endurance, 30 minutes](docs/screenshots/form.png)

The generated session: the evaluator's verdict, then one row per track with its role, zone, BPM,
BPM confidence and duration, and the form to rate the session:

![A generated 30-minute beginner endurance session, verdict safe, 8 tracks from Z1 to Z4](docs/screenshots/run.png)

Then rate it, with an optional note:

![The rating form of the same session, filled in: "Good", with the note "Great session", above the Send feedback button](docs/screenshots/rate.png)

Screenshots taken by the owner, in a browser, on 25 October 2026.

## Why this project

Indoor-cycling classes tie riders to a fixed playlist and a fixed instructor. CycleBeat starts from
the rider's own music. The hard part is not the UI: it is getting a **reliable BPM** for mainstream
tracks now that the Spotify audio-analysis endpoints are closed to new apps, and turning those BPMs
into a session that is **coherent and safe**.

## Architecture

```mermaid
flowchart LR
  subgraph CI["CI: GitHub Actions"]
    tests["build · frontend ·<br/>integration · security"]
    deploy["deploy<br/>main only"]
  end
  subgraph PROD["Production: Render, free tier"]
    webp["cyclebeat-web<br/>static site, React bundle"]
    apip["cyclebeat-api<br/>FastAPI: planner + evaluator<br/>runs uvicorn only"]
    sqlitep[("SQLite inside the container<br/>sessions, feedback")]
    duckp[("DuckDB<br/>baked into the image")]
  end
  build["API image build, once per deploy<br/>patterns + demo snapshot → lake<br/>→ DuckDB → dbt build"]
  subgraph COMPOSE["Local: docker compose up --build"]
    webc["web<br/>nginx, React bundle"]
    apic["api<br/>same image"]
    pg[("postgres<br/>sessions, feedback")]
    duckc[("DuckDB<br/>baked into the image")]
  end
  subgraph PIPE["Local pipeline: make ingest · make dbt, or the compose profile pipeline"]
    src["Deezer demo snapshot or live API<br/>· CSV · patterns JSON"]
    store[("app store<br/>SQLite, or Postgres<br/>when DATABASE_URL is set")]
    lake[("Parquet lake<br/>lake/")]
    duckl[("DuckDB<br/>data/cyclebeat_runtime.duckdb")]
    dbt["dbt<br/>staging → intermediate → marts"]
    airflow["Airflow 3<br/>3 chained DAGs"]
  end

  tests -->|"A1"| deploy
  deploy -->|"A2 deploy hooks"| webp
  deploy -->|"A3 deploy hook"| apip
  webp -->|"A4 HTTPS"| apip
  apip -->|"A5"| sqlitep
  apip -->|"A6 read-only"| duckp
  build -->|"A7"| duckp
  webc -->|"A8 HTTP"| apic
  apic -->|"A9 DATABASE_URL"| pg
  apic -->|"A10 read-only"| duckc
  build -->|"A11"| duckc
  src -->|"A12 cli ingest"| lake
  src -->|"A13 dlt, patterns"| duckl
  store -->|"A14 cli extract-app"| lake
  lake -->|"A15 cli load"| duckl
  dbt -->|"A16"| duckl
  airflow -->|"A17"| lake
  airflow -->|"A18"| dbt
```

**How the parts fit together.** The browser loads a React bundle that was built with the
API's URL baked in. It then talks to a FastAPI service, which plans and checks a session
from the track catalogue and stores the session and its feedback in a transactional store.
The catalogue and the quality KPIs come from a DuckDB warehouse that the API opens read-only.
**In production that warehouse is built once, when the API image is built,** from versioned
files only. The container then runs uvicorn alone, so nothing re-extracts at runtime: the
sessions created on the live site stay in the container's SQLite file, never reach a mart, and
are lost at the next deploy ([docs/metrics.md](docs/metrics.md#where-the-data-comes-from-and-which-window-it-covers),
[ADR-003](docs/adr/adr-003-render-no-disk.md)). Locally, `docker compose up --build` runs the
same API image against Postgres, behind an nginx copy of the front. The compose API reads the
warehouse baked into its image, not the host's. The pipeline (ingest → lake → DuckDB → dbt,
orchestrated by Airflow) is a separate, opt-in path that writes the host's `lake/` and `data/`.
CI runs the test jobs on every push. On `main`, once they are green, it triggers Render's
deploy hooks and smoke-tests the live services; Render deploys nothing on its own.

Every box and arrow above, with its source (line numbers as of this commit; they drift as the
files change):

| Box or arrow | What | Source |
|---|---|---|
| CI test jobs | `build`, `frontend`, `integration`, `security` | `.github/workflows/ci.yml:27`, `:119`, `:157`, `:182` |
| deploy | runs on `main` only | `.github/workflows/ci.yml:198-200` |
| A1 | `deploy` waits for the four test jobs | `.github/workflows/ci.yml:199` |
| A2, A3 | `tools/deploy.py` calls the two deploy hooks, then smoke-tests health, generate, CORS and the web page; Render's auto-deploy is off | `.github/workflows/ci.yml:221-226`; `tools/deploy.py:115`, `:245-266`; `render.yaml:30`, `:48` |
| cyclebeat-web | Render static site built by Vite | `render.yaml:42-47` |
| cyclebeat-api | Render Docker service; the container runs uvicorn only | `render.yaml:23-26`; `Dockerfile:61` |
| planner + evaluator | called by the generate service | `api/services/session.py:68`, `:78` |
| A4 | the bundle calls the API URL fixed at build time; the API lets that origin in | `render.yaml:36-37`, `:55-56`; `frontend/src/api/client.ts:6` |
| A5, SQLite | no `DATABASE_URL` in production, so the store is SQLite | `render.yaml:31-37`; `api/repositories/database.py:153-167` |
| A6, A10 | the API opens the warehouse read-only; it falls back to read-write only if that open fails (a missing file), which the image's baked-in warehouse does not hit | `api/repositories/warehouse.py:38-42`; `api/repositories/track.py:27` |
| API image build, A7 | one `RUN` builds the warehouse from versioned files; the API reads it at `RUNTIME_DB_PATH` | `Dockerfile:40-45`; `render.yaml:32-33` |
| web (compose) | nginx serves the built bundle | `docker-compose.yml:86-92`; `frontend/Dockerfile:24-28` |
| api (compose), A11 | built from the same `Dockerfile` | `docker-compose.yml:60-61`, `:76` |
| A8 | the compose bundle points at the compose API | `docker-compose.yml:90`; `frontend/src/api/client.ts:6` |
| A9, postgres | `DATABASE_URL` set, so the store is Postgres | `docker-compose.yml:40-47`, `:69`; `api/repositories/database.py:106-107`, `:153-158` |
| DuckDB (compose) | the image's warehouse, not mounted over | `docker-compose.yml:58-59`, `:65` |
| Local pipeline | `make ingest`, `make dbt`; compose profile `pipeline` | `Makefile:81-82`, `:92-96`; `docker-compose.yml:106-138`, `:148-191` |
| sources | demo snapshot or live Deezer, optional CSV; patterns JSON | `cyclebeat/cli.py:48-67`; `ingest/ingest_pipeline.py:43` |
| app store | engine picked by `DATABASE_URL` | `cyclebeat/app_store.py:61`, `:64-68` |
| lake | Parquet partitions under `lake/` | `cyclebeat/lake.py:24`, `:84` |
| DuckDB (local) | `RUNTIME_DB_PATH`, default `data/cyclebeat_runtime.duckdb` | `db/runtime.py:21-23`; `dbt/profiles.yml:8` |
| A12 | `cli ingest` writes the lake | `cyclebeat/cli.py:69`; `Makefile:94` |
| A13 | dlt loads the patterns into DuckDB | `ingest/ingest_pipeline.py:51-56`; `Makefile:93` |
| A14 | `cli extract-app` copies sessions and feedback into the lake | `cyclebeat/cli.py:122`; `cyclebeat/app_store.py:157`; `Makefile:95` |
| A15 | `cli load` loads the lake into DuckDB | `cyclebeat/cli.py:106`; `cyclebeat/warehouse.py:122`; `Makefile:96` |
| A16 | dbt builds the marts in the same DuckDB | `dbt/profiles.yml:8`; `Makefile:82` |
| Airflow | three DAGs chained on lake assets | `dags/dag_ingest.py:36`; `dags/dag_resolve_bpm.py:34`; `dags/dag_build_warehouse.py:32` |
| A17 | `dag_ingest` and `dag_resolve_bpm` write the lake | `dags/dag_ingest.py:84`; `dags/dag_resolve_bpm.py:94` |
| A18 | `dag_build_warehouse`: extract-app, load, then dbt build | `dags/dag_build_warehouse.py:44-77` |

The BPM resolution (librosa on the Deezer preview, cross-validated with Deezer's `bpm`) is
described in [ADR-005](docs/adr/adr-005-deezer-preview-backbone.md) and
[ADR-010](docs/adr/adr-010-track-and-bpm-sources.md). Monitoring (Prometheus + Grafana,
`monitoring/`) is the opt-in compose profile `monitoring`. Every KPI the marts expose, with its
grain, formula and guarding tests: [docs/metrics.md](docs/metrics.md).

## Key design decisions

| Decision | Why | ADR |
|---|---|---|
| BPM from `librosa` on the Deezer preview, Deezer `bpm` field as cross-validation | Spotify audio features are closed to new apps; librosa returned a BPM on 82 % of 50 real previews, with a documented error bar ([spike report](docs/spikes/phase1-source-coverage.md)) | [ADR-005](docs/adr/adr-005-deezer-preview-backbone.md) |
| A confidence score on every BPM (`cross_validated` 0.9, `single_source` 0.6) | The planner must know how much to trust each track | [ADR-005](docs/adr/adr-005-deezer-preview-backbone.md) |
| Deterministic planner, no LLM in the core | Cadence and effort must be computed, not generated | [ADR-007](docs/adr/adr-007-session-construction-rules.md) |
| Evaluator validated by a **mutation check** | An evaluator tested on the planner's own output proves nothing | [ADR-007](docs/adr/adr-007-session-construction-rules.md) |
| `openapi.yaml` written by hand before the backend | The contract drives the code, and CI checks they never diverge | — |
| Postgres for app state (sessions, feedback), DuckDB for analytics | OLTP and OLAP have different jobs | [ADR-009](docs/adr/adr-009-postgres-transactional-duckdb-analytical.md) |

All decisions: [docs/adr/](docs/adr/README.md).

**Where sessions and feedback are stored.** Postgres when `DATABASE_URL` is set (the compose
stack sets it), SQLite at `data/cyclebeat_app.db` otherwise, so a clean clone runs with no
service. Choosing the engine from the URL is unit-tested, and the Postgres code path is exercised
in CI against a real database (a `postgres:16-alpine` service; the repository tests run on both
engines, and are skipped locally unless `TEST_DATABASE_URL` points at a server). Postgres is
the store under compose and in CI. The public demo sets no `DATABASE_URL` and has no persistent
disk ([ADR-003](docs/adr/adr-003-render-no-disk.md)): it keeps sessions in SQLite inside its
container, so a session created there survives neither a redeploy nor a restart of the service,
including the free tier's spin-down when idle.

## Quality gates

[![CI](https://github.com/elliepsc/cyclebeat/actions/workflows/ci.yml/badge.svg)](https://github.com/elliepsc/cyclebeat/actions/workflows/ci.yml)

Every check below runs in CI on every push. Counts are in each PR description, not here.

| Check | Command | What it covers |
|---|---|---|
| Lint, strict typing, dead links | `make lint` · `make typecheck` | ruff, strict mypy, relative Markdown links |
| Unit then integration, one command | `make test` | `make test-unit`, then `make test-integration`; stops at the first failing suite and names it; fails (never skips) without Docker; CI runs its two halves in separate jobs (`make test-unit`, `make test-integration`) |
| Unit tests | `make test-unit` | everything under `tests/` except `tests/integration/`, including the API contract suite |
| Evals | `make eval` | adversarial playlists and the planner **mutation check** |
| dbt models and data tests | `make dbt` | staging → intermediate → marts, and the data tests |
| API contract | `make contract` | `openapi.yaml` vs the schema FastAPI generates, plus schemathesis against the real app |
| Integration (end to end) | `make test-integration` | the compose stack (api, web, postgres) driven over HTTP — see [End-to-end tests](#end-to-end-tests) |
| Security scans | `make audit` | Semgrep (blocking on severity ERROR) and gitleaks over the whole git history (blocking on any finding), Docker images pinned by digest — see [Security & ops](#security--ops) |

## Run it locally

### The full system, one command (Docker)

Requires Docker with Compose v2 (on Windows: Docker Desktop with WSL integration, see
[CONTRIBUTING.md](CONTRIBUTING.md)). No `.env` to fill in, no key, no network at run time.

```bash
git clone https://github.com/elliepsc/cyclebeat.git && cd cyclebeat
docker compose up --build
```

| Service | URL | What it is |
|---|---|---|
| `web` | <http://localhost:4173> | the React app (nginx), built against the compose API |
| `api` | <http://localhost:8000> — docs at `/docs` | FastAPI, serving the demo warehouse baked into its image |
| `postgres` | not published (`docker compose exec postgres psql -U cyclebeat`) | sessions and feedback |

Each service has a healthcheck, and starts only once the one it depends on is healthy
(`postgres` → `api` → `web`); `docker compose ps` shows `(healthy)` on all three when ready.
Open <http://localhost:4173>, pick a level, a goal and a duration, and generate a session.
Stop with `Ctrl+C`, then `docker compose down -v` to drop the Postgres volume too.

- **Observed on the maintainer's machine** (WSL2, Docker 27.5, base images already pulled):
  building both images without cache took 70 s, and the three services were healthy about
  22 s after `up`. A first run also downloads the base images (Python, Node, nginx,
  Postgres), which depends on your connection.
- **Ports.** 8000 and 4173 by default. If one is taken, pin another and rebuild — the web
  bundle bakes the API URL in at build time, and the API's CORS list follows the same
  variables: `CYCLEBEAT_API_PORT=9000 CYCLEBEAT_WEB_PORT=5000 docker compose up --build`.
  `make compose-up` picks free ports for you and prints them.
- **Open the app at `localhost` or `127.0.0.1`**: both origins are allowed by CORS.
- **Values in `docker-compose.yml` are local defaults, not secrets** (the Postgres password
  opens a container with no published port). Production uses none of them.

**Deliberately outside the default stack.** The data pipeline (ingest → lake → DuckDB → dbt)
and its Airflow orchestrator are not needed to run the app: the API image builds the demo
warehouse itself, from versioned files only ([ADR-003](docs/adr/adr-003-render-no-disk.md)).
They also **write to your working copy's `data/` and `lake/`** (bind mounts), which the default
stack never does. They are opt-in compose profiles:

```bash
docker compose --profile pipeline up --build     # ingest + dbt, then Airflow on :8080
docker compose --profile monitoring up --build   # Prometheus on :9090, Grafana on :3000
```

### End-to-end tests

`tests/integration/` is a black-box suite: it only talks HTTP to a running compose stack, and
is kept out of `make test-unit`. One command builds the stack, waits until all three services
are healthy (bounded wait), runs the suite, prints the service logs on failure, and always
tears everything down, volumes included:

```bash
make setup              # once: installs pytest from uv.lock
make test-integration   # non-zero exit status if anything fails
```

- It runs as its own compose project, `cyclebeat-it`, so it neither collides with nor wipes a
  stack you already have running (it does need ports 8000 and 4173 free, or
  `make test-integration IT_API_PORT=… IT_WEB_PORT=…`).
- Covered: health; generate a demo session, replay it, find it in the list, rate it (and a
  404 on an unknown session); the two data-quality reads; the web bundle points at the compose
  API; CORS lets the web origin in and keeps a foreign one out; and a session survives a
  recreate of the API container, which only holds because it lives in Postgres.
- **A missing stack fails, it never skips.** The suite only accepts `localhost`, `127.0.0.1`
  or `::1` as a target and refuses any other URL before the first request, so it can never
  run against the public deployment.
- Observed from a fresh clone (images already built, so no compile): 13 tests passed, 35 s for
  the whole command, 8.8 s of it in pytest. CI runs the same command in the `integration`
  job, and the deployment waits for it; its first run, building both images from scratch,
  took 1 min 11 s ([run 38151120398](https://github.com/elliepsc/cyclebeat/actions/runs/38151120398)).

### Without Docker

Requires [uv](https://docs.astral.sh/uv/).

```bash
make setup      # installs the exact pinned environment (uv.lock)
make ingest     # loads the committed demo knowledge base (no network, no API key)
make dbt        # builds the warehouse
make api        # API on http://localhost:8000 — docs at /docs
```

Frontend (React + Vite, in `frontend/`). It needs the Node version pinned in
`frontend/.nvmrc`, and `make api` running in another terminal.

```bash
make front        # dev server on http://localhost:5173 (installs from the lockfile first)
make front-test   # vitest
make front-gen    # regenerate the TypeScript client from openapi.yaml
```

- The API URL is `VITE_API_URL`, fixed at build time (default `http://localhost:8000`).
- The API only answers browsers whose origin is listed in `CORS_ALLOW_ORIGINS`
  (comma-separated, never `*`; default `http://localhost:5173`).
- `frontend/src/api/schema.d.ts` is generated from `openapi.yaml`, never edited by hand: CI
  regenerates it and fails if the committed file differs.

Docker variants: `make compose-up` (the full system, free ports picked for you),
`make compose-pipeline` (plus ingest, dbt and Airflow), `make compose-monitoring`.
WSL setup and the branch/PR workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/v1/sessions/generate` | Plan a session from the catalogue |
| `GET` | `/v1/sessions` · `/v1/sessions/{id}` | List and replay sessions |
| `POST` | `/v1/sessions/{id}/feedback` | Rate a session |
| `GET` | `/v1/quality/coverage` · `/v1/quality/summary` | BPM coverage and data-quality KPIs from the marts |

## Roadmap

| Phase | Content | Status |
|---|---|---|
| 0–1 | Purge of the v1 prototype, source spike | ✅ |
| 2 | Data-engineering core: resolver, lake, DuckDB, dbt, Airflow | ✅ |
| 3 | Planner + evaluator, mutation check | ✅ |
| 4 | Contract-first API | ✅ |
| 5 | Frontend (React, client generated from `openapi.yaml`) | ✅ |
| — | Public deployment (API) | ✅ |
| 7 | Agent extension pack (MCP server, hook, subagents, skill, plugin) | ✅ |
| 10 | Security, audit and DevOps (criterion 13) | ✅ (PR #42) |
| 6 | Bounded warehouse copilot (LLM layer) | planned |

Detailed roadmap: [docs/ROADMAP.md](docs/ROADMAP.md).

## Security & ops

| What | Where |
|---|---|
| Index of the security artifacts | [security/README.md](security/README.md) |
| PR audits (raw reviewer output and triage) | [security/pr-audits/](security/pr-audits/pr-38.md) |
| Scan findings (Semgrep, gitleaks, pip-audit, npm audit), triaged | [security/scans/2026-10-20.md](security/scans/2026-10-20.md) |
| Agent and extension security: threat model, bypasses fixed, what remains | [security/agent-security.md](security/agent-security.md) |
| AI tool and data policy | [security/ai-policy.md](security/ai-policy.md) |
| Operational diagnosis: Postgres down while the API reports healthy | [ops/](ops/README.md) |
| What a coding agent may do here, and the guardrails | [docs/permissions.md](docs/permissions.md) |

## How it was built

What the system must do, requirement by requirement, with the PRs and tests that prove each one:
[product-spec.md](product-spec.md). Remaining work: the [GitHub issues](https://github.com/elliepsc/cyclebeat/issues),
one per block, each closed by the pull request that delivers it.

Developed with AI coding agents under explicit rules: project instructions (`AGENTS.md`,
`CLAUDE.md`), dedicated subagents (`.claude/agents/`: contract guardian, dbt reviewer,
security auditor), one phase = one branch = one pull request, and CI as the definition of done.
The decisions taken — including the ones taken *against* an agent's proposal — are logged in
[docs/ai-workflow.md](docs/ai-workflow.md).

---

*The v1 prototype (LLM Zoomcamp capstone: Spotify, Qdrant, LangGraph) is preserved on the
`archive/v1-llm-zoomcamp` branch.*

**License:** MIT. See [LICENSE](LICENSE).
