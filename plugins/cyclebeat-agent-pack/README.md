# plugins/cyclebeat-agent-pack/ — GENERATED, do not edit

Built by `make plugin` from the sources Claude Code loads in this repo
(`.claude/skills/`, `.claude/agents/`, `.mcp.json`); CI fails if this folder differs from what
`make plugin` produces. Edit the sources, then run `make plugin`.

| In the plugin | Source | Name once installed |
|---|---|---|
| skill `new-mart` | `.claude/skills/new-mart/SKILL.md` | `/cyclebeat-agent-pack:new-mart` |
| subagent `ai-workflow-scribe` | `.claude/agents/ai-workflow-scribe.md` | `cyclebeat-agent-pack:ai-workflow-scribe` |
| subagent `contract-guardian` | `.claude/agents/contract-guardian.md` | `cyclebeat-agent-pack:contract-guardian` |
| subagent `dbt-reviewer` | `.claude/agents/dbt-reviewer.md` | `cyclebeat-agent-pack:dbt-reviewer` |
| subagent `security-auditor` | `.claude/agents/security-auditor.md` | `cyclebeat-agent-pack:security-auditor` |
| MCP server `cyclebeat-warehouse` | `.mcp.json` | `mcp__plugin_cyclebeat-agent-pack_cyclebeat-warehouse__<tool>` |

The MCP server runs the code of the CycleBeat checkout (`${CLAUDE_PROJECT_DIR}`), so the plugin
works inside a clone of this repo only. The guardrails (deny rules and the PreToolUse hook) are not
in the plugin: they stay in `.claude/settings.json`. Names are prefixed with the plugin name only
for whoever installs the plugin; see `docs/agent-extension-pack.md`.

Load it without installing: `claude --plugin-dir plugins/cyclebeat-agent-pack`.
