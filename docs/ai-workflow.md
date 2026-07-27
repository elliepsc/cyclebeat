# AI workflow log

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
