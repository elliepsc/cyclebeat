# 🚴 CycleBeat — music-to-workout data product

CycleBeat turns a playlist into a structured indoor-cycling session: every track gets a tempo,
a cadence, a resistance and an effort phase, and the whole session is checked for safety and
coherence before it is served.

Under the hood it is a **data-engineering project first**: a multi-source ingestion pipeline,
a Parquet lake, a DuckDB warehouse modelled with dbt, a deterministic planning engine with its
own evaluator, and a contract-first API.

> **Status (October 2026): work in progress — AI Dev Tools Zoomcamp 2026 project.**
> The data pipeline, the engine and the API are done and tested, and the API is deployed. The
> frontend is the next phase (see [Roadmap](#roadmap)).
>
> **Live API:** <https://cyclebeat-api.onrender.com/> (`GET /health`, `POST /v1/sessions/generate`
> with the demo source). It runs on Render's free tier on a demo database baked into the image,
> which resets on every deploy ([ADR-003](docs/adr/adr-003-render-no-disk.md)); the free tier
> also spins down when idle, so the first request after a pause can be slow.

---

## Why this project

Indoor-cycling classes tie riders to a fixed playlist and a fixed instructor. CycleBeat starts from
the rider's own music. The hard part is not the UI: it is getting a **reliable BPM** for mainstream
tracks now that the Spotify audio-analysis endpoints are closed to new apps, and turning those BPMs
into a session that is **coherent and safe**.

## Architecture

```
Deezer API (metadata + public 30 s preview)   CSV (manual BPM)
              │                                     │
              ▼                                     ▼
   librosa BPM on preview ──► resolver: cross-validation + confidence score
                                     │
                                     ▼
                  Parquet lake ──► DuckDB ──► dbt (staging → intermediate → marts)
                                     │
                                     ▼
                planner (deterministic rules) ──► evaluator (safety & coherence)
                                     │
                                     ▼
                     FastAPI, contract-first (openapi.yaml)
```

Orchestration: three chained Airflow DAGs (`dags/`). Monitoring: Prometheus + Grafana (`monitoring/`).

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
service. Choosing the engine from the URL is unit-tested, but the Postgres code path is **not
yet exercised in CI against a real database** (CI has no Postgres service). The public demo
sets no `DATABASE_URL` and has no persistent disk ([ADR-003](docs/adr/adr-003-render-no-disk.md)),
so sessions created there are ephemeral.

## Quality gates

[![CI](https://github.com/elliepsc/cyclebeat/actions/workflows/ci.yml/badge.svg)](https://github.com/elliepsc/cyclebeat/actions/workflows/ci.yml)

Every check below runs in CI on every push. Counts are in each PR description, not here.

| Check | Command | What it covers |
|---|---|---|
| Lint, strict typing, dead links | `make lint` · `make typecheck` | ruff, strict mypy, relative Markdown links |
| Unit tests | `make test-unit` | everything under `tests/`, including the API contract suite |
| Evals | `make eval` | adversarial playlists and the planner **mutation check** |
| dbt models and data tests | `make dbt` | staging → intermediate → marts, and the data tests |
| API contract | `make contract` | `openapi.yaml` vs the schema FastAPI generates, plus schemathesis against the real app |

## Run it locally

Requires [uv](https://docs.astral.sh/uv/). Docker is only needed for the full stack below.

```bash
make setup      # installs the exact pinned environment (uv.lock)
make ingest     # loads the committed demo knowledge base (no network, no API key)
make dbt        # builds the warehouse
make api        # API on http://localhost:8000 — docs at /docs
```

Full stack with Airflow and monitoring: `make compose-pipeline`.
Windows/WSL notes and the branch/PR workflow: [CONTRIBUTING.md](CONTRIBUTING.md).

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
| 5 | Frontend (React, client generated from `openapi.yaml`) | 🔜 next |
| — | Public deployment (API) | ✅ |
| 6+ | Bounded warehouse copilot, agent extension pack, security audit | planned |

Detailed roadmap: [docs-notes/CYCLEBEAT_ROADMAP.md](docs-notes/CYCLEBEAT_ROADMAP.md).

## How it was built

Developed with AI coding agents under explicit rules: project instructions (`AGENTS.md`,
`CLAUDE.md`), dedicated subagents (`.claude/agents/`: contract guardian, dbt reviewer,
security auditor), one phase = one branch = one pull request, and CI as the definition of done.
The decisions taken — including the ones taken *against* an agent's proposal — are logged in
[docs/ai-workflow.md](docs/ai-workflow.md).

---

*The v1 prototype (LLM Zoomcamp capstone: Spotify, Qdrant, LangGraph) is preserved on the
`archive/v1-llm-zoomcamp` branch.*

**License:** MIT. See [LICENSE](LICENSE).
