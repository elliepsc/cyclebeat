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

## Implementation note — 2026-10-01 (A4)

The decision stands; two details differ from what the ADR implied.

- **Built at image-build time, from versioned files only.** The `Dockerfile` runs the offline
  pipeline (`ingest.ingest_pipeline`, `cyclebeat.cli ingest` / `extract-app` / `load`, then
  `dbt build`) after `COPY . .`. The input is `data/cycling_patterns.json` and the committed
  spike snapshot (`data/spike/raw_output.json`), so the image needs no network and no key.
  `dbt build` runs the 48 tests: a broken mart fails the build, not the deploy. Because
  `.dockerignore` does not cover every local artifact (a root `*.duckdb`, `data/*.db`), the same
  `RUN` first deletes them rather than trusting the build context.
- **No ingestion at start.** `render.yaml` no longer has a `startCommand` that ran
  `ingest_pipeline` on each boot; the `CMD` (uvicorn, bound to Render's `$PORT`) starts at once.
- **Compose is unchanged and shadows the baked database.** `docker-compose.yml` bind-mounts
  `./data` over `/app/data`, so under compose the API reads the host's database, not the one in
  the image. The baked database is what Render serves.
