# ADR-B4 — Managed cloud warehouse + IaC (local DuckDB vs BigQuery/MotherDuck; Terraform)

- **Status**: Proposed · **Gated**
- **Module**: B4 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The core stays on **local DuckDB** (D3/D4). B4 adds a **managed cloud warehouse target** + **IaC** to fill the
"cloud" blind spot and the DE Zoomcamp M1 (IaC) / M3 (BigQuery) — **on a strict free tier**. Since dbt is
multi-adapter, the switch is essentially config.

## Decision drivers

- **Guaranteed** zero cost: capped free tier + documented `terraform destroy`, no residual billable resource.
- DE/AE cloud signal: partitioning/clustering, query-cost awareness, reproducible IaC.
- Don't complicate the core: the cloud target is **alternative**, env-selected, never required.

## Options

### Cloud warehouse target
- **A — BigQuery free tier** (1 TB queries/month free, 10 GB storage) — **recommended**: it's the DE Zoomcamp
  M3/M4 target, real partitioning/clustering, mature dbt-bigquery. Cost guardrail = pruning + cap.
- B — MotherDuck free tier — closer to DuckDB (less learning), but weaker market signal than BigQuery.

### IaC
- **Terraform** (OSS CLI, local state) provisions dataset + IAM/service account. `apply`/`destroy` documented.
- (Rejected alternative: manual console provisioning → not reproducible, against the IaC spirit.)

### "Prod" orchestration (0 €, deepen Airflow — no extra infra)
Backfills (catchup + date-partitioned runs), SLAs, cross-DAG data contracts (freshness/row-count assertions
between `resolve`→`build`).

## Decision (proposed)

**BigQuery free tier** as the alternative cloud target (`WAREHOUSE_TARGET=bigquery`), **Terraform** for the
dataset, + Airflow prod deepening. MotherDuck remains the documented fallback.

## Consequences

- Multi-target dbt profile; the same models build on DuckDB **and** BigQuery.
- `terraform apply` provisions, `terraform destroy` cleans up (documented manual test = zero residual cost).
- Cost guardrail written (query cap, partition pruning); backfill demonstrated and logged.

## Gate opening condition

Core V3.1 deployed; after the B2/B3 block. Verify the BigQuery free tier is still current at implementation time.
