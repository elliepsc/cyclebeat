# Quality bar — the official grid and the old one, side by side

Peers grade with the **official grid** ([docs/grading-criteria.md](grading-criteria.md): 12 criteria,
24 points, 10 to pass, course repository commits 3ef6f18 and 526d9c1 of 16 October 2026). The
**old grid** ([archive](archive/grading-criteria-v1-2026-10-09.md): 14 criteria, 30 points, the draft
of 9 October 2026) is no longer used for grading; it stays here because most of the repository was
built and labelled against it ("criterion 12", "criterion 13").

One row per requirement. The two grids are scored separately: **never add their points**. This page
records where the repository stands; it does not plan the gaps.

**Evidence levels.** EXECUTED: a command was run and its result is recorded (who, when). OBSERVED:
read in the repository, nothing run. DECLARED: stated in a document, not checked. ABSENT: looked for,
not found. State as of 22 October 2026, `main` at 31e2d26 (PR #42 merged); CI run cited:
[39743172341](https://github.com/elliepsc/cyclebeat/actions/runs/39743172341) on fed5712, the content
merged as 31e2d26.

| Requirement | Official grid (max) | Old grid (max) | Provenance | Current state | Evidence | What is missing |
|---|---|---|---|---|---|---|
| Problem description | Problem Description (2) | 1. Problem Description (2) | both | `README.md` opens with the problem, the system and its behaviour | OBSERVED | — |
| Written product spec **and** a public task tracker whose tasks carry acceptance criteria, used by the agents | Product Specification (2) | — | official | No `product-spec.md` (`ls`, 22 Oct). The plans that served as specs are archived, in French (`docs/archive/`). GitHub issues are enabled and empty (0 issues) | ABSENT | a spec, a public tracker, acceptance criteria, evidence that agents used it |
| The agent team and how it works together | Agent Team Specification (2) | — | official | Four subagents with role and trigger (`CLAUDE.md`, "Subagents"; `.claude/agents/`); one phase = one branch = one PR; reviews committed under `security/pr-audits/` | OBSERVED | one description of the team's process in a single place |
| Project context for agents | Context Management (2) | (old grid: `AGENTS.md` in the expected layout) | both | `AGENTS.md` points to `CLAUDE.md`, which points to `docs/ROADMAP.md`, the ADR index, `docs/permissions.md` | OBSERVED | — |
| How AI tools were used and reviewed | — | 2. AI-Assisted Development Workflow (2) | old | `docs/ai-workflow.md`, one entry per session (prompt, iterations, human corrections) | OBSERVED | — |
| Technologies and architecture | — | 3. Technologies and System Architecture (2) | old | `README.md`, "Architecture"; ADRs | OBSERVED | — |
| Full stack end to end, persistent database, one command | Application (2) | 4. Frontend (3), 6. Backend (3), 7. Database Integration (2) | both | React → FastAPI → Postgres under `docker compose up --build`; CI job `integration` drives it over HTTP | EXECUTED (CI 39743172341, job `integration`, success) | — |
| Frontend tests | (inside Application) | 4. Frontend Implementation, level 3 | old | vitest suite, CI job `frontend` | EXECUTED (CI 39743172341, job `frontend`, success) | proof of use in a browser (old grid, level 3 reads "functional") |
| API contract | — | 5. API Contract (2) | old | hand-written `openapi.yaml`; `make contract` | EXECUTED (CI 39743172341, job `build`; local DoD on c3739c1, 22 Oct: 25 passed) | — |
| Backend structure and tests | (inside Application, Testing) | 6. Backend Implementation (3) | both | routers → services → repositories; `make test-unit` | EXECUTED (local DoD on c3739c1, 22 Oct: 677 passed; owner reports 742 with the hook patch) | — |
| Database across environments | (inside Application) | 7. Database Integration (2) | both | Postgres when `DATABASE_URL` is set, SQLite otherwise (ADR-009); Postgres in compose and in CI | OBSERVED | — |
| Unit **and** integration tests, **one command**, passing | Testing (2) | 9. Integration Testing (2) | both | both suites exist and pass, run by `make test-unit` and `make test-integration`; no target runs both (Makefile, 22 Oct) | EXECUTED for the suites (CI 39743172341); ABSENT for the single command | one command for both suites (official grid) |
| Whole system in containers, database included, one command | Containerization (2) | 8. Containerization (2) | both | `docker compose up --build`: postgres, api, web with chained healthchecks | EXECUTED (CI 39743172341, job `integration`; incident run on `cyclebeat-it`, 15 Oct) | — |
| Public deployment | Deployment (2) | 10. Deployment (2) | both | API and web on Render, deployed by CI from `main` | DECLARED here (README URLs); EXECUTED by the grading audit of 16 Oct (`docs/audit/grading-audit-2026-10-16.md`) | — |
| CI/CD | CI/CD (3) | 11. CI/CD Pipeline (2) | both | CI on every push and pull request; CD deploys to production automatically after green CI on `main` (`ci.yml`, job `deploy`, environment `production`) | OBSERVED (`ci.yml`); EXECUTED for CI (39743172341) | official level 3: CD to a dev environment and a **manual** deploy to production |
| Observability: metrics, traces and structured logs sharing a trace ID, in a UI | Observability (2) | — | official | Prometheus metrics on `/metrics`; Prometheus and Grafana in the compose `monitoring` profile; no tracing library (no OpenTelemetry in `pyproject.toml`) | OBSERVED | traces, structured logs, a shared trace ID |
| An alert on user impact | Alerting on User Impact (1) | — | official | no alert rule in `monitoring/` (grep for `alert`, `rule_files`: empty, 22 Oct) | ABSENT | one alert |
| An on-call agent woken by an alert that fixes the issue | On-Call Agent (2) | — | official | none; `ops/` holds a reproduced incident and its diagnosis, done by hand | ABSENT | the agent |
| Agent extension pack | — | 12. Agent Extension Pack (2) | old | instructions, skill, four subagents, MCP server, PreToolUse hook, permission notes, plugin (`docs/agent-extension-pack.md`); tests in CI | EXECUTED (CI 39743172341: `test_extension_pack_layout.py`, `test_agent_hook.py`, `test_mcp_server.py`) | — |
| Security, audit and DevOps artifacts | — | 13. Security, Audit, and DevOps Hardening (2) | old | the five artifacts under `security/` and `ops/` (PR #42); Semgrep and gitleaks blocking in CI | EXECUTED (CI 39743172341, job `security`: 0 findings, no leaks in 165 commits) | — |
| Reproducibility from a clean clone | (Application: "runs locally with a single command") | 14. Reproducibility (2) | both | `CONTRIBUTING.md`, `README.md`; a cold clone was run end to end by the grading audit of 16 Oct | EXECUTED by the audit of 16 Oct, not re-run since | — |

**Maxima, per grid, not added:** official grid 24 points (10 to pass); old grid 30 points.
