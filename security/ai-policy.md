# AI tool and data policy

Which AI tools work on this repository, what they may see, who reviews what, and the terms of
the data sources. A tool is listed as **used** only when [docs/ai-workflow.md](../docs/ai-workflow.md)
records a session with it; the line is cited.

## Tools

| Tool | Status | Evidence |
|---|---|---|
| Claude Code (CLI, auto mode), models Opus 5.5, Opus and Sonnet 5.5 | **used** — the main coding agent | `docs/ai-workflow.md`, "Tool/model" lines, e.g. l. 6, 28, 50 (Opus 5.5), 117 (Sonnet 5.5), 311 (Opus) |
| Claude Code subagents: `contract-guardian`, `dbt-reviewer`, `security-auditor`, `ai-workflow-scribe` | **used** — reviews and the session log | `security/pr-audits/` (raw reviews), `docs/ai-workflow.md` |
| Codex (GPT-5) | **used** — a few documentation sessions | `docs/ai-workflow.md` l. 481, 505, 517 |
| Cowork (Claude) | **used** — one session | `docs/ai-workflow.md` l. 493 |
| The project MCP server `cyclebeat-warehouse` | **used** — read-only tools for coding agents | `docs/demo.md`; ADR-012 |
| LiteLLM, Ollama | **planned** — the phase-6 LLM layer (demo and CI) | `CLAUDE.md`, Architecture; `docs/ROADMAP.md` `[présentable]` |
| Groq (`qwen/qwen3-32b`) | **planned** — the live LLM of the phase-6 layer | `CLAUDE.md`, Architecture. No session in `docs/ai-workflow.md` |

No paid AI service is part of the product (zero-cost rule, `CLAUDE.md`).

## Data an AI tool may and may not see

| Data | Allowed? | How it is enforced |
|---|---|---|
| Repository code, docs, tests, the committed demo snapshot | yes | — |
| `data/` and `lake/` (the real warehouse and lake) | **read only** (list, stat, hash, copy out); never written by an agent | PreToolUse hook; tests run on temporary copies |
| Secrets: `.env` and variants, private keys, `.netrc`, `.pgpass` | **never**, read or write | hook and deny rules; the `.env` history is an owner check |
| Audio | **never stored** | ADR-010: previews are analysed from a temporary file deleted in a `finally` |
| Production data and the Render account | **never** from an agent session | hook refuses the Render API and deploy hooks; deploys run in CI from `main` |
| MCP tool results (mart rows) | yes, as **data**: titles and artists come from Deezer / a user's CSV and are untrusted | `security/agent-security.md`, prompt injection |

## Human review

- **One phase = one branch + one PR.** The owner opens and merges every PR; the agent cannot
  (hook: `gh pr create/merge`, push and merge to `main` refused).
- **Reviewer subagents before merge**: `contract-guardian` on any diff touching `openapi.yaml`
  or `api/`, `dbt-reviewer` on `dbt/` and SQL, `security-auditor` for security work. Their raw
  output is committed unedited under `security/pr-audits/`, with the main agent's triage in a
  separate file.
- **Every session ends with an entry in `docs/ai-workflow.md`**: prompt, what worked, what human
  review corrected.
- **A guardrail refusal is a stop**: a refusal from the hook, a deny rule or the classifier is
  reported, never worked around, even when it looks like a false positive (`CLAUDE.md`).

## Auto mode and its guardrails

The agent runs in auto mode. Why that is acceptable here, and its three layers (deny rules, the
PreToolUse hook, the classifier), are in [docs/permissions.md](../docs/permissions.md); what they
do not stop is in [agent-security.md](agent-security.md#what-the-guardrails-do-not-stop).

## Data sources and their terms

| Source | Use | Terms (as recorded, with their URL) |
|---|---|---|
| Deezer API (track metadata, 30-second preview, `bpm`) | the BPM backbone | [ADR-010](../docs/adr/adr-010-track-and-bpm-sources.md): non-commercial use only; local or offline storage of audio is forbidden; automated analysis of the preview is **not clearly authorized** by the terms read (<https://developers.deezer.com/termsofuse>). The repository publishes derived values (BPM, confidence), never audio |
| Spotify, YouTube | track identity only, never BPM | ADR-010 |
| A user's CSV | the manual floor | ADR-005, ADR-010 |
