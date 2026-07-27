# ADR-003 — Render free tier has no persistent disk (D3)

- **Status**: Accepted
- **Date**: 2026-07 (Phase 0, hardening D3)
- **Owner**: Ellie

## Context

The deployment target is Render free tier (zero cost, E.8). Persistent disks on Render are **paid** — a
contradiction with the zero-cost constraint. DuckDB is a single file on disk, so "just persist the warehouse
file" is not free.

## Decision

**Bake a demo DuckDB into the Docker image**; accept and document that it **resets on every deploy**. No Render
persistent disk (paid → rejected by E.8). The app serves the demo/read path from the image; the pipeline that
writes the warehouse runs locally / in CI, not on the free-tier web service.

## Options considered

- A — Render persistent disk: **rejected**, paid.
- B — **Demo DB baked into the image** (reset per deploy): **chosen**, zero cost, honest and documented.
- C — MotherDuck free tier as the served warehouse: kept as a **non-required** option (documented), in case a
  persistent cloud warehouse is later wanted.

## Consequences

- README documents the per-deploy reset explicitly (no silent data loss surprise).
- Combined with D4 (two DuckDB files, single writer) and D7 (Render spin-down cold start, keep-alive SSE).
- If persistence becomes required, switch the served target to MotherDuck free tier (option C) — no code rewrite
  (dbt multi-adapter, see bonus B4).
