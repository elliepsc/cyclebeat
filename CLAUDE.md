# CLAUDE.md — CycleBeat

Project instructions for any coding agent. Where we are: [docs/ROADMAP.md](docs/ROADMAP.md).
Why each decision was taken: the [ADR index](docs/adr/README.md). Everything else is in `docs/archive/`
and is history, not a source.

## Truth sources (strict order)

1. The repo code as it is.
2. The ADRs (`docs/adr/`), then `docs/ROADMAP.md` for status and priorities.
3. `docs/archive/` — superseded plans, kept for history. It holds the E.4 copilot specification
   (Appendix E.4 of `docs/archive/CYCLEBEAT_PLAN_V3.md`) until phase 6 turns it into code and tests;
   `docs/archive/CYCLEBEAT_PLAN_V3.2.md` is consulted only to build a bonus module (B1-B7), gated behind
   the deployed core.

V1/V2 are never a source. Conflict detected → the highest source wins AND you flag it.

## Execution rules

- **Invent nothing.** Missing schema, ambiguous endpoint, unspecified threshold → ask the human or give
  2 quantified options. Never a silent fill-in. A claim about an external API or platform is checked
  against its official documentation (with the URL) or left as an open question.
- **One phase = one branch + one PR.** Never a direct commit to main. Each PR: code + tests + docs + an
  entry in `docs/ai-workflow.md`. The human opens and merges the PR.
- **Definition of done**: lint (including `check_links`), typecheck, `test-unit`, `eval`, `dbt` and
  `contract` green, locally then in CI. A failing test is NEVER bypassed (no skip, no xfail without a
  ticket): it is fixed, or the task is blocked and escalated.
- Every new behavior ships its test in the same commit. A step deemed useless → ask, don't delete.
- **Name the reference branch before verifying a doc.** Run `git branch --show-current` and state what
  the claims are checked against (normally `origin/main`) *before* reading any code.
- **Re-verify, don't remember.** A step believed "already done" is re-run through its own verification
  command. Cut work branches from `origin/main` after a fetch, never from local `main`.
- **Write facts after they happen**, in `ai-workflow.md` and everywhere else: numbers after the last
  measurement, a PR as opened or merged only once it is.
- **Experiments never touch the real `lake/` or `data/`.**
- **Task end**: an `ai-workflow.md` entry (prompt/objective, what worked, what human review corrected);
  invoke the `ai-workflow-scribe` subagent.

## Absolute prohibitions

- Touching `.env` or committing a secret.
- Modifying `openapi.yaml` without updating backend + front client in the SAME PR.
- Writing SQL outside `api/repositories/` and `dbt/`.
- Adding a dependency without justification in the PR.
- Widening a phase's scope.
- Introducing a paid brick (paid API, SaaS, cloud instance) → automatic rejection, free alternative or
  question.
- Storing audio durably: **no audio is stored durably (ADR-010); every preview download goes through
  `temporary_download`** (`cyclebeat/http.py`), analysed from a temporary file deleted in a `finally`.
- Reconnecting Spotify or YouTube for BPM: they are track identity only (ADR-010).

## Architecture

Offline pipeline: Deezer/CSV → dlt → Parquet lake → resolve BPM (cross-validation) → DuckDB → dbt
(staging → marts). Airflow 3 LocalExecutor, 3 DAGs (`dag_ingest`, `dag_resolve_bpm`,
`dag_build_warehouse`), zero business logic in `dags/`. BPM backbone: `librosa` on the Deezer 30 s
preview, Deezer `bpm` as enrichment, CSV as the manual floor (ADR-005, ADR-010). Transactional store:
Postgres when `DATABASE_URL` is set, SQLite otherwise; DuckDB is analytical (ADR-009). Service layer:
`openapi.yaml` (contract written BEFORE the backend) → FastAPI (routers → services → repositories) →
React/Vite/TS (generated client, network calls only via `src/api/`). LLM via LiteLLM → Groq
`qwen/qwen3-32b` (live) / Ollama (demo & CI). Warehouse Copilot: bounded read-only tool-use; the MCP
server exposes the same tools.

## Normative data contracts — no variant allowed

The code is the reference; these lines only point to it.

- **BPM normalization, zones, confidence**: `cyclebeat/e2.py` (`normalize_bpm`, `zone_for`, `resolve`)
  — halve above 180, double below 70; Z1 < 100, Z2 100-115, Z3 116-130, Z4 131-145, Z5 > 145;
  ±3 BPM agreement. The two points the appendix left open are decided in
  [ADR-006](docs/adr/adr-006-e2-open-points.md) (`bpm_effective`, arbitration scores 0.6).
- **Session construction rules** (warmup/cooldown, level and goal caps, verdict, blocking checks):
  `cyclebeat/rules.py` and [ADR-007](docs/adr/adr-007-session-construction-rules.md).
- **BPM source of truth and its floor**: [ADR-005](docs/adr/adr-005-deezer-preview-backbone.md) and
  [ADR-010](docs/adr/adr-010-track-and-bpm-sources.md); ADR-004 is superseded.
- **raw/dim/fct schemas**: the dbt models and `cyclebeat/models.py`; any deviation is a breaking change
  with an impact analysis.

## Copilot guardrails (not optional)

Not in code yet (phase 6); specified in Appendix E.4 of `docs/archive/CYCLEBEAT_PLAN_V3.md`.
`query_marts`: single SELECT (sqlglot), marts allowlist, LIMIT 200 injected, 5 s timeout.
`trigger_resolve`: cap 10 tracks, `confirm=true` required, logged. Run caps: max 6 tool calls,
question ≤ 500 chars, 60 s timeout, LiteLLM budget per caller. The 9 tests of E.4 live in
`test_copilot_guards.py`, in the SAME commit as the tools.

## Conventions

Development is WSL2 (Ubuntu) only, with the clone on the Linux filesystem (`~/projets/cyclebeat`,
never `/mnt/c`); setup (uv, nvm + `frontend/.nvmrc`, make, Docker Desktop WSL integration) is in
[CONTRIBUTING.md](CONTRIBUTING.md).
Python 3.11+, uv + pyproject, ruff everywhere, mypy strict on `api/`. Front: pnpm/npm locked.
Makefile targets: setup, ingest, dbt, api, front, test-unit, test-integration, eval, audit, lint,
typecheck, contract. Pydantic v2 everywhere, no FastAPI import outside `api/`. Code, identifiers,
commits and repo docs in English.

## Zero cost

DEMO_MODE by default with no key. Groq free tier with 429 retry (exponential backoff + jitter,
5 attempts), max_tokens ≥ 1024 on generation nodes (reasoning model). Music APIs: JSON responses cached,
pacing ≥ 0.3 s, never re-fetched in CI/review (committed demo snapshot). Any live eval: 5-case sample
first.

## Subagents (`.claude/agents/`)

- `dbt-reviewer` — any PR touching `dbt/` or SQL, before merge.
- `ai-workflow-scribe` — end of each session/PR.
- `security-auditor` — secret hygiene and the final audit.
- `contract-guardian` — PRs touching `openapi.yaml` or `api/`.

## Known pitfalls

- BPM half-time/double-time: the E.2 normalization is THE answer, not a local heuristic.
- A deploy-config change is verified by calling a business endpoint (e.g. `POST /v1/sessions/generate`
  with the demo source), not `/health` alone: the old Render config returned 200 there and 422
  `empty_catalogue` on generate.
- No `DATABASE_URL` in production until the Postgres CI job (`TEST_DATABASE_URL`, `postgres:16-alpine`)
  is green on main. The test suite strips `DATABASE_URL` on purpose.
- Groq free tier ≈ 6,000 TPM: throttle via LiteLLM upstream, don't suffer the 429s.
- Removing a heavy dependency can remove a runtime import something else silently relied on (dlt needs
  `pkg_resources`/setuptools, previously supplied by torch). After any dependency removal run
  `make test-unit` — lint does not catch a break at package-import time.
- When a phase exit criterion is a `grep` for forbidden names, the assertion tests are the only place
  those names may appear.
- Phases 1 and 9 contain human actions: prepare, document, stop — never simulate a result.
