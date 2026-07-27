# ADR-B7 — DataOps / data-reliability layer

- **Status**: Proposed · **Gated**
- **Module**: B7 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The core has DataOps threads scattered around (dbt tests, CI, mutation check, data-quality marts; B4 adds
backfills/SLA/data contracts). B7 consolidates them into an explicit **data-reliability** layer and adds what's
missing: **blocking** quality gates, observability, anomaly monitoring, alerting, and a data-incident runbook.
Goal: answer "how do you *know* the pipeline is healthy, and what happens when it isn't?" — increasingly expected
of DE/AE roles.

## Decision drivers

- Zero cost (OSS only).
- Turn "we have dbt tests" into "bad data fails loudly and is triaged", a real reliability story.
- Reuse the existing warehouse + dbt + Airflow (no new infra).

## Options

### Observability / gates tool
- **A — Elementary Data** (OSS, dbt-native: freshness, volume/anomaly monitors, schema-change, report + lineage)
  — **recommended**: dbt-native, zero infra, produces a committable report.
- B — re_data (OSS alternative) — similar, less mature ecosystem.
- C — hand-rolled dbt tests only (freshness + custom volume checks) — cheapest, but no observability report.

### Gate strictness
- **Blocking in CI** (freshness/volume/schema failures fail the build) — recommended; warnings-only defeats the
  purpose.

### Alerting (must stay 0 €)
- GitHub Actions notification on pipeline failure + Airflow SLA-miss callback. No paid SaaS (Monte Carlo, etc.).

## Decision (proposed)

**Elementary** for observability + **blocking** freshness/volume/schema gates in CI, **slim CI**
(`dbt build --select state:modified+`), **dbt env targets** (dev/ci/prod), free alerting, and a
**data-incident runbook**. Fall back to hand-rolled dbt tests (C) if Elementary adds friction.

## Consequences

- New dev dependency: Elementary dbt package (OSS) + its report generation in CI.
- `docs/runbooks/data-incident.md` created; ties to the crit. 13 operational-diagnosis artifact.
- CI gains a blocking data-quality job; a deliberately stale/anomalous fixture proves the gate fails.
- The Data Quality screen (front) can surface the Elementary report.

## Gate opening condition

Core V3.1 deployed; naturally paired with B4 (same warehouse/dbt/Airflow). Cheap enough to slot right after B5.
