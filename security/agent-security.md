# Agent and extension security

The threat model of what a coding agent touches on CycleBeat: the MCP server and its read-only
tools, the PreToolUse hook, the deny rules, the subagents and the plugin. What each layer does,
the five bypasses found and fixed during phase 10, the exposure window they opened, and what
still gets through. What the agent may and may not do, and the minimum Claude Code version, are
in [docs/permissions.md](../docs/permissions.md); this page does not repeat them.

## Assets and the realistic attacker

| Asset | Where | Why it matters |
|---|---|---|
| Secrets | `.env` at the repo root (Groq, Render keys), never tracked (owner check: `git log --all --oneline -- .env` returns no line, 13 October 2026) | a key in a transcript leaves the machine |
| The real data | `data/`, `lake/` (gitignored) | the warehouse the demo serves |
| `main` and production | GitHub `main`, Render (deployed by CI from `main` only) | a merge or a push ships to users |
| The guardrails themselves | `agent-hooks/`, `.claude/settings*.json` | an agent that edits them loosens its own limits |

The attacker the guardrails are built for is **a mistaken or prompt-injected agent**, not a
person with a shell: the hook reads command text and says so. Two injection channels are real:
external strings in the data (Deezer and CSV titles, see
[below](#prompt-injection-through-the-data)) and any text the agent reads while working.

## The layers

| Layer | What it does | By construction or by instruction |
|---|---|---|
| MCP server `cyclebeat-warehouse` ([mcp-server/](../mcp-server/README.md)) | two tools, `query_marts` and `get_quality_report`, annotated read-only | **construction**: since PR #41 their SQL runs on an *exposure database*, in memory, holding copies of the four allowed marts only, path settings neutralised, then locked (`api/repositories/readonly_warehouse.py`, `exposed()`). The SQL guard (`api/services/warehouse_tools.py`) is the second line |
| PreToolUse hook (`agent-hooks/pre_tool_use.py`) | refuses writes to `data/`/`lake/`, secrets files, force push, push and merge to `main`, PR creation and merge, Render, edits to the guardrails | **instruction-level parsing of command text**; fails closed on its own errors |
| Deny rules (`.claude/settings.json`) | prefix rules on tools and commands | static prefixes ([permissions.md, Limits](../docs/permissions.md#limits--what-this-does-not-stop)) |
| Auto-mode classifier | refuses actions it judges risky | outside the repo; a refusal is a stop (CLAUDE.md) |
| Subagents | review only (see [Subagents](#subagents)) | **instruction**: they keep Bash |
| Plugin (`plugins/cyclebeat-agent-pack/`) | ships the skill, the four subagents and `.mcp.json`; NOT the hook or the settings | trusting the plugin means trusting the repo it runs from: its `.mcp.json` runs `mcp-server/` of the open project |

## The five bypasses found and fixed (PR #41)

Each was found by an audit pass, reproduced on a temporary warehouse, pinned by a test that
failed first, then fixed. The raw reports and their triage are in
[pr-audits/](pr-audits/fix-query-marts-cte-scope-triage.md).

| # | Bypass | What it reached | Fix |
|---|---|---|---|
| 1 | A CTE defined in a subquery whitelisted its name for the whole query | any table or view of the warehouse | 4ac9ed8 (per-scope check), then 2980b7f (exposure database) |
| 2 | Scalar catalogue functions (`pg_get_viewdef`, `current_setting`, ...) pass a table check | view definitions off the allowlist; the OS user's home path | 4ac9ed8, 2d2f008 |
| 3 | Python lowercases U+212A KELVIN SIGN to `k`, DuckDB does not: a CTE named `stg_tracKs` let the real `stg_tracks` through | tables whose name holds a `k` | 2d2f008 (ASCII-only identifiers) |
| 4 | sqlglot re-emits function names with Unicode `upper()`: `current_settıng` became `CURRENT_SETTING` after the check | the OS user's home path | 2980b7f (ASCII function names, the guard re-checks its own output) and the exposure database |
| 5 | `JOIN LATERAL sniff_csv('<file>')` is not a table node; DuckDB 0.10.2 lets `sniff_csv` read a file with external access off (CVE-2024-41672) | **the first line of any file the server can read** | f7d651d (only named tables, subqueries and VALUES as sources; table-function names refused anywhere) |

The same audits fixed three disclosures that read no data: DuckDB's lock error (path, executable,
PID) and an unreadable directory's `PermissionError` now give one fixed message, and unbounded
`range` / `generate_series` / `repeat` are refused (memory, not confidentiality).

## Exposure window, PR #38 to PR #41

| | |
|---|---|
| Window | `main` from the merge of PR #38 (ea7b054, 2026-10-12 16:08 +0200) to the merge of PR #41 (7fd132a, 2026-10-15 16:08 +0200): 72 hours. The vulnerable code existed earlier on the `phase-7/extension-pack` branch, from 9777af4 / 730e82f (2026-10-11 20:37 +0200), for any local session on that branch |
| Reach | through `query_marts` (MCP), the **first line** of any file the MCP server process could read: `.env` included, SSH keys included (bypass 5). Through bypass 1, any table of the warehouse |
| Who could trigger it | an agent session with the project MCP server approved (`.mcp.json`, one-time approval) or the plugin enabled |
| Evidence of use | **none either way**: MCP tool calls are not logged anywhere this project can read. The phase-7 demo used the server (`docs/demo.md`); no recorded query used `sniff_csv` or `LATERAL`, but absence of a log is not absence of use |
| Owner's decision on rotating the `.env` keys | **décision de la propriétaire : [à compléter]** |

## What remains

- **`sniff_csv` on DuckDB 0.10.2.** The engine still reads a file header on the locked
  connection and on the exposure database; only the guard stops it. Two `xfail(strict=True)`
  tests record it and turn red on the upgrade; the upgrade is the first `[présentable]` line of
  [docs/ROADMAP.md](../docs/ROADMAP.md).
- **A denylist of functions.** `_FORBIDDEN_FUNCTIONS` and the table-function names are read
  for DuckDB 0.10.2; a macro defined in the warehouse would not be copied into the exposure
  database, but a new built-in after an upgrade must be re-checked. An allowlist of functions is
  on the same roadmap line.
- **The auditor is read-only by instruction, not by construction.** `security-auditor` has no
  Write or Edit tool (`.claude/agents/security-auditor.md:4`), but it keeps Bash, which can write.
  What stops it is its own instructions and the PreToolUse hook. The same holds for
  `contract-guardian` and `dbt-reviewer` (see [Subagents](#subagents)).

## Prompt injection through the data

`dim_track.title`, `artist` and `preview_url` come from Deezer or a user's CSV and reach the agent
verbatim in `query_marts` rows. Neither the tool result nor the server instructions mark them as
untrusted (audit of PR #38, L2: a title `ignore previous instructions` came back as is). Today
every tool is read-only, so an injected instruction can only steer the agent's next actions,
which the hook and the classifier then judge. The phase-6 copilot adds `trigger_resolve`, a tool
that acts: labelling the fields as untrusted is to be decided with that phase. Recorded, not
fixed (owner decision, 20 October 2026).

## Subagents

| Subagent | Tools | Read-only? |
|---|---|---|
| `security-auditor` | Read, Grep, Glob, Bash | by instruction and the hook; Bash can write |
| `contract-guardian` | Read, Grep, Glob, Bash | same |
| `dbt-reviewer` | Read, Grep, Glob, Bash | same |
| `ai-workflow-scribe` | Read, Edit, Write, Grep, Glob, Bash | no: it writes `docs/ai-workflow.md` |

Two lessons of phase 10: a subagent's definition is read from the checked-out branch (a fix
branch cut before an agent update ran the old auditor, with Write, twice), and a reviewer's raw
output lives only in the session until it is committed (a machine shutdown lost a scratchpad).

## What the guardrails do not stop

Beyond the limits already listed in
[permissions.md](../docs/permissions.md#limits--what-this-does-not-stop) (a computed path in
`python -c`, aliases, a mod overriding a hook), the phase-10 audits recorded these, not fixed by
owner decision:

| Gap | Example | Note |
|---|---|---|
| ANSI-C quoting spells a secret | `cat $'.env'` | the token is not `.env` to the parser |
| The Grep tool's `glob` parameter | Grep with `glob: ".env"` | the hook reads `path` only; whether the `Read(.env)` deny rule covers it is not documented |
| `find -name` / `grep --include` patterns | `find . -name '*env' -exec cat {} +` | fnmatch without the leading-dot rule |
| `git show <rev>:.env` | `git show HEAD:.env` | no effect while `.env` was never tracked |
| `git stash -u` | stashes untracked files, `lake/` included | not a deletion, but it moves them |
| A recursive `rm` of a parent named literally | `rm -rf ~/projets/cyclebeat` | the patch refuses patterns, not a literal parent |
| GitHub routes outside `gh api` GraphQL / pulls / contents | `gh api -X PATCH .../git/refs/heads/main`, `curl` to the merge API, `git -c push.default=upstream push`, `git pull` on `main` | branch protection on `main` is the backstop; not verified |
| Parsing gaps | `pushd data && touch x`, `dbt --log-level debug build`, `D=da; touch ${D}ta/x`, `git apply`, `git restore --source=HEAD~3 .claude` | the hook tracks `cd` only, reads the first dbt word, does not expand variables |
| Files that run code | `.mcp.json` (the MCP command of the next session), `Makefile` (a target the hook trusts by name) | editable by the agent |
| `build_plugin` follows symlinks | a symlinked agent file packages a file from outside the repo | |
| Deny rules are prefixes | `git -c a=b push --force`; and the reverse: a `cp` whose SOURCE is in `agent-hooks/` was refused as a write (20 October 2026) | a known limit of deny rules on Bash; recorded, not fixed (owner decision) |
| MCP tool arguments | no hook rule refuses an MCP call by its arguments | the official hooks reference documents `tool_input` only for built-in tools (checked 13 and 20 October 2026, <https://code.claude.com/docs/en/hooks>); a rule waits for that to be documented |

The audit of PR #38 also found deletions and secret reads that the hook missed; the patch that
refuses them ([pr-audits/pr-38-hook.patch](pr-audits/pr-38-hook.patch)) is prepared and tested,
and is the owner's to apply (`agent-hooks/` is hers).

## Evidence

- Raw audits: [pr-audits/pr-38.md](pr-audits/pr-38.md) and the eight pre-merge reviews of PR #41
  under [pr-audits/](pr-audits/fix-query-marts-cte-scope-triage.md).
- Tests: `tests/unit/test_copilot_guards.py`, `tests/unit/test_exposure_warehouse.py`,
  `tests/unit/test_agent_hook.py`.
- Decisions: [ADR-012](../docs/adr/adr-012-deterministic-tools-llm-separation.md) and its
  dated notes.
