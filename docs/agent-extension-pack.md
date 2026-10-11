# Agent extension pack (criterion 12)

The six elements the grading asks for (`docs/grading-criteria.md:106`), where Claude Code loads
each one, where a reviewer finds it in the expected layout (`docs/grading-criteria.md:45-50`),
and the proof it has been used. Every file below has a single source; the grading-layout paths
either hold the real code or point to it.

| # | Element | Loaded by Claude Code from | Grading-layout path | Proof of use |
|---|---|---|---|---|
| 1 | Project instructions | [`CLAUDE.md`](../CLAUDE.md) (root); [`AGENTS.md`](../AGENTS.md) for other agents | — (root files) | read at the start of every session; [ai-workflow.md](ai-workflow.md) logs every session run under them |
| 2 | Reusable workflow | [`.claude/skills/new-mart/SKILL.md`](../.claude/skills/new-mart/SKILL.md) | [`agent-capabilities/`](../agent-capabilities/README.md) (description + link) | pending: step 2 of the owner's demo session |
| 3 | Subagent / specialist | [`.claude/agents/`](../.claude/agents/) — `contract-guardian`, `dbt-reviewer`, `security-auditor`, `ai-workflow-scribe` | — | `contract-guardian` reviewed the phase-5 contract change ([ai-workflow.md](ai-workflow.md), phase 5 entry: "contract-guardian suggestion") |
| 4 | MCP server | [`.mcp.json`](../.mcp.json) → [`mcp-server/cyclebeat_warehouse.py`](../mcp-server/cyclebeat_warehouse.py) | [`mcp-server/`](../mcp-server/README.md) (the real code) | a real stdio session in [`tests/unit/test_mcp_server.py`](../tests/unit/test_mcp_server.py) (CI) |
| 5 | Hook / guardrail | [`.claude/settings.json`](../.claude/settings.json) → [`agent-hooks/pre_tool_use.py`](../agent-hooks/pre_tool_use.py) | [`agent-hooks/`](../agent-hooks/README.md) (the real code) | blocked `gh pr merge 999999`, a write to `data/` and a read of `.env` in an auto-mode session on 2026-10-11 ([permissions.md](permissions.md#why-auto-mode-and-why-it-is-acceptable-here)) |
| 6 | Permission notes | — | [`docs/permissions.md`](permissions.md) | — |
| + | Plugin packaging (module 5: "light plugin or custom agent") | `claude --plugin-dir plugins/cyclebeat-agent-pack` | [`plugins/cyclebeat-agent-pack/`](../plugins/cyclebeat-agent-pack/README.md) (generated) | pending: the owner's `--plugin-dir` session |

## The plugin

[`plugins/cyclebeat-agent-pack/`](../plugins/cyclebeat-agent-pack/README.md) packages the skill,
the four subagents and the MCP server. It is **generated** by `make plugin`
([`tools/build_plugin.py`](../tools/build_plugin.py)) from `.claude/skills/`, `.claude/agents/` and
`.mcp.json`, committed like `frontend/src/api/schema.d.ts`, and CI fails if it differs from what
`make plugin` produces. One source per file: edit the source, regenerate.

- **What changes for whoever installs it**: names get the plugin prefix — the skill becomes
  `/cyclebeat-agent-pack:new-mart`, a subagent `cyclebeat-agent-pack:dbt-reviewer`, the MCP tools
  `mcp__plugin_cyclebeat-agent-pack_cyclebeat-warehouse__query_marts`
  (https://code.claude.com/docs/en/plugins/components). In this repo nothing changes: the
  project files are what loads.
- **The guardrails are not in it**: the deny rules and the hook stay in `.claude/settings.json`,
  which binds every session in this repo whether or not the plugin is installed, under the
  unprefixed names they were written for.
- **The MCP server is in it** because Claude Code substitutes `${CLAUDE_PROJECT_DIR}` in a
  plugin's MCP configuration: the documentation lists it among the path variables *"substituted
  in ... MCP and LSP server configurations"* ("Reference plugin paths and store data",
  https://code.claude.com/docs/en/plugins/components). The server still runs the code of the
  CycleBeat checkout, so the plugin works inside a clone of this repo only.
- `claude plugin validate plugins/cyclebeat-agent-pack` passes, with two warnings: no `version`
  and no `author` (both optional, left out rather than invented).

## Why the code sits where it does

- **Hook**: Claude Code needs the *declaration* in `.claude/settings.json`; the script can live
  anywhere. It lives in `agent-hooks/`, the grading path, and the settings point at it with
  `${CLAUDE_PROJECT_DIR}` (exec form, https://code.claude.com/docs/en/hooks).
- **MCP server**: `.mcp.json` has to be at the root; it points at `mcp-server/`. The guards it
  runs are in `api/` because CLAUDE.md only allows SQL in `api/repositories/` and `dbt/`, and
  because the phase-6 copilot will reuse them ([ADR-012](adr/adr-012-deterministic-tools-llm-separation.md)).
- **No `.agents/` folder**: the convention of a folder shared between several assistants, with
  symbolic links into `.claude/`, is not used, because only Claude Code works on this repo and
  symbolic links break on a Windows clone that does not enable them; `AGENTS.md` stays a plain
  pointer to `CLAUDE.md` instead.
