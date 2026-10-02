# Architecture Decision Records — CycleBeat

Log of architecture decisions. One structural decision = one ADR, numbered, immutable once `Accepted`
(you don't rewrite it: you create a new one that supersedes it).

## Convention

Lightweight format (MADR-inspired): **Context → Options → Decision → Consequences**. Statuses:

- `Proposed` — written, not yet decided by the owner.
- `Gated` — proposed **and blocked**: do not implement until its opening condition is met.
- `Accepted` — decision made, implementation authorized.
- `Superseded by adr-XXX` — replaced.

What may change in an `Accepted` ADR: a link path, the status line when a later ADR replaces it (with
the link), and a dated `Note (YYYY-MM-DD):` line at the end. Never its context, options or decision.

The status column below summarizes each ADR's own status line, which is the source of truth.

## Index

### Core

| ADR | Topic | Status | Date |
|---|---|---|---|
| [adr-001-v3-repositioning](adr-001-v3-repositioning.md) | Why V3 (purge Spotify/Qdrant, DE-first, AI Dev Tools target) | Accepted | 2026-07 |
| [adr-002-airflow](adr-002-airflow.md) | Airflow vs Prefect | Accepted | 2026-07 |
| [adr-003-render-no-disk](adr-003-render-no-disk.md) | No Render disk: demo DB baked into the image (D3) | Accepted | 2026-07 |
| [adr-004-bpm-resolution-floor](adr-004-bpm-resolution-floor.md) | BPM floor: librosa on CC audio + CSV; Deezer/GetSongBPM as enrichment | Superseded by adr-005 | 2026-07-28 |
| [adr-005-deezer-preview-backbone](adr-005-deezer-preview-backbone.md) | BPM backbone: librosa on the Deezer 30 s preview; Deezer `bpm` as enrichment; CC/Jamendo dropped | Accepted (Spotify import section and preview-cache mitigation superseded by adr-010) | 2026-08-14 |
| [adr-006-e2-open-points](adr-006-e2-open-points.md) | The two points E.2 leaves open: `bpm_effective` = librosa's value; librosa arbitration scores 0.6 | Accepted | 2026-08-15 |
| [adr-007-session-construction-rules](adr-007-session-construction-rules.md) | Session construction rules: warmup/cooldown, level and goal caps, 2-value verdict + blocking list, full-track segments | Accepted | 2026-08-21 |
| [adr-008-session-persistence](adr-008-session-persistence.md) | `fct_session` materialized; `raw.feedback` rekeyed on `session_id`; DuckDB primary; SQL moved into `api/repositories/` | Superseded by adr-009 | 2026-08-29 |
| [adr-009-postgres-transactional-duckdb-analytical](adr-009-postgres-transactional-duckdb-analytical.md) | Postgres (Neon) as the transactional store beside DuckDB analytical; the warehouse ingests from Postgres | Accepted | 2026-08-30 |
| [adr-010-track-and-bpm-sources](adr-010-track-and-bpm-sources.md) | Three source roles (playback / identity / BPM); Spotify and YouTube identity-only, never BPM; no persistent audio storage | Accepted | 2026-10-02 |

ADR-011 (design of the BPM observation table, "Idea 2") is deferred until after the `v1.0-submission` tag.

### Extensions (B1–B7) — all `Gated`

> Common opening condition: the **core must be deployed, live, and tested from a clean clone**, and the
> source spike (phase 1) green. See `docs/archive/CYCLEBEAT_PLAN_V3.2.md` §0.

| ADR | Topic | Status | Date |
|---|---|---|---|
| [adr-b1-multi-agent-framework](adr-b1-multi-agent-framework.md) | B1 — Multi-agent framework: LangGraph vs lightweight supervisor | Proposed · Gated | to be decided |
| [adr-b2-spark-scale-threshold](adr-b2-spark-scale-threshold.md) | B2 — Spark as a scale spike; volume threshold; synthetic data | Proposed · Gated | to be decided |
| [adr-b3-batch-vs-streaming](adr-b3-batch-vs-streaming.md) | B3 — When streaming is warranted; Redpanda vs Kafka | Proposed · Gated | to be decided |
| [adr-b4-cloud-warehouse](adr-b4-cloud-warehouse.md) | B4 — Local DuckDB vs BigQuery/MotherDuck; Terraform IaC; cost guardrails | Proposed · Gated | to be decided |
| [adr-b5-cross-model-judge](adr-b5-cross-model-judge.md) | B5 — LLM judge on a model different from the generator | Proposed · Gated | to be decided |
| [adr-b6-k8s-optional](adr-b6-k8s-optional.md) | B6 — K8s outside the core track (only if DevOps target) | Proposed · Gated | to be decided |
| [adr-b7-dataops](adr-b7-dataops.md) | B7 — DataOps / data-reliability layer (gates, Elementary, alerting, runbook) | Proposed · Gated | to be decided |

## Discipline reminder

A `Gated` ADR is not implemented while it is gated, even if the code looks trivial. Gating is the #1
mitigation of the scope-creep risk (the v1 lesson). To open an ADR: verify the condition, move the status to
`Accepted` in a dedicated PR, and only then write code.
