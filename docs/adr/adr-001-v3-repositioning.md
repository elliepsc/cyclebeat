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
