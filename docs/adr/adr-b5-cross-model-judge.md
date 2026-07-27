# ADR-B5 — LLM judge on a model different from the generator

- **Status**: Proposed · **Gated**
- **Module**: B5 (V3.2 plan)
- **Date**: to be decided
- **Owner**: Ellie

## Context

The core's LLM evals (coach groundedness, copilot) may use an LLM-as-judge. If **judge = generator** (same
model), the score is biased (inflated self-judging) — a flaw already flagged on homebarista. B5 professionalizes
the eval/observability layer (priority 3; maps Alexey, Blent Agentic AI, GDE).

## Decision drivers

- Remove self-judging bias → more defensible scores in interviews/defense.
- Zero cost (two free models: generator ≠ judge).
- Documented methodology (README footnote).

## Options

- **A — Judge on a free model different from the generator** (e.g. generation on Groq `qwen3-32b`, judge on a
  second free/Ollama model). **Recommended.**
- B — Judge = same model, bias assumed and documented. Acceptable as a last resort (it's the core's fallback
  position), but B5 exists precisely to do better.
- C — Human judge only (golden set with SQL-verifiable answers). Robust but doesn't cover qualitative dimensions
  (specificity, actionability). To be combined, not substituted.

## Decision (proposed)

**Option A**: cross-model judge, **combined** with the SQL-independently-verifiable golden set (C) for numeric
answers. Mandatory methodology footnote (the relative ranking remains the deliverable, not absolute scores).

## Consequences

- LiteLLM config: a `judge` caller pointing to a model distinct from `coach`/`copilot`.
- B5 observability: tracing (Langfuse self-host / OpenTelemetry), Grafana dashboard over `fct_llm_calls` /
  `fct_agent_runs` (cost/latency/tool usage/cost per agent), Evidently drift.
- Extends the golden set + wires B1's trajectory eval.

## Gate opening condition

Core V3.1 deployed; ideally right after B1 (to tool its trajectory eval).
