# ADR-002 — Orchestration: Airflow over Prefect

- **Status**: Accepted
- **Date**: 2026-07 (Phase 0)
- **Owner**: Ellie

## Context

V2 planned Prefect for orchestration (lighter infra). The V3 repositioning targets a DE portfolio where the
orchestration tool is itself a hiring signal.

## Decision drivers

- **Market signal**: Airflow is ubiquitous in DE job postings; Prefect much less so.
- Cost: Airflow adds a scheduler + metadata DB to the stack — acceptable if isolated.
- The pipeline is small (3 DAGs), so the heavier tool must not slow the app or CI.

## Decision

Use **Airflow 3 (LocalExecutor)** with 3 DAGs (`dag_ingest`, `dag_resolve_bpm`, `dag_build_warehouse`), tasks
calling the domain functions via operators/BashOperator, retries + SLA. The scheduler + metadata DB live in a
separate compose profile `pipeline` (the app runs without them). In CI, DAGs are tested via `dag.test()` /
import checks, never by booting the full Airflow.

## Consequences

- +1-2 days of infra effort vs Prefect, assumed.
- Fallback documented: tasks remain plain Python functions callable via `make ingest` (CLI, no Airflow).
- The market-signal gain (Airflow on the CV) outweighs the infra lightness of Prefect for this project's goal.
