# agent-capabilities/ — what the coding agent is given (criterion 12)

This folder is the grading-layout entry point. Claude Code loads each capability from its own
location, so the source stays there and this page describes and links it; nothing here is a copy.
The full map of the six elements is [docs/agent-extension-pack.md](../docs/agent-extension-pack.md).

## Reusable workflow — the `new-mart` skill

**Role.** Adds a dbt mart end to end, the same way every time: model, `schema.yml` with grain and
tests, build on a scratch warehouse (never `data/`), `dbt-reviewer` review, and — only when asked —
the read endpoint contract-first with `contract-guardian`.
**When it is used.** Any request for a new mart, KPI table or analytical aggregate; Claude picks it
up from its description, or the user types `/new-mart`.
**Source.** [`.claude/skills/new-mart/SKILL.md`](../.claude/skills/new-mart/SKILL.md) (loaded by Claude
Code from `.claude/skills/`; also generated into the plugin, where it is
`/cyclebeat-agent-pack:new-mart`).
**Proof of use.** Invoked as `/cyclebeat-agent-pack:new-mart` in the owner's demo; its equality
test caught a real 0-vs-NULL difference and the agent restored the original expression
([docs/demo.md](../docs/demo.md), step 2).

## Project instructions — `CLAUDE.md` and `AGENTS.md`

**Role.** The rules every session starts from: truth sources, execution rules, prohibitions,
normative data contracts, known pitfalls. `AGENTS.md` is a pointer to `CLAUDE.md` for agents that
read that name, so there is one rule set.
**When it is used.** Loaded at the start of every Claude Code session in this repo.
**Source.** [`CLAUDE.md`](../CLAUDE.md), [`AGENTS.md`](../AGENTS.md).
**Proof of use.** Every session in [docs/ai-workflow.md](../docs/ai-workflow.md) ran under it; step 1
of the owner's demo ([docs/demo.md](../docs/demo.md)).

## The other elements

| Element | Where |
|---|---|
| Subagents, including the API specialist `contract-guardian` | [`.claude/agents/`](../.claude/agents/) |
| MCP server (read-only warehouse) | [`mcp-server/`](../mcp-server/README.md) |
| Hook and deny rules | [`agent-hooks/`](../agent-hooks/README.md), [`.claude/settings.json`](../.claude/settings.json) |
| Plugin packaging (generated) | [`plugins/cyclebeat-agent-pack/`](../plugins/cyclebeat-agent-pack/README.md) |
| Permission notes | [docs/permissions.md](../docs/permissions.md) |
