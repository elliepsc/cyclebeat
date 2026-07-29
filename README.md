> ⚠️ **STATUS — this README describes the v1 (LLM-Zoomcamp) product and is superseded.**
> The project is being repositioned to a DE-first data product targeting the AI Dev Tools grid
> (see `docs/adr/adr-001-v3-repositioning.md` and `docs-notes/CYCLEBEAT_PLAN_V3.md`). Known
> discrepancies with the current/target code: **Streamlit → Dash** (`app/coaching.py`,
> `app/dashboard.py`; `app/streamlit_app.py` does **not** exist), **Spotify → Deezer/Jamendo/CSV**
> (Spotify audio endpoints are dead for new apps), **Qdrant is being purged**, **Prefect → Airflow**
> (ADR-002). A full rewrite is a Phase-0 deliverable. Do not follow the run instructions below as-is.
> Session audit & decisions: `docs-notes/DECISIONS_SESSION_2026-07.md`.

# 🚴 CycleBeat — Agentic Music-to-Coaching Session Designer

[![Python](https://img.shields.io/badge/python-3.11-blue)](Dockerfile)
[![Docker](https://img.shields.io/badge/docker-compose-blue)](docker-compose.yml)
[![License](https://img.shields.io/badge/license-course_project-lightgrey)](#)

> Turn any Spotify playlist into a structured indoor cycling session with synchronized coaching cues, retrieval-powered training patterns, and agentic planning.

**Try it in 2 minutes (no Spotify needed):**

```bash
cp .env.example .env  # fill in OPENAI_API_KEY + OPENAI_BASE_URL for Groq/OpenAI-compatible LLM calls
docker compose up --build
# open http://localhost:8501 and select "Demo (no Spotify needed)"
```

---

## Problem Statement

Indoor cycling classes are engaging, but they lock riders into a fixed playlist, a fixed instructor style, and a fixed workout structure. At the same time, simply matching BPM to effort is too simplistic — a good cycling session needs coherent structure, smooth transitions, realistic effort/recovery balance, and adaptation to the rider's goal.

**CycleBeat** transforms a Spotify playlist into a structured coaching session synchronized to the musical structure of each track, grounded in a knowledge base of 40 cycling patterns, and delivered as live timestamped cues.

**Core promise:** your music, your goal, your ride — but with a session that still feels structured, safe, and coach-like.

**What I built:** the playlist-to-session agent graph, the cycling pattern knowledge base, the hybrid retrieval pipeline, the cue generation prompts, the Streamlit coaching UI, the FastAPI endpoints, Docker Compose setup, and the evaluation scripts.

---

## How It Works

```
Spotify Playlist URL
        ↓
Spotify Audio Analysis (sections, tempo, loudness, energy)
        ↓
build_raw_query()          ← rules-based, no LLM
        ↓
rewrite_query()  [LLM #1]  ← rewrites the raw query into natural coaching language
        ↓
hybrid_search()            ← vector search + keyword search fused (no LLM)
        ↓
rerank()                   ← BPM + loudness range filter (no LLM)
        ↓
generate_cue()   [LLM #2]  ← generates the coaching instruction from the retrieved pattern
        ↓
Timestamped coaching session
        ↓
Live Streamlit UI — synchronized cues, progress bar, 10s pre-change alert
        ↓
User feedback + monitoring dashboard
```

---

## App Preview

Screenshots are expected in `docs/screenshots/`:

| View | File | What it should show |
|---|---|---|
| Live coaching UI | `docs/screenshots/live-coaching-ui.png` | Active cue, resistance target, progress bar, and next-phase alert |
| Monitoring dashboard | `docs/screenshots/monitoring-dashboard.png` | Feedback KPIs, charts, and feedback log |

Video preview target: `docs/cyclebeat-demo.mp4` or a GitHub-attached README video showing a 30–60 second Streamlit demo.

---

## Architecture

### What uses an LLM, what doesn't

**Rules-based / local computation — no API calls:**

| Component | What it does |
|---|---|
| `build_raw_query()` | Converts BPM + loudness into a raw text query (`"intense tempo fast 171 BPM"`) |
| Sentence-transformers | Encodes text into dense vectors — runs fully locally |
| `vector_search()` | Cosine similarity search in Qdrant |
| `text_search()` | Keyword overlap scoring across pattern labels, instructions, tags |
| `hybrid_search()` | Reciprocal rank fusion of vector + keyword scores (α=0.7) |
| `rerank()` | Filters candidates by BPM range and loudness range match |
| Session timer | Elapsed time tracking and cue synchronization in Streamlit |

**LLM calls (Groq API):**

| Component | When it runs | What it does |
|---|---|---|
| `rewrite_query()` | Before retrieval | Reformulates the raw audio-feature description into natural coaching language |
| `generate_cue()` | After retrieval | Generates a 1–2 sentence coaching instruction grounded in the retrieved pattern |
| LLM-as-Judge | Evaluation only | Scores prompt variants on clarity, motivation, precision, naturalness |

### How RAG fits in

Retrieval and generation work together in two steps:

1. **Retrieval:** `hybrid_search()` + `rerank()` selects the most relevant cycling pattern from the knowledge base
2. **Generation:** the retrieved pattern (phase, resistance, cadence, effort, coach tone) is injected into the `generate_cue()` prompt — the LLM produces a grounded instruction, not a hallucinated one

`rewrite_query()` extends RAG upstream: it reformulates the query *before* retrieval, improving recall for natural-language coaching concepts that raw audio features don't express.

**Without RAG:** the LLM receives raw BPM/loudness numbers → generic output.
**With RAG:** the LLM receives a structured coaching pattern → precise, contextualized instruction.

---

## Knowledge Base

40 cycling patterns stored in `data/cycling_patterns.json`, organized in two categories:

**Local patterns (29):** phase-specific coaching moments — warm-up (3 variants), steady (3), build (2), sprint (6 variants: 15s / 30s / 45s / 60s + surge + attack), climb (4: seated moderate/hard, standing moderate/max), interval ON/OFF (3), recovery (4), cool-down (2), cadence drills (2).

**Transition patterns (11):** dedicated patterns for the moments *between* effort blocks — prepare sprint, release after sprint, prepare climb, release after climb, standing↔seated switches, warm-up to main set, main set to cool-down, recovery to interval, interval to recovery, build to sprint.

Each pattern includes: `bpm_range`, `loudness_range`, `energy_range`, `cadence_target`, `resistance`, `effort`, `duration_min/max_s`, `coach_tone`, `tags`.

---

## Agentic Architecture (LangGraph)

Three nodes in a compiled state graph:

```
START → playlist_agent → coach_planner → save_session → END
              ↓ (error)                ↓ (error)
             END                      END
```

- **playlist_agent:** fetches Spotify tracks and audio analysis, computes session timestamps
- **coach_planner:** runs the full RAG pipeline per section — query rewrite → retrieval → rerank → generation
- **save_session:** persists the generated session JSON to disk

Conditional routing on error at each step — the graph short-circuits to END on any agent failure rather than propagating a broken state.

---

## Evaluation

### Retrieval evaluation (`evaluation/retrieval_eval.py`)

Three approaches compared on a 10-query ground-truth test set.

| Approach | Hit@1 | Hit@3 | MRR |
|---|---:|---:|---:|
| Vector only | 0.80 | 0.90 | 0.850 |
| Keyword only | 0.70 | 1.00 | 0.833 |
| **Hybrid** | **0.80** | **0.90** | **0.850** |

Hybrid search is used in production because it keeps the semantic ranking quality of vector search while still letting keyword matches participate in retrieval before the BPM/loudness reranker.

> **Why vector and hybrid score identically here:** on a 40-pattern knowledge base with well-separated phase labels, dense similarity alone reaches near-ceiling recall. Hybrid is kept because keyword overlap adds resilience on edge cases (exact tag matches, very short queries) not captured in the dense space — the gap widens as the knowledge base grows.

### LLM evaluation (`evaluation/llm_eval.py`)

Two prompt styles compared via LLM-as-Judge using the configured OpenAI-compatible model on 5 test cases:

- **Prompt A:** structured JSON output with resistance target + instruction
- **Prompt B:** natural instructor-style coaching cue

Scored on clarity, motivation, precision, and naturalness. Winner is wired into the production pipeline.

### Session-level evaluation (`evaluation/session_eval.py`)

End-to-end evaluation of the full generated session on three metrics:

- **Effort/recovery ratio** — ideal range 35–65% effort time
- **Phase diversity** — at least 4 distinct phases per session
- **Transition coherence** — less than 15% incoherent transitions (e.g. sprint → climb without recovery)

Global score 0–100, compared against the rules-only baseline on the bundled demo session:

| System | Effort Ratio | Unique Phases | Bad Transitions | Global Score |
|---|---:|---:|---:|---:|
| Rules-only baseline | 0.0% | 1 | 0/26 | 37/100 |
| **CycleBeat RAG + LLM session** | **40.0%** | **8** | **2/26** | **100/100** |

### Baseline (`evaluation/baseline_rules_only.py`)

A rules-only system (no RAG, no LLM) used as the lower bound:

```
loudness > -6  AND tempo > 140  → sprint
loudness > -6  AND tempo <= 140 → climb
loudness > -10 AND tempo > 120  → steady
loudness <= -14                 → recovery
default                         → steady
```

The baseline makes the improvement from RAG + LLM measurable rather than claimed.

---

## Evaluation Criteria Coverage

| Criterion | Where |
|---|---|
| Problem description | [Problem Statement](#problem-statement) |
| RAG flow | [How It Works](#how-it-works) and [How RAG fits in](#how-rag-fits-in) |
| Retrieval evaluation | [Evaluation → Retrieval](#retrieval-evaluation-evaluationretrieval_evalpy) |
| LLM evaluation | [Evaluation → LLM](#llm-evaluation-evaluationllm_evalpy) |
| Interface | Streamlit UI in `app/streamlit_app.py` + FastAPI in `api/main.py` |
| Ingestion pipeline | `ingest/ingest_pipeline.py` using dlt staging + Qdrant loading |
| Monitoring | [App Preview](#app-preview) and Streamlit monitoring mode |
| Containerization | `docker-compose.yml` + `Dockerfile` |
| Reproducibility | [Reproducibility](#reproducibility) |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Hybrid retrieval over pure vector search | Vector search handles semantic coaching language; keyword search preserves exact phase/tag matches before reranking. |
| Groq/OpenAI-compatible client | Keeps inference fast and low-friction while allowing the same code path to swap to any OpenAI-compatible endpoint. |
| Demo mode first | Evaluators can review the UI and generated session without Spotify credentials. |

---

## Tech Stack

| Layer | Tool |
|---|---|
| LLM | Groq (`llama-3.3-70b-versatile`) via OpenAI-compatible client |
| Agentic orchestration | LangGraph 0.2.x |
| Vector database | Qdrant |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`, local) |
| Music analysis | Spotify Audio Analysis API (spotipy) |
| Ingestion pipeline | dlt + Python script |
| Interface | Streamlit |
| Monitoring | Streamlit dashboard (5 charts + feedback log) |
| Containerization | Docker + docker-compose |

---

## Project Structure

```
cyclebeat/
├── agents/
│   ├── coach_planner.py         # RAG pipeline: query rewrite → hybrid retrieval → rerank → LLM generation
│   ├── playlist_agent.py        # Spotify fetch + audio analysis ingestion
│   └── orchestrator.py          # LangGraph graph: playlist → coach → save
├── api/
│   └── main.py                  # FastAPI REST API — session generation + feedback endpoints
├── app/
│   └── streamlit_app.py         # Live coaching UI + monitoring dashboard
├── data/
│   ├── cycling_patterns.json    # 40-pattern knowledge base
│   ├── demo_session.json        # Pre-generated session (no Spotify needed)
│   └── feedback.json            # User feedback log (auto-created at runtime)
├── evaluation/
│   ├── baseline_rules_only.py   # Rules-only baseline generator
│   ├── retrieval_eval.py        # Vector vs keyword vs hybrid — Hit@1, Hit@3, MRR
│   ├── llm_eval.py              # Prompt A vs B via LLM-as-Judge
│   └── session_eval.py          # Session-level metrics (effort ratio, diversity, coherence)
├── ingest/
│   └── ingest_pipeline.py       # dlt staging + Qdrant vector loading
├── scripts/
│   └── spotify_auth.py          # One-time local Spotify token generation
├── docker-compose.yml
├── Dockerfile
├── render.yaml                  # One-click Render.com cloud deployment
├── pyproject.toml               # Dependencies and tooling config (uv)
├── uv.lock                      # Fully pinned, reproducible resolution
└── .env.example
```

---

## REST API

The FastAPI backend runs alongside Streamlit and exposes a clean REST interface.
When running with Docker Compose, the API is available at `http://localhost:8000`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/session/demo` | Pre-generated demo session (JSON) |
| `GET` | `/session/generated` | Last session generated from Spotify |
| `POST` | `/session/generate` | Generate a session from a Spotify playlist URL |
| `POST` | `/feedback` | Submit a session rating + note |
| `GET` | `/feedback` | All collected feedback entries |
| `GET` | `/feedback/stats` | Aggregated satisfaction stats |

Interactive docs (Swagger UI): `http://localhost:8000/docs`

**Example — generate a session:**
```bash
curl -X POST http://localhost:8000/session/generate \
  -H "Content-Type: application/json" \
  -d '{"playlist_url": "https://open.spotify.com/playlist/...", "use_llm": true, "use_hybrid": true}'
```

---

## Cloud Deployment

CycleBeat is deployable on any Docker-compatible cloud platform.
The recommended stack for cloud is **Qdrant Cloud** (managed vector DB) + **Render.com** (app hosting).

### Option A — Render.com (one-click, free tier)

1. Create a free Qdrant Cloud cluster at [cloud.qdrant.io](https://cloud.qdrant.io) — copy the cluster URL and API key.

2. Fork this repo, then go to [Render.com](https://render.com) → **New → Blueprint** and connect your fork.
   Render detects `render.yaml` automatically and creates both services (`cyclebeat-api` and `cyclebeat-app`).

3. Set these environment variables in the Render dashboard:

```env
OPENAI_API_KEY=your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
MODEL_NAME=llama-3.3-70b-versatile
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
```

4. Render builds from the Dockerfile, runs the ingestion pipeline on startup, then launches both the API and the Streamlit app.

### Option B — Any Docker host (AWS ECS, GCP Cloud Run, Railway…)

```bash
# Build and push the image
docker build -t cyclebeat .
docker tag cyclebeat your-registry/cyclebeat:latest
docker push your-registry/cyclebeat:latest
```

Set `QDRANT_URL` + `QDRANT_API_KEY` in your host's environment variables (replaces the local Qdrant container).

---

## Development environment

> Unlike the rest of this README, this section describes the **current V3 toolchain**
> and is expected to survive the Phase-0 rewrite. It exists because the definition of
> done — `make lint && make test-unit` — is not runnable out of the box on this setup.

The repo sits on a Windows path and is used from two shells: Windows (PowerShell) and
WSL at `/mnt/c/...`. **They cannot share the same virtual environment.** Windows `uv`
creates `.venv/` with a `Scripts/` layout; Linux `uv` expects `bin/`, considers the
environment foreign, and tries to recreate it — which fails on the `drvfs` mount with
`failed to remove directory .venv/Scripts: Input/output error (os error 5)`.

Each OS therefore gets its own environment. **Do not delete `.venv/`** to "fix" the
error: it is the Windows environment and it is working. `.venv/` is gitignored, so none
of this affects the repository.

### WSL — recommended

`make` is already available; only `uv`'s environment path needs redirecting, to a
location on the Linux filesystem (also much faster than `/mnt/c`).

**One-time setup.** Append the helper to `~/.bashrc`:

```bash
cat >> ~/.bashrc <<'EOF'

cyclebeat() {
  cd "/mnt/c/Users/Ellie Pro/Documents/Projets Data/projets_github/cyclebeat" || return
  export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/cyclebeat"
}
EOF
```

Then reload it once: `source ~/.bashrc`.

**Every new terminal.** The function is defined in every shell, but the `export` it
performs only lives in the shell that ran it — so it has to be *called*, not merely
defined. First command in any new terminal:

```bash
cyclebeat
```

It moves you to the repo and exports `UV_PROJECT_ENVIRONMENT`. Only then:

```bash
make lint && make test-unit
```

Skipping `cyclebeat` is the single most common failure: `uv` falls back to the Windows
`.venv/` and raises the `os error 5` above. The first run after setup builds the Linux
environment (`uv` provisions CPython 3.11 itself); later runs reuse it.

Why a function rather than a plain `export` in `~/.bashrc`: `UV_PROJECT_ENVIRONMENT` is
not scoped to a project, so exporting it globally would make *every* uv project on the
machine share this one environment.

### Windows PowerShell

Two prerequisites, both missing on a fresh setup:

```powershell
winget install --id ezwinports.make
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:USERPROFILE\.local\bin", "User")
```

The first installs `make` (`ezwinports` 4.4.1 — prefer it over `GnuWin32.Make`, still on
3.81). The second puts `uv` on `PATH`: the installer drops it in
`%USERPROFILE%\.local\bin`, which is not on `PATH` by default, so every Makefile target
would otherwise fail on `uv: command not found`. **Reopen the terminal**, then run
`make lint && make test-unit` — no per-session step is needed on this side.

---

## Setup & Run

### Option 1 — Docker (recommended)

```bash
# 1. Copy and fill in your credentials
cp .env.example .env

# 2. (Spotify only) Generate OAuth token once, locally
uv run python scripts/spotify_auth.py

# 3. Start everything
docker compose up --build
```

Open http://localhost:8501 (Streamlit UI) and http://localhost:8000/docs (API)

### Option 2 — Local Python

```bash
# 1. Install uv (once) — https://docs.astral.sh/uv/getting-started/installation/
#    macOS / Linux : curl -LsSf https://astral.sh/uv/install.sh | sh
#    Windows       : powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Create the environment and install dependencies
#    uv provisions Python 3.11 itself and installs exactly what uv.lock pins.
make setup                         # equivalent to: uv sync

# 3. Copy and fill in your credentials
cp .env.example .env

# 4. Start Qdrant (Docker required for the vector DB only)
docker run -p 6333:6333 qdrant/qdrant

# 5. Ingest the knowledge base
make ingest

# 6. Run the app
uv run streamlit run app/streamlit_app.py
```

There is no virtualenv to activate: `uv run <cmd>` executes inside the project
environment, and every `make` target already wraps its command in `uv run`.

### Demo mode (no Spotify account needed)

```bash
uv run streamlit run app/streamlit_app.py
# → select "Demo (no Spotify needed)" in the sidebar
```

The demo loads `data/demo_session.json` — a pre-generated session that works fully out of the box.

---

## Environment Variables

```env
# LLM — Groq or any OpenAI-compatible endpoint
OPENAI_API_KEY=your_groq_key
OPENAI_BASE_URL=https://api.groq.com/openai/v1
MODEL_NAME=llama-3.3-70b-versatile

# Spotify — optional, demo mode works without
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback

# Qdrant — local Docker
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Qdrant Cloud (replaces local when set)
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
```

---

## Reproducibility

- Dependencies are declared in `pyproject.toml` and fully pinned in `uv.lock` (committed); `uv sync` reproduces the exact environment, and `uv` also provisions the Python version from `.python-version`
- `data/demo_session.json` is a complete pre-generated session — no Spotify credentials required to review the app
- `data/cycling_patterns.json` is the full knowledge base — no external download needed
- Docker Compose starts all services in the correct order with health checks

---

## What's Next

See [`FUTURE_WORK.md`](FUTURE_WORK.md) for the full architecture evolution plan.

Key directions:
- **Interface** — React web client + React Native mobile app consuming the FastAPI backend (Streamlit kept for the monitoring dashboard only)
- **Ingestion** — dlt → Prefect for scheduled weekly pattern updates; migration path to Airflow documented
- **Monitoring** — Prometheus metrics on FastAPI + Grafana dashboards replacing the Streamlit infra charts
- **Agents** — Safety Critic node in LangGraph, Music Interpreter node, Rider Profile injection
- **Data** — PostgreSQL replacing flat JSON files for multi-user sessions and feedback

---

*Built as a capstone project for [LLM Zoomcamp 2026](https://github.com/DataTalksClub/llm-zoomcamp) by Ellie Pascaud.*
