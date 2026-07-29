# ADR-001 — V3 repositioning: DE-first, AI Dev Tools target

- **Status**: Accepted
- **Date**: 2026-07 (Phase 0)
- **Owner**: Ellie

## Context

The repo started as a V1 LLM-Zoomcamp capstone: Spotify Audio Analysis, Qdrant, LangGraph, hybrid search,
Streamlit. Audits (V2, then V3) found: Spotify Audio Analysis is dead for new apps; the vector DB is oversized
for a 30-50 chunk KB; a 3-node LangGraph graph doesn't justify a graph framework; and the LLM-Zoomcamp angle is
already covered by the sibling project *homebarista*.

## Decision

Reposition CycleBeat as a **DE-first, end-to-end data product** targeting the **AI Dev Tools Zoomcamp** grid
(not LLM Zoomcamp): multi-source pipeline (Deezer/Jamendo/CSV → dlt → Parquet lake → DuckDB → dbt), contract-first
FastAPI + React, a bounded warehouse copilot, MCP/subagents/hooks, security/CI-CD — all built with a documented
AI-engineering workflow. The V2 DE core is preserved; the V1 LLM-Zoomcamp lineage is purged.

**Purged** (Phase 0): Spotify client + `.spotify_cache`, Qdrant + hybrid search + retrieval eval, LangGraph
orchestrator (replaced by a bounded tool-use agent), Streamlit app (replaced by React). **Kept**: FastAPI skeleton,
DuckDB runtime, dbt, dlt ingest, docker-compose/Dockerfile/render.yaml, the 40 cycling patterns (KB seed).

## Consequences

- The V1 state is preserved on branch `archive/v1-llm-zoomcamp` before purge.
- Deezer/Jamendo/CSV replace Spotify (validated by the phase-1 source spike).
- Two agentic layers are documented separately (product copilot vs process workflow) to avoid reviewer confusion.
- Full rationale: `docs-notes/CYCLEBEAT_PLAN_V3.md` §0, and the V3.1 hardening delta (D1-D8).

## Execution notes — purge run on 2026-07-28

The runbook (plan appendix E.1 #3) was written against the 2026-07-09 audit. Four points diverged
from the repo as it actually stood; they are recorded here rather than silently resolved.

1. **The purged UI was Dash, not Streamlit.** `app/` contained `coaching.py` + `dashboard.py`
   (Plotly Dash, ~900 lines), decoupled from the backend — it called the API over HTTP and imported
   nothing purged. **Owner decision: delete now.** Its main feature (the *generate* button) died with
   the orchestrator, so keeping it would have shipped a visibly broken UI; React arrives in phase 5
   and the code stays reachable on `archive/v1-llm-zoomcamp`. The Streamlit label in this ADR and in
   the runbook refers to that directory.
2. **`POST /session/generate` now returns 501.** It imported the deleted orchestrator. Serving the
   demo session instead would have simulated a result, which the execution rules forbid, so the
   endpoint fails explicitly until the V3 resolver (phase 2) and the contract-first rewrite (phase 4).
3. **Kept beyond the ADR's original list**: the Prometheus/Grafana monitoring stack. It is not a v1
   LLM-Zoomcamp brick, it scrapes only the API, and it feeds criterion 13 later.
4. **Two dependency changes are not simple removals**: `duckdb` is now declared explicitly
   (`db/runtime.py` imports it directly, previously satisfied only transitively), and `setuptools`
   was **added** — dlt 0.5.4 imports `pkg_resources` at import time and used to receive setuptools
   from torch, so removing the embeddings stack broke `import dlt`. Both are dropped or revisited
   when dlt is upgraded in phase 2.

Deployment stayed out of scope (phase 9), but `Dockerfile` and `render.yaml` still pointed at
`app/streamlit_app.py` — a file that never existed in this repo — and at Spotify/Qdrant env vars.
Those dead references were removed so the image and the blueprint are coherent with the purged repo;
no new deployment work was done.
