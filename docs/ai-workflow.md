# AI workflow log

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
