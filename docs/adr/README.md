# Architecture Decision Records — CycleBeat

Log of architecture decisions. One structural decision = one ADR, numbered, immutable once `Accepted`
(you don't rewrite it: you create a new one that supersedes it).

## Convention

Lightweight format (MADR-inspired): **Context → Options → Decision → Consequences**. Statuses:

- `Proposed` — written, not yet decided by the owner.
- `Gated` — proposed **and blocked**: do not implement until its opening condition is met.
- `Accepted` — decision made, implementation authorized.
- `Superseded by adr-XXX` — replaced.

## Index

### Core (00x series) — Phase 0 deliverables of the V3.1 plan, **to be written when the build starts**
> These three ADRs are not written yet: they are part of Phase 0 (purge & setup) of the core.

| ADR | Topic | Status |
|---|---|---|
| [adr-001-v3-repositioning](adr-001-v3-repositioning.md) | Why V3 (purge Spotify/Qdrant, DE-first, AI Dev Tools target) | Accepted |
| [adr-002-airflow](adr-002-airflow.md) | Airflow vs Prefect | Accepted |
| [adr-003-render-no-disk](adr-003-render-no-disk.md) | No Render disk: demo DB baked into the image (D3) | Accepted |
| [adr-004-bpm-resolution-floor](adr-004-bpm-resolution-floor.md) | BPM floor: librosa on CC audio + CSV; Deezer/GetSongBPM as enrichment | Accepted (coverage pending phase-1 spike) |

### Bonus (B series — V3.2 plan) — **all `Gated`**
> Common opening condition: the **core V3.1 must be deployed, live, and tested from a clean clone**,
> and the source spike (phase 1) green. See `docs-notes/CYCLEBEAT_PLAN_V3.2.md` §0.

| ADR | Module | Topic | Status |
|---|---|---|---|
| [adr-b1-multi-agent-framework](adr-b1-multi-agent-framework.md) | B1 | Multi-agent framework: LangGraph vs lightweight supervisor | Proposed · Gated |
| [adr-b2-spark-scale-threshold](adr-b2-spark-scale-threshold.md) | B2 | Spark as a scale spike; volume threshold; synthetic data | Proposed · Gated |
| [adr-b3-batch-vs-streaming](adr-b3-batch-vs-streaming.md) | B3 | When streaming is warranted; Redpanda vs Kafka | Proposed · Gated |
| [adr-b4-cloud-warehouse](adr-b4-cloud-warehouse.md) | B4 | Local DuckDB vs BigQuery/MotherDuck; Terraform IaC; cost guardrails | Proposed · Gated |
| [adr-b5-cross-model-judge](adr-b5-cross-model-judge.md) | B5 | LLM judge on a model different from the generator | Proposed · Gated |
| [adr-b6-k8s-optional](adr-b6-k8s-optional.md) | B6 | K8s outside the core track (only if DevOps target) | Proposed · Gated |
| [adr-b7-dataops](adr-b7-dataops.md) | B7 | DataOps / data-reliability layer (gates, Elementary, alerting, runbook) | Proposed · Gated |

## Discipline reminder

A `Gated` ADR is not implemented while it is gated, even if the code looks trivial. Gating is the #1
mitigation of the scope-creep risk (the v1 lesson). To open an ADR: verify the condition, move the status to
`Accepted` in a dedicated PR, and only then write code.
