# ADR-B2 — Spark as a scale spike (volume threshold, synthetic data)

- **Status**: Proposed · **Gated**
- **Module**: B2 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The target warehouse (DuckDB) handles ~40 patterns + a few thousand tracks — a **trivial** volume. B2 aims to
prove **distributed computing** skills (DE market gap: Blent DE, DE Zoomcamp M6). The risk is **CV-padding**:
Spark on a tiny dataset is architecturally unjustified and a senior reviewer will see it.

## Decision drivers

- Demonstrate real Spark mastery (DataFrame API, joins/groupBy, partitions, shuffles, broadcast).
- Stay honest: never claim Spark is *necessary* for CycleBeat's actual volume.
- Zero cost (local PySpark, no managed cluster).
- Don't diverge from the output contract (the warehouse reads the same Parquet).

## Options

### Option A — Spark as an *alternative path* for `dag_build_warehouse`, on synthetic data (recommended)
Generate a large synthetic dataset (10–50M events/resolutions), reimplement the heavy aggregation in PySpark,
write the same Parquet. The ADR sets the **threshold**: "DuckDB by default; Spark above ~X GB".
- ➕ Spark becomes *relevant*; DuckDB↔Spark parity test on the small set; honest benchmark.
- ➖ Effort to generate data + maintain a second engine.

### Option B — dbt-spark on the real (small) volume
- ➕ Less custom code.
- ➖ Unjustified at this volume → exactly the CV-padding we want to avoid. **Rejected.**

### Option C — Skip Spark, document the "scale path" in prose
- ➕ Zero effort.
- ➖ No demonstrable artifact in interviews. **Rejected** (B2's goal is precisely the artifact).

## Decision (proposed)

**Option A.** Threshold to be specified at implementation time (order of magnitude ~1–5 GB / tens of millions of
rows). Synthetic data generated locally, committed and reproducible script.

## Consequences

- Makefile target `spark-build`; optional `spark` compose profile; versioned synthetic data generator.
- Mandatory parity test (Spark vs DuckDB → identical results on the small set).
- Benchmark (time, volume) documented; ADR explicitly states "why DuckDB remains the default".

## Gate opening condition

Core V3.1 deployed + (recommended) after B1/B5 — B2/B3 are the second priority block.
