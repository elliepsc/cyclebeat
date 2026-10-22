# Grading audit — CycleBeat, 16 October 2026

- **Audited reference:** `origin/main` = `7fd132a` (Merge PR #41), cloned cold from GitHub into a
  temporary directory. The local branch `phase-10/security-audit` is 4 commits ahead
  (`2cedef3`…`ce4b631`: `make audit`, `ops/`, Semgrep/gitleaks in CI). It is **not pushed**
  (`git ls-remote` returns nothing): a peer cannot see it, so it is not scored. It is mentioned
  wherever it would change a score.
- **Method:** read and run, no change to the project. Evidence levels: EXECUTED (command run, result
  seen), OBSERVED (file/config exists and matches, not run), DECLARED (only the docs say so), ABSENT.
  When in doubt, the lower level (the min score).
- **Auditor:** Claude Code (Opus 5.5), session of 16 October 2026.
- **Target (decided by the owner on 16 October 2026):** reach the top of **both** grids. The action
  plan below is a single combined plan.

## Summary

| Grid | Min score (strict peer) | Max score (lenient peer) | Pass mark |
|---|---|---|---|
| **V1** (14 criteria, the draft of 2026-10-09; **superseded on 2026-10-16**, now [archived](../archive/grading-criteria-v1-2026-10-09.md); provenance line updated 2026-10-22) | **27 / 30** | **29 / 30** | none shown |
| **V2** (12 criteria, **the official current grid**: course repository `project/README.md`, commits 3ef6f18 and 526d9c1 of 2026-10-16, copied verbatim in [docs/grading-criteria.md](../grading-criteria.md); provenance verified 2026-10-22) | **15 / 24** | **18 / 24** | 10 |

- **V1:** close to the ceiling; everything that must "work" was executed and passes. The points lost
  are criterion 13 (3 of its 5 artefacts are missing from `main`) and, at the margin, the README
  architecture (criterion 3) and browser proof of the frontend (criterion 4).
- **V2:** passes comfortably (15 ≥ 10 even at worst), but 6 points need new work (traces, alerting,
  on-call agent), and the public tracker does not exist (0 issues).

## V1 table

| # | Criterion | Points | Evidence level | Evidence | Missing for the next level |
|---|---|---|---|---|---|
| 1 | Problem Description | 2 / 2 | OBSERVED | `README.md`: "Why this project" (BPM problem, Spotify closed), system description, expected behaviour ("pick a level, a goal and a duration, and generate a session"), API table | Ceiling. Risk: the status banner is stale ("its public deployment is next"; Roadmap "6+ … planned" although phases 7 and 8 are merged). |
| 2 | AI-Assisted Development Workflow | 2 / 2 | OBSERVED | `docs/ai-workflow.md` (524 lines, 26 sessions): initial prompt, iterations, "Corrected by human review", measured verification; `CLAUDE.md`, `AGENTS.md`, `.claude/agents/` (4 subagents); raw audits in `security/pr-audits/` | Ceiling. |
| 3 | Technologies and System Architecture | **1 – 2** / 2 | OBSERVED | The README diagram covers Deezer → lake → DuckDB → dbt → planner → FastAPI. Frontend, Postgres, compose and CI/CD are described but **scattered** (compose services table, storage paragraph, one line "CI and deployment run in GitHub Actions") and **absent from the diagram** | One diagram: web (nginx/React) → API → Postgres + DuckDB, compose, CI → Render, plus a "how they fit together" paragraph. ~1 h. |
| 4 | Frontend Implementation | **2 – 3** / 3 | EXECUTED (HTTP, tests) / not exercised in a browser | `curl` web → 200, `<title>CycleBeat`; the served bundle contains `http://localhost:8000`; no `fetch`/`axios` outside `frontend/src/api/` (empty grep); client generated from `openapi.yaml`; `make front-test` → **4 files, 14 tests passed**; instructions in the README | For 3 at the min: proof of real use in a browser (screenshot or GIF; `docs/screenshots/` holds only `.gitkeep`). The auditor did not drive the UI. |
| 5 | API Contract | 2 / 2 | EXECUTED | Hand-written `openapi.yaml` (header: "This file is the contract, not a by-product"); `make contract` → **25 passed** (comparison with the FastAPI schema + schemathesis); front client regenerated and diffed in CI | Ceiling. |
| 6 | Backend Implementation | 3 / 3 | EXECUTED | `api/` routers → services → repositories; `make test-unit` → **663 passed, 15 skipped, 2 xfailed**; `make typecheck` → strict mypy clean (21 files); generate 200, feedback 201, replay 200 under compose | Ceiling. |
| 7 | Database Integration | 2 / 2 | EXECUTED | Postgres when `DATABASE_URL` is set (compose), SQLite otherwise (README, ADR-009); tables `sessions`, `feedback` read with `psql`; feedback row read back; CI step "Repository tests on Postgres" | Ceiling. |
| 8 | Containerization | 2 / 2 | EXECUTED | `docker compose up -d --build --wait` → 3 services `(healthy)` in 35 s (local layer cache reused) | Ceiling. |
| 9 | Integration Testing | 2 / 2 | EXECUTED | `tests/integration/` separate, excluded from `test-unit`, documented ("End-to-end tests"); `make test-integration` → **13 passed**, 45 s, stack torn down | Ceiling. |
| 10 | Deployment | 2 / 2 | EXECUTED (`curl -I`) + OBSERVED (CI log) | `curl -I https://cyclebeat-web.onrender.com/` → 200; `/docs` → 200; `deploy` job log of run 38748710556: both deploys `live` on `7fd132a`, `smoke generate: ok` | Ceiling. |
| 11 | CI/CD Pipeline | 2 / 2 | OBSERVED (GitHub runs) | `.github/workflows/ci.yml`: `build`, `frontend`, `integration`, then `deploy` (`needs` all three, main only); last main run: 4 jobs `success` | Ceiling. |
| 12 | Agent Extension Pack | 2 / 2 | EXECUTED (hook, MCP test) + OBSERVED | `docs/agent-extension-pack.md` maps the 6 elements; `docs/permissions.md`; the hook `agent-hooks/pre_tool_use.py` **blocked the auditor twice during this audit** (`make ingest`, then a command naming the secrets file); MCP stdio session covered by `test_mcp_server.py` (in the 663); plugin generated + drift check in CI | Ceiling. |
| 13 | Security, Audit, DevOps Hardening | **1** / 2 | OBSERVED | On `main`: PR audits (`security/pr-audits/`, 8 raw reports + triage) = 1 of the 5 artefacts. **ABSENT from main:** deterministic scan findings (no `security/scans/`; `make audit` on main = `echo "No audit target is defined yet." && exit 1`), dedicated agent security notes (`security/agent-security.md`), operational diagnosis (`ops/` only on the local branch), AI tool/data policy (`security/ai-policy.md`) | All 5 artefacts on `main`. See the plan. ROADMAP line `Critère 13`: ⬜. |
| 14 | Reproducibility | 2 / 2 | EXECUTED | Cold clone → `make setup` (0), `lint` (0 dead links), `typecheck`, `test-unit`, `eval` (55 passed), `contract`, `front-test`, `test-integration`, `docker compose up`: all exit 0. Deployment documented in `CONTRIBUTING.md` (deploy hooks, secrets, Blueprint) | Ceiling. Minor risk: `make dbt` not re-run by the auditor (see "What was executed"). |
| | **Total** | **27 – 29 / 30** | | | |

**Expected repository contents (not scored, but seen by a peer):** missing from `main`:
`product-spec.md`, `backend/` (the code is in `api/` and `cyclebeat/`, with no redirect README),
`ops/`. `custom-agent/` is not required (`plugins/` is present). The ROADMAP already lists this map
as ⬜.

## V2 table

| Criterion | Points | Evidence level | Evidence | Missing for the next level |
|---|---|---|---|---|
| Problem Description | 2 / 2 | OBSERVED | Same evidence as V1-1 | Ceiling. |
| Product Specification | **0 – 1** / 2 | OBSERVED / ABSENT | No `product-spec.md`. The only spec is `docs/archive/CYCLEBEAT_PLAN_V3.md`, in French, in a folder `CLAUDE.md` calls "history, not a source". **0 GitHub issues** (open or closed); no project board visible (token lacks the `read:project` scope, not verifiable). The repo is public. | 1: a short, real `product-spec.md`. 2: public issues with acceptance criteria, referenced in commits/PRs (`Closes #N`), closed by PRs, with traces that the agent read or commented on them. |
| Agent Team Specification | **1 – 2** / 2 | OBSERVED | 4 subagents with description and trigger (`CLAUDE.md` § Subagents: "dbt-reviewer — any PR touching dbt/"…); the real process is visible in the triage (`security/pr-audits/…-triage.md`: main agent → security-auditor + contract-guardian → owner triage). But no document describes **the team and its process** in one place | A `docs/agent-team.md`: roles, who triggers whom, hand-offs, what the human decides, linked from `CLAUDE.md`. |
| Context Management | 2 / 2 | OBSERVED | `AGENTS.md` → `CLAUDE.md`, which points to `docs/ROADMAP.md`, the ADR index, `docs/permissions.md`, `CONTRIBUTING.md` | Ceiling. Note: `AGENTS.md` itself describes nothing (pointer only); a very literal peer could notice. |
| Application | 2 / 2 | EXECUTED | One command (`docker compose up --build`); the web bundle targets the API; CORS returns `access-control-allow-origin: http://localhost:4173`; POST generate 200 → row in Postgres → API `--force-recreate` → replay 200, list `total: 1` | Ceiling. **Same evidence as Containerization** (see cross-check). |
| Testing | **1 – 2** / 2 | EXECUTED | Unit (663) and integration (13) tests exist and pass. But **no single command**: `make test-unit` and `make test-integration` are separate; no target runs both | A `make test` target that chains both. ~30 min. |
| Containerization | 2 / 2 | EXECUTED | Postgres included, one command, chained healthchecks | Ceiling. |
| Deployment | 2 / 2 | EXECUTED + OBSERVED | Same evidence as V1-10 | Ceiling. |
| CI/CD | 2 / 3 | OBSERVED | `pull_request` trigger present (`pull_request` runs exist, e.g. 38745238561); automatic CD to Render after green tests. **A single deployment environment** (`production`, branch rule; `main - cyclebeat-web` is the environment Render created, with no rule). No dev, no manual promotion | 3: automatic deploy to a dev environment, then a manual promotion to production (GitHub environment with a required reviewer, or `workflow_dispatch`). |
| Observability | 1 / 2 | EXECUTED | Prometheus metrics on `/metrics` (`http_requests_total` per route), scraped (`health: up`) in the `monitoring` profile; Grafana has the datasource but **its dashboards folder is empty**. Logs = plain-text uvicorn lines, **no JSON, no traces, no trace ID**. Nothing collected in production (Render). No customer data in metrics (templated routes); access logs carry the client IP and the `session_id` in the path | 2: all 6 conditions — one journey (generate) traced (OTel), metrics, JSON logs sharing the trace ID, no sensitive data, collection + storage + UI (e.g. Tempo/Loki/Grafana). |
| Alerting on User Impact | 0 / 1 | EXECUTED | Prometheus `GET /api/v1/rules` → `"groups":[]`; no `rule_files` | One alert rule (5xx rate or generate latency) loaded in the `monitoring` profile. |
| On-Call Agent | 0 / 2 | ABSENT | None. The ROADMAP files it under `[production]` ("read-only first-diagnosis agent"), and a diagnosis without a fix scores 0 | An agent woken by an alert that fixes the issue. In tension with the guardrails (no push to main, no Render calls). |
| | **Total** | **15 – 18 / 24** | | |

## Cross-check ("would a strict peer cloning cold grant it?")

- **Removed at the min:** V1-3 (incomplete diagram, scattered technologies), V1-4 (no browser
  proof; only HTTP + bundle + vitest were verified), V2 Product Specification (the only spec text is
  archived and in French), V2 Agent Team (no single description of the process), V2 Testing (no
  single command).
- **Kept despite doubt:** V1-10 / V2 Deployment (`curl -I` on `/health` returns 405 because the
  route is GET-only; GET calls to Render were then refused by the permission layer, so the
  functional production proof is the CI log `smoke generate: ok` of 15 October, not a request made
  today).
- **Shared evidence (do not count the effort twice):**
  - V2 Application and V2 Containerization rest on the **same** `docker compose up` run, as do V1-8
    and V1-14.
  - V1-10, V1-11, V2 Deployment and V2 CI/CD rest on the **same** run 38748710556.
  - V1-6, V1-9 and V2 Testing rest on the same suites.
  - V1-1 and V2 Problem Description: same README.
- **Fragile points:** `docs/PEER_REVIEW.md` on `main` awards itself "28/23" on the old grid
  (Qdrant, Streamlit, LangGraph); it is marked SUPERSEDED but sits at the top of `docs/` and can
  confuse a peer. The 2 `xfail(strict=True)` tests have no ticket (no issue), only a ROADMAP line;
  `CLAUDE.md` requires a ticket.

## What was executed

| Command (in the clone of `origin/main`) | Result |
|---|---|
| `git clone https://github.com/elliepsc/cyclebeat.git` | `7fd132a` |
| `docker compose -p cyclebeat-audit up -d --build --wait` | exit 0, 35 s, 3 services healthy (local layer cache reused: not a cold build time) |
| `curl http://localhost:4173/`; `GET /health` | 200; 200 `{"status":"ok"}` |
| `POST /v1/sessions/generate` (demo, intermediate, intervals, 45 min) | 200, 13 segments, CORS header for `localhost:4173` |
| `POST /v1/sessions/{id}/feedback` | 201; row read back with `psql` |
| `up -d --no-deps --force-recreate --wait api`, then `GET /v1/sessions/{id}` and `GET /v1/sessions` | 200; `total: 1` (the session survived the recreate) |
| `GET /metrics` | `http_requests_total` present |
| `--profile monitoring up -d prometheus grafana` (ports 9390/3300; local 3000 is taken by another project) | target `cyclebeat-api` `up`; rules: none; Grafana: Prometheus datasource, "CycleBeat" folder with no dashboard |
| `docker compose … down -v` | audit stack removed, 0 containers left |
| `make setup`, `lint`, `typecheck`, `test-unit`, `eval`, `contract` | all exit 0: 0 dead links; mypy OK (21 files); 663 passed / 15 skipped / 2 xfailed; 55 passed; 25 passed |
| `make front-test` | exit 0, 4 files, 14 tests passed |
| `make test-integration` | exit 0, 13 passed, 45 s, project `cyclebeat-it` torn down |
| `curl -I` web / `/health` / `/docs` (Render) | 200 / **405** (HEAD on a GET route) / 200 |
| `RUNTIME_DB_PATH=… make ingest` then `make dbt` | **not executed**: refused by the project hook ("make ingest writes lake/ and data/"), even in the clone. Not worked around. dbt remains proven by the CI `build` job (step "dbt build" green) and by the API image build, which builds the demo warehouse |
| `GET` on the Render API (`/health`, `/v1/quality/summary`) | **refused** by the permission layer (Render calls are forbidden by `CLAUDE.md`). Not retried |
| Check that the secrets file exists | **refused** by the hook. Observed only: `.gitignore` ignores it (line 12, `!.env.example` as the exception) and `git ls-files -ci --exclude-standard` is empty (no ignored file is tracked) |
| `gh repo view`, `gh issue list`, `gh pr list`, `gh run list`, environments | public; 0 issues; 41 PRs, all merged; latest runs green; environments `production` (branch rule) and `main - cyclebeat-web` |
| `gh project list` | **failed**: the token lacks the `read:project` scope |

## Combined action plan (freeze on 25 October 2026, 9 days)

Ranked by points gained (V1 + V2) per hour. Estimates are the auditor's, for the owner to correct.
Each action = one branch + one PR (project rules). Each PR from step 2 on starts from a public issue
with acceptance criteria and closes it (`Closes #N`): that is action G, run alongside everything else.

| Order | Action | V1 gain | V2 gain | Effort | Note |
|---|---|---|---|---|---|
| 1 | **A** — push `phase-10/security-audit`, open and merge the PR (owner's action) | prerequisite for C | — | 0.5 h | puts `ops/` and `make audit` on main |
| 2 | **G** — public issues with acceptance criteria for every action below, closed by their PRs | — | Product Spec +1 (with K) | 2–3 h, spread over the PRs | the agent reads the issue at the start of each PR |
| 3 | **D** — `make test` = `test-unit` + `test-integration` | — | Testing +1 (min) | 0.5 h | |
| 4 | **K** — short, real `product-spec.md` + redirect READMEs (`backend/` → `api/`, `cyclebeat/`) | expected contents complete | Product Spec +1 (min) | 1–1.5 h | already ⬜ in the ROADMAP |
| 5 | **B** — README: current status, one architecture diagram (web, Postgres, compose, CI → Render), a UI screenshot or GIF | crit. 3 +1, crit. 4 +1 (min) | secures Problem Description | 1.5–2 h | the screenshot needs the owner's browser |
| 6 | **E** — `docs/agent-team.md` (roles, triggers, hand-offs, human decisions), linked from `CLAUDE.md` | — | Agent Team +1 (min) | 1–1.5 h | |
| 7 | **C** — criterion 13: committed Semgrep report (`security/scans/`), `security/agent-security.md`, `security/ai-policy.md` | crit. 13 +1 | — | 4–6 h | the only V1 point still open at the max |
| 8 | **F** — one Prometheus alert rule (5xx rate or generate latency) in the `monitoring` profile, with a test | — | Alerting +1 | 1–2 h | needs an alert rule file, no new dependency |
| 9 | **H** — dev environment + manual promotion to production | — | CI/CD +1 | 3–5 h | two more Render services; free-tier limits **not verified** |
| 10 | **I** — OTel on generate + JSON logs with a trace ID + traces/logs viewable in Grafana | — | Observability +1 | 6–10 h | the ROADMAP excluded it explicitly (§2.8): needs the owner's decision; new dependencies to justify |
| 11 | **J** — on-call agent that fixes on alert | — | On-Call +2 | 8 h or more | design to decide (e.g. the agent opens a fix PR, the human merges); whether that counts as "fixes the issue" is an open question |

**Projected scores if every step lands:**

| Steps done | V1 (min – max) | V2 (min – max) |
|---|---|---|
| Today | 27 – 29 | 15 – 18 |
| 1 to 8 (~13–18 h) | 30 – 30 | 20 – 20 |
| + 9 (dev/prod) | 30 – 30 | 21 – 21 |
| + 10 (observability) | 30 – 30 | 22 – 22 |
| + 11 (on-call agent) | 30 – 30 | 24 – 24 |

These projections assume each action meets the wording of the criterion; they are re-measured after
each merge, not taken as given.

## Work that scores under one grid only

Kept so the plan can be trimmed if one grid becomes official:

- **V1 only:** criterion 13 (Semgrep, gitleaks, `ops/`, agent security notes, AI policy),
  criterion 3 (architecture), and the frontend "tests + instructions" level (V1-4 has 3 levels).
  V2 has **no security criterion**.
- **V2 only:** spec + public tracker, agent team, single test command, dev environment + manual
  promotion, full observability, alerting, on-call agent.
- **Already at the ceiling on its grid:** the extension pack (V1-12 at the max, absent from V2), MCP
  and the plugin. In V2 only `CLAUDE.md`/`AGENTS.md` counts, through Context Management.

## Manual checks for the owner

1. **Browser journey** on <http://localhost:4173> (compose) and <https://cyclebeat-web.onrender.com/>:
   generate, replay, rate a session. The auditor did not drive the UI; a committed screenshot or GIF
   removes the doubt on V1-4.
2. **Provenance of the V2 grid:** source and date not verified. Confirm it on the course page.
3. **V1 grid:** re-read the source before the freeze (draft, copy of 9 October).
4. **GitHub Projects:** not verifiable (no `read:project` scope). A board, if one exists, counts for
   V2 Product Specification.
5. **Local secrets file and git history:** the hook prevented the check; `make audit` (gitleaks over
   the whole history) exists on the local branch only.
6. **Production working today:** a demo `POST /v1/sessions/generate` on the Render API (Render calls
   are forbidden to the agent; the latest proof is the CI smoke test of 15 October).
7. **`make ingest` + `make dbt` from a clone:** refused by the hook for the agent; green in CI.
8. **The `production` environment:** check in GitHub whether an approval is required (the API only
   shows a branch rule) — relevant to action H.
