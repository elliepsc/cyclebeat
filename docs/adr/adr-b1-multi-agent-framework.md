# ADR-B1 — Multi-agent orchestration framework

- **Status**: Proposed · **Gated** (implement only once the core V3.1 is deployed + source spike green)
- **Module**: B1 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The V3.1 core ships a **single-agent copilot**, bounded (§9: tool-use, SELECT-only, sandboxed DuckDB D1,
out-of-band confirmation D2, trust boundary D5). B1 promotes it into a **supervised multi-agent system**
(supervisor/router → specialized workers: `warehouse-analyst`, `lineage-explainer`, `coaching-agent`).

The V3 plan had **removed** LangGraph from the copilot ("3 linear nodes don't justify a graph framework").
B1 changes that: conditional branching + shared state + N agents = a real graph. The question is whether we
reintroduce LangGraph *now that it's justified*, or stay framework-light.

## Decision drivers

- Stay within the zero-cost constraint (E.8) and avoid needless dependency debt.
- Keep **all** per-worker guardrails (D1/D2/D5) — security composes, it doesn't dilute.
- Learning value: LangGraph is in the syllabus of the targeted agentic courses (Blent Agentic AI).
- Interview demonstrability + trajectory eval (real gain vs single-agent).

## Options

### Option A — LangGraph (pedagogically recommended)
Explicit graph (nodes = agents, edges = routing/hand-off), typed shared state, checkpoints.
- ➕ Maps directly to Blent's LangGraph module; native streaming/persistence; readable in interviews.
- ➕ *Justified* reintroduction → material for this ADR ("when a graph framework becomes legitimate").
- ➖ Dependency + learning curve; over-engineering risk if routing stays simple.

### Option B — Lightweight supervisor (custom function-calling)
A supervisor = a loop that picks a worker via function-calling, workers = OpenAI-compatible clients.
- ➕ Zero new dependency; full control; consistent with V3's "no framework".
- ➖ You reimplement routing/state/tracing by hand; less "sellable" than LangGraph on an agentic CV.

## Decision (proposed)

**Recommendation: Option A (LangGraph)**, *because* the pedagogical/portfolio gain is the very goal of B1, and
the complexity (N agents + branching + state) finally justifies it. To be confirmed by Ellie; if the goal leans
"minimalism/control" over "course signal", switch to B.

## Consequences

- Extend `fct_agent_runs`: `agent_name`, `role` (supervisor|worker), `parent_run_id`, `handoff_reason`;
  new mart `mart_agent_topology`.
- Each worker keeps its guardrails; test `test_supervisor_cannot_bypass_worker_guards`.
- Eval: golden set of 12 routing questions (≥ 11/12) + trajectory eval (cost/latency vs single-agent documented).
- `trigger_resolve` stays subject to out-of-band confirmation D2 at both supervisor AND worker level.

## Gate opening condition

Core V3.1 deployed and live + source spike green + (recommended) B5 available for the trajectory eval.
