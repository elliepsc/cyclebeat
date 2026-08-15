# CLAUDE.md — CycleBeat V3

Project instructions for any coding agent. Derived from the NORMATIVE appendices
E.0-E.8 of `docs-notes/CYCLEBEAT_PLAN_V3.md` — when in doubt, read the source
appendix; on conflict, the truth-source order applies.

## Truth sources (strict order — E.0.1)

1. The repo code as it is.
2. `docs-notes/CYCLEBEAT_PLAN_V3.md` Appendix E (execution contracts).
3. The body of the V3 plan.

The DE core detail formerly split into `CYCLEBEAT_PLAN_V2.md §6-9` is now carried
normatively by V3 Appendix E (self-sufficient). V1/V2 are archived backups, kept
for history, not in the repo, and are NEVER a truth source.

Bonus layer: `docs-notes/CYCLEBEAT_PLAN_V3.2.md` (latest revision) specifies the
OPTIONAL modules B1-B7. It EXTENDS the V3 core — it does not replace it — and is
gated: no bonus module starts before the core is deployed + the source spike
(phase 1) is green. Consult it only when building a bonus module; for core work the
order above governs.

Conflict detected → the highest source wins AND you flag it.

## Execution rules (E.0)

- **Invent nothing.** Missing schema, ambiguous endpoint, unspecified threshold →
  ask the human or give 2 quantified options. Never a silent fill-in.
- **One phase = one branch + one PR.** Never a direct commit to main.
  Each PR: code + tests + docs + an entry in `docs/ai-workflow.md`.
- **Definition of done**: `make lint && make test-unit && make dbt` green.
  A failing test is NEVER bypassed (no skip, no xfail without a ticket) —
  it's fixed, or the task is blocked and escalated.
- **NORMATIVE sections** (appendices E.2-E.8, runbooks): convert to todos
  line by line, exact order, no omission or merging. Every new behavior ships
  its test in the same commit. A step deemed useless →
  ask, don't delete.
- **Re-verify, don't remember.** A runbook step believed "already done" is re-run
  through its own verification command before being skipped. In particular:
  `git ls-remote origin` before relying on an archive/safety branch, and cut work
  branches from `origin/main` after a fetch, never from local `main`.
- **Task end**: phase checklist updated in the PR + an ai-workflow.md entry
  (prompt/objective, what worked, what human review corrected). Invoke the
  `ai-workflow-scribe` subagent.

## Absolute prohibitions (E.0.5)

- Touching `.env` or committing a secret (git history is public eventually).
- Modifying `openapi.yaml` without updating backend + front client in the
  SAME PR.
- Writing SQL outside `api/repositories/` and `dbt/`.
- Adding a dependency without justification in the PR.
- Widening a phase's scope.
- Introducing a paid brick (E.8): paid API, SaaS, cloud instance →
  automatic rejection, free alternative or question.

## Target architecture (V3 §3, §5)

Offline pipeline: Deezer/CSV → dlt → Parquet lake → resolve BPM
(cross-validation) → DuckDB → dbt (staging → marts). Orchestration Airflow 3
LocalExecutor, 3 DAGs (`dag_ingest`, `dag_resolve_bpm`, `dag_build_warehouse`),
zero business logic in `dags/`. BPM backbone: `librosa` on the Deezer 30 s
preview, Deezer `bpm` as cross-validation enrichment, CSV as the manual floor
(ADR-005 — Jamendo/CC dropped, `extract_jamendo` removed from `dag_ingest`).
Service layer: `openapi.yaml` (contract written BEFORE the backend) → FastAPI
(routers → services → repositories) → React/Vite/TS (generated client,
network calls only via `src/api/`). LLM via LiteLLM → Groq
`qwen/qwen3-32b` (live) / Ollama (demo & CI). Warehouse Copilot: bounded
read-only tool-use (E.4). MCP server = the same tools as the copilot.

## Normative data contracts (E.2 — no variant allowed)

- BPM normalization: `while bpm > 180: bpm /= 2` then `while bpm < 70: bpm *= 2`.
- Zones on bpm_effective: Z1 < 100, Z2 100-115, Z3 116-130, Z4 131-145, Z5 > 145.
- Confidence: 2+ sources agreeing within ±3 BPM → 0.9 `cross_validated`;
  1 source → 0.6 `single_source`; disagreement > 3 → librosa arbitration else
  0.3 + `review` flag; no source → bpm NULL, excluded from the planner.
- raw/dim/fct schemas: see E.2 — any deviation = breaking change with impact
  analysis.

## Copilot guardrails (E.4 — not optional)

query_marts: single SELECT (sqlglot), marts allowlist, LIMIT 200 injected,
5 s timeout. trigger_resolve: cap 10 tracks, confirm=true required, logged.
Run caps: max 6 tool calls, question ≤ 500 chars, 60 s timeout, LiteLLM
budget per caller. The 9 tests in `test_copilot_guards.py` (E.4 list) live
in the SAME commit as the tools.

## Conventions (E.6)

Python 3.11+, uv + pyproject, ruff + mypy strict on `cyclebeat/` and `api/`.
Front: pnpm/npm locked. Makefile targets: setup, ingest, dbt, api, front,
test-unit, test-integration, eval, audit, lint. Pydantic v2 everywhere, no
FastAPI import outside `api/`. Code/identifiers/commits and repo docs in
English. The `docs-notes/` ultraplan notes may stay bilingual (see `*.fr.md`).

## Zero cost (E.8 — cross-cutting invariant)

DEMO_MODE by default with no key. Groq free tier with 429 retry (exponential
backoff + jitter, 5 attempts), max_tokens ≥ 1024 on generation nodes
(reasoning model). Aggressive caching of music APIs (lake = permanent cache),
pacing ≥ 0.3 s. Any live eval: 5-case sample first.

## Available subagents (`.claude/agents/`)

- `dbt-reviewer` — on any PR touching dbt/ or SQL, before merge.
- `ai-workflow-scribe` — end of each session/PR (grid criterion 2).
- `security-auditor` — phase 0 (secret hygiene) and phase 10 (5 crit. 13 artifacts).
- `contract-guardian` — PRs of phases 4-5 touching openapi.yaml or api/.

## Known pitfalls

- BPM half-time/double-time: the E.2 normalization is THE answer, not a local
  heuristic.
- Music API quotas: never re-fetch in CI/review — committed demo snapshot.
- Groq free tier ≈ 6,000 TPM: throttle via LiteLLM upstream, don't suffer the 429s.
- Removing a heavy dependency can remove a runtime import something else was
  silently relying on (dlt 0.5.4 needs `pkg_resources`/setuptools, previously
  supplied by torch). After any dependency removal run `make test-unit` — lint
  does not catch a break at package-import time.
- When a phase exit criterion is a `grep` for forbidden names, the assertion
  tests are the only place those names may appear.
- No non-ASCII in the stdout of anything a Makefile target runs: the Windows
  console is cp1252 and `make ingest` crashed on an emoji.
- The v1 leftovers (Spotify, Qdrant, LangGraph, the v1 UI) were removed by the
  phase 0 purge. `POST /session/generate` is a deliberate 501 until the V3
  resolver (phase 2) and the contract-first rewrite (phase 4) land — do not
  reconnect it to anything before then.

## Phases

§15 of the V3 plan sets the phases and their BLOCKING exit criteria.
Before coding a phase: restate the brief (E.7 template: objective,
inputs, deliverables, validation, out of scope) and get it validated in plan mode.
Phases 1 and 9 contain human actions: prepare, document,
stop — never simulate a result.
