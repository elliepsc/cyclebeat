# AI workflow log

## Session 2026-07-29 — Phase 0 (close-out) — Land the purge and the orphaned ADR-004 commit on main, then publish the planning documents

**Loop**: spec (session brief) → context → re-verify the brief → plan → edit → run → test → diff → review → commit
**Tool/model**: Claude Code / Opus
**Initial prompt**: "Land phase 0 on main — the purge and the orphaned ADR-004 commit — via PRs, from an up-to-date base, losing no work." Out of scope stated up front: any V3 core construction.
**Notable iterations**:
- **The session brief was written against a stale state.** It described the purge PR as unmerged and asked for it to be opened; re-verifying against the remote showed it was already merged. Only step 2 (the orphaned ADR-004 commit) was genuinely outstanding. Re-verifying each stated fact before acting, rather than executing the brief top to bottom, is what caught it.
- **The brief's second premise was also false, not just imprecise.** It asked to apply edits "to the `origin/main` version of the plans, not the stale local copies". `git log --all -- <file>` returns 0 commits for all six files: they were never tracked, no `origin/main` version has ever existed, and the local copies are the only version there is. Reported as a false premise rather than silently reinterpreted as "edit the local files".
- PR #3 (`phase-0/purge` → `main`) opened and merged; both CI checks green before merge — this is the CI run the previous entry recorded as "not yet observed green on GitHub". `main` = `83b86d9`.
- PR #4 (`chore/agent-workflow-docs` → `main`) opened and merged, recovering commit `5d11038` (ADR-004 BPM resolution floor, the `docs/adr/README.md` index line, the README banner, 2 ai-workflow entries), which had been pushed *after* PR #2 was merged and was therefore invisible on `main`. `main` = `31d90a6`.
- The merge conflict was in this file, `docs/ai-workflow.md`, where both sides had appended an entry at the top. Resolved by keeping all four entries, newest first — none dropped, none reworded.
- `phase-0/purge` deleted locally and on origin, after `git rev-list --count origin/main..origin/phase-0/purge` returned 0.
**Escalated instead of decided** (E.0 "invent nothing"):
- **`CLAUDE.md` names `docs-notes/CYCLEBEAT_PLAN_V3.md` as truth-source #2, but `.gitignore` excluded it.** Anyone cloning the repo got the rules without the source they are derived from, and ADR-004 / `DECISIONS_SESSION_2026-07.md` cross-referenced files a reviewer could not open. Escalated to the owner with three options; the owner chose to commit the plans and the decisions log.
**Corrected by human review**: three decisions were the human's, not the agent's — merging PR #4 (rather than cherry-picking `5d11038`), committing the planning documents rather than leaving them ignored, and deleting the merged `phase-0/purge` branch.
**Caught during execution** (recorded because the grid asks what the loop actually caught):
- **Un-ignoring required restructuring `.gitignore`, not deleting a line.** Git cannot re-include a file whose parent directory is excluded, so `docs-notes/` became `docs-notes/*` plus explicit negations (`.gitignore:1-11`). Verified after the change that exactly 5 `docs-notes` files became visible and that `chatgpt.md`, `BACKLOG.md`, the fitflow notes, `HANDOFF` and `GIT_WORKFLOW.md` all stayed ignored.
- **Publishing was blocked by three unrelated causes, not one.** (a) CRLF worktree vs LF blobs again — Windows Git normalized and reported clean while WSL Git saw 21 files rewritten; (b) a stale git index that would not refresh on its own; (c) the real one — `gh` installed in WSL had registered an invalid token as a *URL-scoped* credential helper (`credential.https://github.com.helper`), which outranks the generic helper, so every push failed with "Invalid username or token" while the Windows credential store held a perfectly valid credential. Fixed by `.gitattributes` (`* text=auto eol=lf`), an index rebuild, and removing the `gh` helper entries so git reaches the Windows Credential Manager. Chasing (a) first cost time, because a plausible cause was found before the whole failure was characterized.
- **Secret hygiene re-run before committing the plans**: all six newly tracked files scanned for token/key patterns and credential-shaped assignments — clean.
**Role split**: decided by the human: merging PR #4, committing the planning documents rather than leaving them ignored, deleting the merged branch / delegated: the two merges, the `docs/ai-workflow.md` conflict resolution, the `.gitignore` restructuring, the credential and line-ending diagnosis, this entry.
**Verification**: `git cat-file -e origin/main:docs/adr/adr-004-bpm-resolution-floor.md` OK; `git merge-base --is-ancestor 5d11038 origin/main` yes; README banner present on `main`; `make lint` clean and `make test-unit` 19 passed on `main`; zero commits ahead of `main` on every remote branch.
**Lesson**: the agent's value here was almost entirely in verification, not production — the two facts it disproved (the purge PR was already merged, the plans had no `origin/main` version) would each have produced a wrong or wasted change if the brief had been executed as written. It lost time on the reverse failure mode: it stopped at the first plausible explanation for the push failure (line endings) instead of characterizing all three causes before fixing any.
**To capitalize in CLAUDE.md**: (1) "a task brief is a claim, not a fact — re-verify each stated state against the remote before acting" (the 2026-07-28 entry proposed "re-verify, don't remember" for *memory*; this session shows the same rule is needed for *instructions received*). (2) A truth-source file listed in CLAUDE.md must be tracked in git — an ignored truth source is a broken chain for anyone cloning the repo. (3) The publishing procedure (branch → push → PR → merge → sync, never `git push origin main`) currently lives only in the local, gitignored `docs-notes/GIT_WORKFLOW.md`; adding it to CLAUDE.md itself was offered to the owner and is **not yet done**.

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
## Session 2026-07-28 - Cross-cutting - Commit and push documentation updates

**Loop**: inspect working tree -> review Markdown-only diff -> add session log -> commit -> push
**Tool/model**: Codex
**Initial prompt**: "commit et push la mise à jour de fichier docs et md"
**Notable iterations**: confirmed the branch only had README/docs Markdown changes before staging; no code, SQL, OpenAPI, dependency, or secret-bearing file was touched.
**Corrected by human review**: none in this commit session.
**Role split**: agent committed and pushed the already prepared documentation updates; no subagent callable in this environment.
**Verification**: `git diff --check` before commit; post-push status clean.
**Lesson**: keep documentation-only commits scoped by explicit pathspecs so pending non-doc work cannot leak into the PR.
**To capitalize in CLAUDE.md**: nothing new.

## Session 2026-07-28 — Cross-cutting — Doc/decision sync after review audit

**Loop**: audit repo vs plan → identify doc gaps → decide → write ADR + decision note → cross-link
**Tool/model**: Cowork (Claude)
**Initial prompt**: "vérifie la notation de la grille, où est le RAG/orchestrateur/source musicale, puis assure-toi que tout est dans les fichiers — go et modifie"
**Notable iterations**: separated current-repo state (~13/30 on the target grid) from the plan's 30/30 projection; established that the double-ingestion debt and the Qdrant feedback-loop gap are mooted by the Phase-0 purge, and extracted the durable lessons instead (single-ingestion invariant, feedback→warehouse).
**Corrected by human review**: human ratified the librosa-floor reversal (backlog framing was preview-based) and asked to persist all decisions to files rather than leave them in chat.
**Role split**: written by the agent: `adr-004-bpm-resolution-floor.md`, `docs-notes/DECISIONS_SESSION_2026-07.md`, status banners on README/PEER_REVIEW, E.2 `fct_feedback` note, ADR index row / delegated: repo audit, web-verification of Spotify/Deezer/Jamendo/GetSongBPM API status (2026).
**Verification**: grep coverage matrix across README/CLAUDE/AGENTS/docs/docs-notes to confirm what was already documented before adding anything; API status cross-checked via web search (Spotify audio endpoints dead since 2024-11-27, no replacement 2026).
**Lesson**: doc drift is a grading risk in itself — README described v1 while code moved to Dash/V3; flag stale files with banners rather than silently trusting them.
**To capitalize in CLAUDE.md**: nothing new (E.0 "invent nothing / ask" already covered the ratification step).

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
