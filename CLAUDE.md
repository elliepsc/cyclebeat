# CLAUDE.md — CycleBeat

Project instructions for any coding agent. Where we are: [docs/ROADMAP.md](docs/ROADMAP.md).
Why each decision was taken: the [ADR index](docs/adr/README.md). Everything else is in `docs/archive/`
and is history, not a source.
What the system must do: [product-spec.md](product-spec.md). Remaining work: the [GitHub issues](https://github.com/elliepsc/cyclebeat/issues).

## Truth sources (strict order)

1. The repo code as it is.
2. The ADRs (`docs/adr/`), then `docs/ROADMAP.md` for status and priorities.
3. `docs/archive/` — superseded plans, kept for history. It holds the E.4 copilot specification
   (Appendix E.4 of `docs/archive/CYCLEBEAT_PLAN_V3.md`) until phase 6 turns it into code and tests;
   `docs/archive/CYCLEBEAT_PLAN_V3.2.md` is consulted only to build a bonus module (B1-B7), gated behind
   the deployed core.

V1/V2 are never a source. Conflict detected → the highest source wins AND you flag it.
- `docs/grading-criteria.md` is a verbatim copy of the course rubric: re-check it against its source (URL and commit in its header) before relying on it; the old grid is in `docs/archive/`.
- A truth source must be tracked by git: an ignored source is absent from every clone (`git check-ignore -v <file>` returns nothing).

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
- A task brief is a claim, not a fact: re-verify each state it asserts against the remote before acting.
- A file or task named in a brief is checked with `git ls-files` first: a brief describes the intended repo, not the current one.
- Never present a command block with placeholders as runnable: one command per block, each placeholder spelled out as a substitution.
- **Write facts after they happen**, in `ai-workflow.md` and everywhere else: numbers after the last
  measurement, a PR as opened or merged only once it is.
- **Experiments never touch the real `lake/` or `data/`.**
- A block of work starts by reading its issue, `gh issue view <N> --json title,body,comments` (plain `gh issue view` fails on gh 2.45: Projects classic sunset); the agent comments its plan on the issue before coding, each comment starting with "Posted by the coding agent (Claude Code)."
- Commits cite `#N`; the PR says `Closes #N` and ticks the acceptance criteria met; the agent never closes or reopens an issue by hand: the merged PR closes it.
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

Specified in Appendix E.4 of `docs/archive/CYCLEBEAT_PLAN_V3.md`, amended by
[ADR-012](docs/adr/adr-012-deterministic-tools-llm-separation.md). In code (phase 7):
`query_marts` and `get_quality_report` in `api/services/warehouse_tools.py`: single SELECT
(sqlglot), marts allowlist, LIMIT 200 injected, 5 s timeout, over a locked read-only DuckDB
connection (`api/repositories/readonly_warehouse.py`); the MCP server and the future copilot
both call them. Still phase 6 (LLM layer): `trigger_resolve` (cap 10 tracks, `confirm=true`
required, logged) and the run caps (max 6 tool calls, question ≤ 500 chars, 60 s timeout,
LiteLLM budget per caller). The E.4 tests live in `test_copilot_guards.py`: 6 now, the 3 that
need the agent loop with the LLM layer (ADR-012).

## Agent guardrails (code, not instructions)

`.claude/settings.json` deny rules and the PreToolUse hook `agent-hooks/pre_tool_use.py` refuse
writes to `data/`/`lake/`, secrets files, force push, pushes and merges to `main`, `gh pr
create/merge`, Render calls, and edits to the guardrails themselves. A refusal is not an obstacle
to route around: stop and report it. See [docs/permissions.md](docs/permissions.md).
This includes suspected false positives and classifier refusals: never retry with an equivalent
command (e.g. `git add .claude` after `git add .claude/settings.json` is refused); report it and
propose the fix to the owner.
Deny rules on Bash are prefix-based and can refuse a command whose SOURCE is protected (`cp agent-hooks/... <scratch>`): stop and ask the owner for the copy.

## Conventions

Development is WSL2 (Ubuntu) only, with the clone on the Linux filesystem (`~/projets/cyclebeat`,
never `/mnt/c`); setup (uv, nvm + `frontend/.nvmrc`, make, Docker Desktop WSL integration) is in
[CONTRIBUTING.md](CONTRIBUTING.md).
Python 3.11+, uv + pyproject, ruff everywhere, mypy strict on `api/`. Front: pnpm/npm locked.
Makefile targets: setup, ingest, dbt, api, front, test-unit, test-integration, eval, audit, lint,
typecheck, contract, mcp-server, plugin (`plugins/` is generated by `make plugin`, never edited).
Pydantic v2 everywhere, no FastAPI import outside `api/`. Code, identifiers, commits and repo docs
in English.
Run project commands through `uv run` (or `make`), never a bare `python`: another interpreter can carry another duckdb.
Before a heavy dev dependency (an orchestrator) enters the lock, check it against the existing pins: `uv lock` surfaces the conflicts only at resolution.

## Zero cost

DEMO_MODE by default with no key. Groq free tier with 429 retry (exponential backoff + jitter,
5 attempts), max_tokens ≥ 1024 on generation nodes (reasoning model). Music APIs: JSON responses cached,
pacing ≥ 0.3 s, never re-fetched in CI/review (committed demo snapshot). Any live eval: 5-case sample
first.

## Subagents (`.claude/agents/`)

Who does what, the hand-offs and where each trace lands: [docs/agent-team.md](docs/agent-team.md).

- `dbt-reviewer` — any PR touching `dbt/` or SQL, before merge.
- `ai-workflow-scribe` — end of each session/PR.
- `security-auditor` — secret hygiene and the final audit.
- `contract-guardian` — every diff touching `openapi.yaml` or `api/`.

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
- A persistence test must recreate the container (`up -d --no-deps --force-recreate <svc>`), not
  restart it: a restart keeps the writable layer, so a local-file fallback (SQLite) passes it.
- Never pipe a gate command (`make lint`, `make test-unit`, ...) into `tail`/`head` without checking
  its own exit code (`set -o pipefail` or `${PIPESTATUS[0]}`): the pipeline returns the exit code of
  `tail`, so a red gate looks green (phase 7: a commit with 2 dead links went through this way).
- The hook reads `RUNTIME_DB_PATH` only as a command prefix (`RUNTIME_DB_PATH=... make dbt`), not
  from the exported environment.
- A file ignored by git passes every local check and is missing in CI: `*.log` kept an incident
  log out of `ce4b631`, its link passed locally and broke the CI. A link must point to a TRACKED
  file (`make lint` now refuses an untracked target); check `git check-ignore -v <file>` before
  citing a new file.
- Repo labels "criterion 12" / "criterion 13" use the OLD grid's numbering (`docs/archive/`), not the official one.
- `file:line` pointers break when text is prepended to the target: prefer a section anchor, and grep for such pointers before editing a target.
- Never chain `git push` after a gate with `;` or a newline: use `&&` or check the exit code; a gate that cannot run (Docker daemon down) is red, not skipped.
- Subagent definitions are read from the checked-out branch: before a review, check that `.claude/agents/<name>.md` there is the intended version.
- Commit raw subagent review outputs under `security/pr-audits/` as soon as they return: the scratchpad in `/tmp` does not survive a WSL shutdown.
- A raw subagent output can carry links relative to the reviewer's context, dead from `security/pr-audits/`: run `make lint` before committing it, and disclose any change in its provenance header.
- A test that runs `make` in a subprocess drops `MAKEFLAGS`, `MFLAGS` and `MAKELEVEL` from its environment: a parent `make -i` would leak in and hide the child's exit status.
- A doc sentence describing a guardrail is checked against the hook's code, not the rule's intent (issue #45: the hook refuses `gh issue close` only, not reopen, delete, transfer or `gh api` state changes).
- A guard over SQL text compares identifiers as the engine does (DuckDB folds ASCII only) and re-checks the SQL it emits.
- In a container, `HEALTHCHECK` and `CMD` read the same `${PORT:-8000}`, and `CMD` uses `exec` so uvicorn receives the stop signal.
- A compose service built from the API image inherits its `HEALTHCHECK`: a service that does not run uvicorn needs `healthcheck: disable: true`.
- A `make dbt` failure the code does not explain: retry on a clean `RUNTIME_DB_PATH` before touching the models, the runtime DuckDB can be stale.
- A helper whose docstring states a precondition ("an ALREADY normalized value") is composed, not called, by callers holding unvalidated data; the composition sits next to it (`e2.zone_of` under `e2.zone_for`).
- A measurement count and a warehouse grain are different numbers: say which one a figure is when a report and a mart disagree.
- A test that cannot run on the dev OS is run in Docker before pushing to CI to find out.
- A data test that passes on an empty model proves nothing: on the scratch warehouse (0 sessions) 32 of 72 dbt data tests run over empty models. A new grain or key test is shown to fail once on an injected duplicate row before it counts as evidence.
- A mart's grain is written as one sentence ('one row represents ...') from its SQL and sources before a key is chosen; a key picked because the current rows are unique is not a grain (issue #46 → #54).
- A composite-grain test uses a singular `GROUP BY ... HAVING count(*) > 1`, not `unique` on a concatenated key: a NULL in one column makes the concatenation NULL and hides the duplicate.
- When the docs leave a tool's behaviour open (a dbt unit test with `rows: []`), the answer is a first run against the unchanged code, expected to fail; record the docs URL and the locked version next to the measurement.
