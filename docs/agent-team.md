# The agent team and how it works

This page describes how CycleBeat has actually been built: one human owner, one main coding agent
(Claude Code), and four review or writing subagents defined in [`.claude/agents/`](../.claude/agents/).
The rules themselves are in [CLAUDE.md](../CLAUDE.md). This page shows how those rules fit
together in practice and links to the traces each step leaves. It describes the process that has
been followed so far, not an ideal one. The session-by-session record is
[docs/ai-workflow.md](ai-workflow.md).

## Roles

| Role | Who | Triggered by | Can write | Produces |
|---|---|---|---|---|
| Owner | the human (repository owner) | — | everything, including what the agent is refused | decisions, approvals, the PRs, the merges, the hook patches |
| Main coding agent | Claude Code, following [CLAUDE.md](../CLAUDE.md) | an owner prompt naming an issue (since issue #44) or a roadmap phase (before it) | code, tests, docs on a work branch, within the [guardrails](permissions.md) | the plan comment, the commits, the pushed branch, the triage of review findings |
| [`contract-guardian`](../.claude/agents/contract-guardian.md) | subagent, read-only (Read, Grep, Glob, Bash) | a diff touching `openapi.yaml` or `api/` | nothing: it reports | a verdict (APPROVED / CHANGES REQUIRED) on contract-first discipline and the E.3 shapes |
| [`dbt-reviewer`](../.claude/agents/dbt-reviewer.md) | subagent, read-only (Read, Grep, Glob, Bash) | a diff touching `dbt/` or SQL | nothing: it reports | a review against the E.2 data contracts, the grain and the missing tests |
| [`security-auditor`](../.claude/agents/security-auditor.md) | subagent, read-only (Read, Grep, Glob, Bash) | a PR diff with a security surface (guardrails, tools, Makefile, CI), and the phase-10 audit | nothing: it returns its report as its final message | findings with file, line and a proposed fix, plus an "Unable to verify" section |
| [`ai-workflow-scribe`](../.claude/agents/ai-workflow-scribe.md) | subagent (Read, Edit, Write, Grep, Glob, Bash) | the end of each session or PR | `docs/ai-workflow.md` and `docs/specs/` only | the session entry, plus proposed `CLAUDE.md` lessons that the owner applies or not |

The three reviewers never fix anything. The main agent applies a fix or records why it did not,
and the owner arbitrates when the two disagree.

## The process, step by step

1. **Issue.** The owner names the issue. The main agent reads it with
   `gh issue view <N> --json title,body,comments` and re-checks each state the issue asserts
   against `origin/main`, with `git ls-files` for every file it names.
2. **Plan comment.** The agent posts its plan on the issue. The comment starts with "Posted by
   the coding agent (Claude Code)." and ends with the open questions. The agent then **stops**.
3. **Owner approval.** The owner approves or amends the plan and answers the questions. The agent
   relays those decisions in a second comment on the issue, starting with "Owner decisions
   relayed:", so the issue stays the full record.
4. **Branch.** It is cut from `origin/main` after a `git fetch`, never from local `main`. One
   issue or phase = one branch = one PR.
5. **Code and tests.** Each new behavior ships with its test in the same commit. Commits cite
   `#N`. The agent works through the definition of done in [CLAUDE.md](../CLAUDE.md): lint
   (including `check_links`), typecheck, `test-unit`, `eval`, `dbt`, `contract`. It reads each
   exit code directly, never through a pipe.
6. **Reviews.** The agent runs the subagents whose trigger the diff matches. Before it does, it
   checks that `.claude/agents/<name>.md` on the branch is the intended version. **The raw output
   is committed under [`security/pr-audits/`](../security/pr-audits/) as soon as it returns.** The
   agent's triage (one verdict per finding: fixed, patch pending, accepted, recorded) goes in a
   separate file next to it, for example
   [`pr-38-triage.md`](../security/pr-audits/pr-38-triage.md). A fix can trigger another pass
   (four passes on the `query_marts` fix branch).
7. **Workflow entry.** `ai-workflow-scribe` writes the session entry in
   [docs/ai-workflow.md](ai-workflow.md). It covers the objective, what worked, what the owner's
   review corrected, and who decided what.
8. **Push.** The agent pushes the work branch and reports the CI run. It stops there.
9. **PR and merge.** The owner opens the PR, which says `Closes #N` and ticks the acceptance
   criteria met. CI runs, and the owner merges. The merged PR closes the issue: no one closes it
   by hand.

## What only the owner decides or does

- Approving a plan and answering its open questions. A missing threshold or an ambiguous spec is
  a question for the owner, never a silent fill-in.
- Opening and merging PRs, and anything that lands on `main`. The hook refuses `gh pr create`,
  `gh pr merge`, pushes and merges to `main`, and force pushes.
- Closing or reopening issues. The hook refuses `gh issue close` and `gh issue edit --state`.
- **Changing the guardrails.** `agent-hooks/` and `.claude/settings*.json` belong to the owner.
  When a hook change is needed, the agent prepares a patch only, for example
  [`pr-38-hook.patch`](../security/pr-audits/pr-38-hook.patch), and **the owner applies it**,
  in an editor or a terminal outside the agent.
- Secrets (`.env`, keys) and deploys (Render): both are refused to the agent.
- Human actions in a phase (phases 1 and 9). The agent prepares and documents them, then stops.
  It never simulates the result.
- Scoping a review pass, and accepting a finding without fixing it.

## When the agent is refused

A refusal from the PreToolUse hook, a deny rule or the auto-mode classifier means **stop and
report**. That holds even for a suspected false positive. The agent does not retry with an
equivalent command. It reports the refusal and, where useful, proposes the fix to the owner. Two
real cases are recorded in [docs/ai-workflow.md](ai-workflow.md):

- `git add .claude` after `git add .claude/settings.json` was refused. That retry was a
  workaround, and the owner restated the rule.
- `cp agent-hooks/pre_tool_use.py <scratch>` was refused because the source path is protected.
  The owner made the copy.

The layers, and what each one enforces, are described in [docs/permissions.md](permissions.md).

## Where each trace lands

| Trace | Where |
|---|---|
| The plan, the owner's decisions, the open questions | comments on the GitHub issue |
| Raw subagent reviews and the agent's triage | [`security/pr-audits/`](../security/pr-audits/) |
| Scan reports (Semgrep, gitleaks) | [`security/scans/`](../security/scans/) |
| What was asked, what worked, what the owner corrected | [docs/ai-workflow.md](ai-workflow.md) |
| The measured gates and the acceptance criteria met | the PR description and its CI run |
| Lessons that became rules | [CLAUDE.md](../CLAUDE.md), applied by the owner |
