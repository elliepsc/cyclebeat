# Agent extension pack (criterion 12)

The six elements the grading asks for (`docs/grading-criteria.md:106`), where Claude Code loads
each one, where a reviewer finds it in the expected layout (`docs/grading-criteria.md:45-50`),
and the proof it has been used. Every file below has a single source; the grading-layout paths
either hold the real code or point to it.

| # | Element | Loaded by Claude Code from | Grading-layout path | Proof of use |
|---|---|---|---|---|
| 1 | Project instructions | [`CLAUDE.md`](../CLAUDE.md) (root); [`AGENTS.md`](../AGENTS.md) for other agents | — (root files) | read at the start of every session; [ai-workflow.md](ai-workflow.md) logs every session run under them |
| 2 | Reusable workflow | *to come in this branch* | `agent-capabilities/` | — |
| 3 | Subagent / specialist | [`.claude/agents/`](../.claude/agents/) — `contract-guardian`, `dbt-reviewer`, `security-auditor`, `ai-workflow-scribe` | — | `contract-guardian` reviewed the phase-5 contract change ([ai-workflow.md](ai-workflow.md), phase 5 entry: "contract-guardian suggestion") |
| 4 | MCP server | [`.mcp.json`](../.mcp.json) → [`mcp-server/cyclebeat_warehouse.py`](../mcp-server/cyclebeat_warehouse.py) | [`mcp-server/`](../mcp-server/README.md) (the real code) | a real stdio session in [`tests/unit/test_mcp_server.py`](../tests/unit/test_mcp_server.py) (CI) |
| 5 | Hook / guardrail | [`.claude/settings.json`](../.claude/settings.json) → [`agent-hooks/pre_tool_use.py`](../agent-hooks/pre_tool_use.py) | [`agent-hooks/`](../agent-hooks/README.md) (the real code) | blocked `gh pr merge 999999`, a write to `data/` and a read of `.env` in an auto-mode session on 2026-10-11 ([permissions.md](permissions.md#why-auto-mode-and-why-it-is-acceptable-here)) |
| 6 | Permission notes | — | [`docs/permissions.md`](permissions.md) | — |

## Why the code sits where it does

- **Hook**: Claude Code needs the *declaration* in `.claude/settings.json`; the script can live
  anywhere. It lives in `agent-hooks/`, the grading path, and the settings point at it with
  `${CLAUDE_PROJECT_DIR}` (exec form, https://code.claude.com/docs/en/hooks).
- **MCP server**: `.mcp.json` has to be at the root; it points at `mcp-server/`. The guards it
  runs are in `api/` because CLAUDE.md only allows SQL in `api/repositories/` and `dbt/`, and
  because the phase-6 copilot will reuse them ([ADR-012](adr/README.md)).
