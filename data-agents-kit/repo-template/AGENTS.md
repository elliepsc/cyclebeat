# AGENTS.md — Codex / other coding agents

The authoritative engineering guide for this repo is **`CLAUDE.md` at the repo
root**. Read it in full and follow it before any work. This file exists because
Codex reads `AGENTS.md`, not `CLAUDE.md` — keep it a pointer, do not fork the rules.

Non-negotiables (fallback summary if CLAUDE.md is unreachable):

1. Business definitions come ONLY from `.claude/skills/analytics-engineer/references/metrics.md`.
   Missing definition = ask, never invent.
2. Prod warehouse is read-only. Every change is a PR; a human merges. Never merge your own PR.
3. No destructive operations (DROP, DELETE without WHERE, TRUNCATE, --full-refresh
   on protected incrementals) without explicit human confirmation.
4. Every model change ships with tests (unique + not_null on the grain key minimum),
   documentation, and a declared downstream impact analysis.
5. Never weaken, delete, or hardcode around a failing test. A failing test is information.
6. State assumptions (grain, filters, timezone, period). Distinguish observed /
   interpreted / assumed / uncertain in every analysis.

Maintenance: if CLAUDE.md changes materially, update this summary in the same PR.
