# ADR-B3 — Streaming: justification and choice (Redpanda vs Kafka)

- **Status**: Proposed · **Gated**
- **Module**: B3 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

CycleBeat is fundamentally **batch** (offline Airflow pipeline). B3 adds a **streaming path** to prove real-time
skills (DE gap: Blent DE, DE Zoomcamp M7). Like B2, it needs a *plausible* use case — otherwise streaming = decor.

## Decision drivers

- Credible real-time use case in the "cycling session" domain.
- Schema management (Avro + registry) = serious DE signal.
- Zero cost, opt-in (the app runs without streaming).

## Options

### Use case (what to stream)
- **A — live session telemetry** ("now playing" / simulated cadence/BPM during the session) → real-time mart
  `mart_live_session`. *Plausible and demonstrable.* **Recommended.**
- B — rolling feedback stream. Plausible but visually poorer.

### Broker
- **Redpanda** (Kafka-compatible, Apache-2.0, lightweight, built-in schema registry) — **recommended**: single
  container, no ZooKeeper, free.
- Kafka + Confluent registry — heavier (ZooKeeper/KRaft + separate registry), same API. Overkill here.

### Consumer
- Simple Python consumer (recommended for readability) vs Kafka Streams/ksqlDB (more "showcase" but heavier).

## Decision (proposed)

Use case **A** (live telemetry) on **Redpanda**, **Avro** schemas validated via the registry, **Python consumer**
landing to the lake + real-time mart. Kafka Streams left optional if time permits.

## Consequences

- `streaming` compose profile (simulated producer + Redpanda + consumer); the app doesn't start it by default.
- Versioned Avro schema; test: non-conforming message rejected and counted.
- 1 integration test `@streaming` (producer→topic→consumer→mart); README documents batch vs streaming.

## Gate opening condition

Core V3.1 deployed; to be done after B2 (the "DE at scale" block).
