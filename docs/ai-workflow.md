# AI workflow log

## Session 2026-07-28 — Phase 0 — Purge of the v1 bricks and CI skeleton (runbook E.1 #2, #3, #6)

**Loop**: spec (E.1) → context → plan → edit → run → test → diff → review → commit
**Tool/model**: Claude Code / Opus
**Initial prompt**: "Finish phase 0 (purge & setup) of the V3 plan — runbook E.1 steps #2 (secret hygiene), #3 (purge) and #6 (CI skeleton), on branch `phase-0/purge`." Out of scope stated up front: live music sources, BPM resolver, Airflow DAGs, `openapi.yaml`, React frontend, deployment.
**Notable iterations**:
- The runbook assumed the 2026-07-09 audit state, so several files it did not anticipate had to be reconciled after the deletions: `docker-compose.yml` (qdrant/app/dashboard services, ingest command, `env_file` dropped so a clean clone boots without `.env`), `Dockerfile`, `render.yaml`, `.env.example`, `Makefile`, and the known-pitfalls line in `CLAUDE.md`. The purge is not "delete four directories", it is "delete four directories and repair everything that pointed at them".
- E.1 #2 came back clean and stayed a no-op: `git ls-files | grep -iE "\.env|spotify"` returned only `.env.example` and `scripts/spotify_auth.py` (itself being deleted), `git log --all -- .env` was empty, no `.spotify_cache` on disk. No `git filter-repo`, no credential rotation. Recorded as verified rather than skipped.
- The purge deletes without shipping a replacement, so the guards were written in the same commit as the deletion: `tests/test_purge_guards.py` (AST scan of `api/`, `db/`, `ingest/` for forbidden imports + purged paths absent), `tests/test_api_contract.py`, `tests/test_ingest_pipeline.py`.
**Corrected by human review**: one item — the runbook/repo mismatch on the UI (below). It was escalated rather than guessed, and the owner's answer (delete `app/` now; repair the dead `Dockerfile`/`render.yaml` references rather than defer them) set the scope of the reconciliations.
**Caught by re-verification and by the new tests** (not by human review — recorded here because the grid asks what the loop actually caught):
- **The safety net was not actually on origin.** `archive/v1-llm-zoomcamp` was believed already pushed; `git ls-remote origin` showed only `main` and `chore/agent-workflow-docs`. Pushed before touching anything. An "already done" runbook item must be re-verified with the runbook's own verification command, never from memory.
- **Local `main` was 8 commits behind `origin/main`** (PR #2 already merged). The work branch was cut from `origin/main`, not from local `main`.
- **Runbook/repo mismatch on the UI**: E.1 says "delete `app/` Streamlit", but `app/` was Plotly Dash (~900 lines, decoupled, calling the API over HTTP). Escalated to the owner with two costed options instead of guessing; the owner chose deletion because the UI's main feature died with the orchestrator. Recorded in `docs/adr/adr-001-v3-repositioning.md` ("Execution notes — purge run on 2026-07-28", point 1).
- **Purging the embeddings stack broke `import dlt`**: dlt 0.5.4 imports `pkg_resources` at import time and had been silently receiving setuptools via torch. Caught by the new tests, not by lint. Fixed by declaring `setuptools>=70,<81` explicitly (`pyproject.toml:18-21`), justified in the pyproject comment and in ADR-001 point 4.
- **The guard tests defeated the phase exit criterion**: they carried the words "qdrant"/"spotipy" in their docstrings, so the exit grep was non-empty. Restructured so the application packages are literally clean and those names live only in `tests/test_purge_guards.py`, the file whose job is to assert their absence.
- **`make ingest` crashed on Windows**: emoji in the pipeline's print output against a cp1252 console. Non-ASCII output removed from `ingest/ingest_pipeline.py`.
- **Windows Git and WSL Git disagreed on whether the tree was dirty**, on the same checkout: `core.autocrlf=true` globally and no `.gitattributes`, so the worktree was CRLF while every blob is LF. Windows Git normalized and reported clean; WSL Git compared raw bytes and reported 21 files rewritten (`3176 insertions, 3176 deletions` — every line, one carriage return each), which blocked `git pull` and `git merge` in WSL. Diagnosed by hashing: `git hash-object` matched the index entry, so there were no real changes. Fixed by `core.autocrlf=false`, a full worktree rewrite from the index, and an index rebuild (the stat cache would not refresh). `.gitattributes` (`* text=auto eol=lf`) added so a fresh clone does not repeat it — the repo runs on Linux (ubuntu CI, Docker, `make` from WSL) and a CRLF `Makefile` breaks GNU make.
**Role split**: decided by the human: deleting `app/` (Dash) now rather than keeping it as an interim UI, and repairing the dead `Dockerfile`/`render.yaml` references inside phase 0 instead of deferring them to phase 9. The 501 was offered by the human as one of two options (501 or serve the demo) and the agent chose 501, because serving demo data for a *generate* call would simulate a result / delegated: the dependency graph audit, the removal + repair edits, the three guard test files, the CI workflow, the ADR execution notes.
**Verification**: `make lint` green. `make test-unit` 19 passed. `make ingest && make dbt` from an empty warehouse → PASS=23 ERROR=0. `docker compose config` valid. `python -c "import api.main"` OK. Exit-criterion grep `spotipy|qdrant|langgraph` over `api db ingest` empty. `uv lock` drops torch and 40+ transitive packages. CI (`.github/workflows/ci.yml`, lint + test-unit + ingest + dbt, `cancel-in-progress` for E.8 zero cost) is **not yet observed green on GitHub** — it runs on push.
**Spec/actual gaps (runbook E.1)**: #2 was a no-op (nothing to purge from history); #3 named the UI as Streamlit when it was Dash and did not list docker-compose / Dockerfile / render.yaml / .env.example among the files to repair; two dependency changes are additions rather than removals (`duckdb` declared explicitly, `setuptools` added). All four are written up in ADR-001 instead of being resolved silently.
**Lesson**: the agent was fast on the mechanical part (dependency graph, orphan detection, mass edits, guard tests) and the tests it wrote caught a break — `import dlt` — that lint would have missed. It lost time twice on state assumed rather than checked: a branch believed pushed that was local-only, and a local `main` believed current. Both were one command away.
**To capitalize in CLAUDE.md**: applied in this PR — "re-verify, don't remember" under the execution rules, and three pitfalls (dependency removal breaks import-time deps, guard tests are the only place forbidden names may appear, no non-ASCII in Makefile-run stdout). Subject to review like any other diff in the PR.

## Session 2026-07-27 — Cross-cutting phase — Commit of agent artifacts and ADRs

**Loop**: context → audit working tree → edit → diff → commit → push
**Tool/model**: Codex / GPT-5
**Initial prompt**: "commit and push"
**Notable iterations**: the repo was on `main` with untracked files; applied the project rule "no direct commit to main" by creating a dedicated branch before pushing.
**Corrected by human review**: files were already present in the working tree before intervention; no additional human correction in this session.
**Role split**: written by the human: agent artifacts, data-agents kit, bonus ADRs / delegated: Git verification, exclusion of `dbt/.user.yml`, log creation, commit and push.
**Verification**: regex secret scan on the added files; `dbt/.user.yml` identified as a local uncommitted file. `make lint` attempted, blocked because `make` is not available in the current Windows shell.
**Lesson**: even for a simple commit, checking local files avoids publishing a dbt user identifier.
**To capitalize in CLAUDE.md**: explicitly add `dbt/.user.yml` to the local files not to commit.

## Session 2026-07-27 — Phase 0 — Add normative Makefile targets

**Loop**: context → inspect project commands → edit → verify → commit → push
**Tool/model**: Codex / GPT-5
**Initial prompt**: "why not create a make then?"
**Notable iterations**: the previous commit session exposed that `make` was unavailable in PowerShell and the repo did not contain a `Makefile`; V3 Phase 0 explicitly requires one.
**Corrected by human review**: the human challenged the missing `Makefile` instead of accepting a blocked validation note.
**Role split**: written by the agent: Makefile and workflow log / delegated: command discovery and verification.
**Verification**: `python -m compileall api agents app db ingest evaluation scripts` passed. `dbt build --project-dir dbt --profiles-dir dbt` could not run because `dbt` is not available in the current shell; `make` itself also remains unavailable unless GNU Make is installed.
**Lesson**: when the project defines `make` as the DoD interface, absence of a Makefile is a repo gap; absence of the binary is an environment gap.
**To capitalize in CLAUDE.md**: nothing.
