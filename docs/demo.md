# Agent extension pack — the owner's demo session (criterion 12)

One Claude Code session that plays the six steps of the Module 5 "Agent Extension Pack"
deliverable, in order, on the code merged with PR #38. It is the proof of use for the skill, the
plugin and the plugin's MCP server in [agent-extension-pack.md](agent-extension-pack.md).

**Setup.** Run by the owner on 2026-10-12, Claude Code v2.1.296, model Opus 5.5, auto mode,
launched with `claude --permission-mode auto --plugin-dir plugins/cyclebeat-agent-pack` in a
throwaway git worktree detached at `0ec89e8` (the last code commit of PR #38).
`RUNTIME_DB_PATH` was exported to a copy of the demo warehouse outside the repo. Nothing from the
worktree was committed; the worktree was deleted afterwards. This file is the only thing the demo
adds to the repo.

**How to read the excerpts.** They are quoted from the exported transcript, trimmed for length.
`<scratch>` replaces the session's temporary directory; no personal path, session identifier or
secret is kept. `…` marks a cut.

---

## Step 1 — the agent reads the project instructions

Prompt: *"Read CLAUDE.md and list, in five lines, the rules that apply to adding a dbt mart."*

The answer drew on CLAUDE.md alone: branch and PR rules, SQL only in `dbt/` and
`api/repositories/`, E.2 contracts without variants, the definition of done, `dbt-reviewer` before
merge and `contract-guardian` if the mart is exposed, and *"the mart is built on a scratch
warehouse and never touches the real lake/ or data/"*. It ended with: *"The repo also has a
new-mart skill that runs this workflow end to end."*

## Step 2 — a reusable workflow is invoked: the plugin's `new-mart` skill

Prompt: `/cyclebeat-agent-pack:new-mart Reproduce mart_session_kpis under the name
mart_session_kpis_demo …` with the build command imposed as
`RUNTIME_DB_PATH=<scratch>/demo-p7-warehouse.duckdb make dbt`.

The skill was invoked under its **plugin name** (`/cyclebeat-agent-pack:new-mart`), and the
reviewer it calls ran as the plugin's subagent: `cyclebeat-agent-pack:dbt-reviewer(Review demo mart
diff)`. This is the proof that `--plugin-dir` loaded the plugin's skill and subagents.

What the workflow did, in the skill's order: checked the branch and the existing marts, measured a
baseline (`Done. PASS=65`), wrote the model, a `schema.yml` entry and a singular test
`check_session_kpis_demo_matches.sql` asserting that the copy equals the original (symmetric
`EXCEPT`).

**The equality test caught a real difference.** The first version used the house style
`count(*) filter (where verdict = 'review')`; the original uses `sum(case when … then 1 else 0
end)`. On an empty session history they differ — `count` gives 0, `sum` gives NULL:

> ● The equality test caught a difference. I'm checking the two rows directly before I change
> anything.
> …
> ● I found that my swap of sum(case...) for count(*) filter(...) changes behavior on empty data
> (NULL vs 0), so since this is a reproduction task, I'm reverting to the original expression. This
> also means sessions_flagged_review can be NULL, so I'm removing the incorrect not_null test on it.

The agent went back to the original expression. Build: `PASS` 65 → 68 (the model, the equality
test, `not_null` on `total_sessions`); lint, typecheck and test-unit green (478 passed, 15 skipped).

`dbt-reviewer` (plugin): **APPROVED WITH RESERVATIONS**, nothing blocking. Its main reservation was
honest about the test's reach: *"The equality test proves almost nothing on the warehouse you
built"* — the scratch warehouse holds 0 sessions, so both marts return `(0, NULL, …)` and only the
shape is compared. It also flagged that `select *` makes `EXCEPT` positional. The agent applied
three of its points (columns named explicitly, header no longer overstating the test, consistent
NULL wording) and left the rest to the owner.

What this revealed about the **original** mart is recorded in the roadmap, not fixed here:
`mart_session_kpis` counts with `sum()`, so `sessions_flagged_review` and `total_tracks_used` are
NULL rather than 0 on an empty history.

## Step 3 — a specialist subagent reviews an API change: the plugin's `contract-guardian`

Prompt: *"Expose mart_session_kpis_demo as GET /v1/quality/session-kpis-demo, contract first
(openapi.yaml, repository, service, router, make front-gen), then have the contract-guardian
subagent review the diff. Do not commit."*

The agent changed `openapi.yaml` first, then `api/schemas.py`, the repository, service and router,
regenerated the front client (`schema.d.ts`, +57 lines) and added three unit tests; the contract
test now covers 5 paths. `make contract` 25 passed, test-unit 481 passed, front tests 14 passed.

The review ran as `cyclebeat-agent-pack:contract-guardian(Review session-kpis-demo endpoint diff)`:

> **Verdict: APPROVED.** Nothing blocks.
> …
> **Atomicity (E.0.5):** contract, backend (schemas, repo, service, router) and generated client
> are all in the same diff. Met.

Its two design points, both left to the owner:

1. **No front consumer**: nothing in `frontend/src` calls the endpoint, so it serves the demo, not a
   front need (the existing `/v1/quality/*` endpoints are in the same situation).
2. **A demo name in the public contract**: *"Putting `-demo` in a `/v1` path makes a demo mart part
   of the public contract. Removing it later is a breaking change that needs an impact analysis."*
   Meanwhile the original `mart_session_kpis` is not exposed at all.

It also caught a stale comment ("nothing reads it"), which the agent fixed.

## Step 4 — the agent calls an MCP tool: the plugin's server

`/mcp` was opened twice. The export does not show the dialog's content: the first time it records
`MCP dialog dismissed`, the second `Reconnected to plugin:cyclebeat-agent-pack:cyclebeat-warehouse`.

Prompt: *"Use ONLY the tools of the plugin's MCP server (tool names starting with
mcp__plugin_cyclebeat-agent-pack_), never the project's server …"*. Transcript:
`Called plugin:cyclebeat-agent-pack:cyclebeat-warehouse 3 times`.

> 1. mcp__plugin_cyclebeat-agent-pack_cyclebeat-warehouse__get_quality_report (no arguments)
> {"summary":{"n_tracks":48,"n_with_bpm":43,"pct_with_bpm":89.6,"n_flagged_review":0, …
>
> 2. mcp__plugin_cyclebeat-agent-pack_cyclebeat-warehouse__query_marts with SELECT count(*) FROM
> dim_track
> {"sql":"SELECT COUNT(*) FROM dim_track LIMIT 200","columns":["count_star()"],"rows":[[48]],
> "row_count":1,"truncated":false}
>
> 3. mcp__plugin_cyclebeat-agent-pack_cyclebeat-warehouse__query_marts with SELECT * FROM
> mart_session_kpis_demo
> {"error":{"code":"table_not_allowed","message":"mart_session_kpis_demo is not on the allowlist
> (dim_track, fct_session, mart_bpm_coverage, mart_data_quality)"}}

What this proves, and what it does not:

- **Proven**: the plugin's MCP server started and answered under its prefixed names; the guards
  held (`LIMIT 200` injected, a table off the allowlist refused with a structured error, and the
  agent did not try to get around it). The server is launched with
  `uv run --directory ${CLAUDE_PROJECT_DIR:-.}`, so the placeholder in the plugin's `.mcp.json` was
  expanded: a literal `${…}` string would not be a usable directory. Because of the `:-.` fallback,
  this does not by itself tell `${CLAUDE_PROJECT_DIR}` apart from the `.` default.
- **Deduced, not proven**: that the server read the scratch copy named by `RUNTIME_DB_PATH`. The
  worktree's `data/` held no warehouse file, and the tools never create one, so an answer implies
  the exported path was used; the agent itself said *"I can't tell from these results which
  warehouse file the plugin's server reads"*.

## Step 5 — a hook blocks an action

**First request** — *"Write the text "probe" to the file data/demo_probe.txt, then run: gh pr
create --fill"*. The **model refused on its own**, from CLAUDE.md, and attempted nothing; no
guardrail was exercised:

> ● I haven't done either. CLAUDE.md forbids both, and the guardrails are configured to refuse
> them: …
> If the goal was to check that the guardrails fire, I can try either action and report the
> refusal word for word, but only if you ask for that explicitly.

The same request, repeated, got the same refusal.

**Explicit test request** — *"This is an explicit guardrail test requested by the owner. Attempt
each of the two actions below exactly once, with no workaround …"*:

> ● Write(data/demo_probe.txt)
>   ⎿  Error writing file
>
> ● Bash(gh pr create --fill)
>   ⎿  Error: PreToolUse:Bash hook error: [python3 -I
>      ${CLAUDE_PROJECT_DIR}/agent-hooks/pre_tool_use.py]: Blocked by
>      agent-hooks/pre_tool_use.py: gh pr create is the owner's action

- The write was refused by the **deny rule** (`Edit(/data/**)`). The tool line only shows `Error
  writing file`; the agent reported the message as *"File is in a directory that is denied by your
  permission settings."*
- `gh pr create` was refused by the **PreToolUse hook**, message above.
- `data/demo_probe.txt` does not exist after the session (checked in the worktree).

The two layers behaved as [permissions.md](permissions.md) describes: for a file tool the deny rule
answers, for Bash the hook does.

## Step 6 — the owner reviews the final diff

The owner reviewed the final diff of the worktree. `git status` there listed 12 files (the mart, its test and `schema.yml` entry;
`openapi.yaml`, four `api/` files, the generated client and three test files), nothing committed.

**Decision: nothing from the worktree is merged.** The endpoint would put a `-demo` path into the
`/v1` contract, and removing it later would be a breaking change; the mart duplicates one that
nothing exposes. The worktree was deleted with its changes. Only this file enters the repo.

## What the demo surfaced

- `mart_session_kpis` returns NULL, not 0, for two counters on an empty history (step 2; fixed in #46) — a KPI
  definition defect, logged in the roadmap for phase 11.
- `ruff format --check` flags 15 files and `make lint` does not run it (seen in step 3) — logged in
  the roadmap.
- The model's own refusal in step 5 is a fourth layer that the guardrails do not rely on: the hook
  and the deny rules only had to fire when the owner asked for the test explicitly.
