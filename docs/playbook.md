# Playbook — running a data project with a coding agent (lessons from CycleBeat)

> Version 1, October 24, 2026. Written from project steering conversations (data lead ↔ Ellie).
> This is NOT the exhaustive source: the CycleBeat repository is the source of truth (see §1).
> To be supplemented with the source-backed inventory the agent will produce from the repository (see §7).

## 1. Where to find the record of what was done

| Question | Where to look | Type of record |
|---|---|---|
| Which rules does the agent follow? | `CLAUDE.md` (+ the `AGENTS.md` pointer) | Rules, known pitfalls, guardrails |
| How does the human + agent team work? | `docs/agent-team.md` | Roles, triggers, hand-offs, reserved decisions |
| What did we do, session by session? | `docs/ai-workflow.md` | Log: prompt, iterations, human corrections, checks, lessons |
| Why this architectural choice? | `docs/adr/` | Structural decisions, never rewritten (dated notes) |
| What must the system do? | `product-spec.md` | FR/NFR requirements, criteria, status + evidence (PRs, tests) |
| What remains, and what did we decide along the way? | GitHub issues + their comments | Agent plans, relayed owner decisions |
| Who reviewed what? | `security/pr-audits/` | Raw review outputs + triage records |
| Where do we stand against the rubric? | `docs/quality-bar.md` | Requirement by requirement, level of evidence |
| Which checks block progress? | `Makefile`, `.github/workflows/ci.yml`, `agent-hooks/`, `.claude/settings.json` | Executable gates |
| The data lead's reasoning | The project's claude.ai conversations + its `claude/*.md` files | **Not in the repository** (see §6) |

Rule: a decision only exists if it is written in the repository or on an issue. A decision made
only in a conversation will be lost in three months.

## 2. Principles (what helped most)

1. **Record a fact after measuring it.** Keep observations / interpretations / assumptions / uncertainties separate.
2. **Test first, measure the failure.** A test that has never failed proves nothing (empty table, fixture without a forbidden case).
3. **One phase = one issue = one branch = one PR.** `main` changes only through a human merge.
4. **A refusal (hook, deny rule, classifier) = STOP and report.** Never work around it with an equivalent command.
5. **Commit raw outputs as soon as they return** (reviews, scans, incidents). The scratchpad is volatile.
6. **Never rewrite an accepted ADR**: add a dated note.
7. **A “Deviations” section is mandatory** in every agent report.
8. **Explicit stopping rules** for loops (e.g. 3 workarounds of the same kind → structural fix).
9. **Documentation never claims more than the code does**: verify any sentence about a guardrail against that guardrail's code.
10. **No silent scope expansion**: anything found along the way becomes an issue or a recorded caveat.

## 3. Setting up a new project (in this order)

1. A short `CLAUDE.md`: sources of truth, execution rules, prohibitions, guardrails, conventions, known pitfalls
   (one line per rule). `AGENTS.md` = a simple pointer.
2. Executable gates from day 1: `make lint`, `make typecheck`, `make test` (a single command that fails
   when a dependency is missing instead of skipping), plus domain-specific gates (`make dbt`, `make contract`, `make eval`).
3. CI: the same commands as locally, actions pinned by SHA, `main` protection (required checks).
4. Guardrails in code: a PreToolUse hook (protected data areas, secrets, human-only merges/PRs, deletions),
   deny rules, with **hook tests** (allowed cases ≥ refused cases).
5. Security: Semgrep + gitleaks in CI, images pinned by version and digest.
6. `product-spec.md` + public issues with an **issue template** (Context, Acceptance criteria, Out of scope,
   Requirements served, Definition of done) + milestones without dates.
7. `docs/agent-team.md`: actual roles (not ideal ones), review subagents (`.claude/agents/`).
8. `docs/ai-workflow.md` updated by a scribe subagent at the end of each PR.
9. `docs/quality-bar.md` if an external rubric grades the project (verbatim copy of the rubric + source).

## 4. The issue cycle

1. A new session for each issue: “Take issue #N. Follow the process in CLAUDE.md: read the issue, create your
   branch from an up-to-date origin/main, comment your plan on the issue, then STOP before coding.”
2. Review the plan (§5 checklist). Decisions → the agent copies them onto the issue
   (“Posted by the coding agent. Owner decisions relayed: …”).
3. Test-first coding; subagent reviews; raw outputs committed; triage.
4. DoD with exit codes checked (never `| tail` without pipefail, never chain `push` after a gate).
5. Push; the agent writes the PR description to a file (starting with `Closes #N`) and provides the
   `gh pr create … --body-file …` command; the human creates the PR, checks CI, merges, and checks that the issue closed.
6. An `ai-workflow.md` entry; proposed `CLAUDE.md` additions applied in the first commit of the next issue.

## 5. Review checklists (the data lead's role)

**Plan:** does it address the issue's real question? Facts re-verified against `origin/main`? Measurable criteria? A test
that will fail first? Stopping rules? Explicit exclusions from scope? What falls to the human (manual
actions, copies, Docker, secrets)? Will any test be meaningless on the available data?

**Report:** does every claim have a measurement? Were negative tests run? Is the “Deviations” section present and
honest? Raw outputs committed? Does the documentation claim more than the code does? What was found along the way,
and where is it recorded?

**Data (AE):** write the grain in one sentence before choosing the key; count = 0, mean/extremum/date = NULL on empty data;
never silently classify an unknown value; test input values, not just output values;
choose deduplication based on the source's behavior; prove every grain test can fail.

## 6. When to check in with the data lead (and how to record it)

**Check-in required:**

- The plan for a medium/high-risk issue (`autonomy:plan-gate`): data, security, deployment, guardrails;
- Any agent STOP (refusal, ambiguity, ambiguous grain, a figure contradicting the issue);
- A new ADR or a process/guardrail change;
- End of a milestone: a fresh audit against the rubric;
- Any sign of drift (plans piling up, an issue growing in scope).

**No check-in needed:** `autonomy:full` issues (documentation, finishing touches): reviewing the PR is enough.

**Record every check-in:**

1. Put the decision on the issue (comment relayed by the agent) → a public, dated record.
2. At the end of a check-in, ask the data lead: “summarize our decisions in 5 lines for issue #N”.
3. Whenever switching conversations: a `claude/HANDOFF_<project>_<date>.md` file in the claude.ai project.
4. Once per milestone: update this playbook (what helped, what did not).

## 7. Next step to make this playbook exhaustive

Create a CycleBeat issue titled “Extract the playbook from the repository” (approved plan): the agent inventories,
**from the files and git history**, every process, check, guardrail and template, with its source
(file, commit, PR) and rationale (the incident or lesson that prompted it, drawn from `ai-workflow.md`).
Deliverable: `docs/playbook.md` in the repository + a list of files to copy as-is into a new project
(templates) and those to rewrite (specific to CycleBeat). The data lead reviews before merge.
Do not build a generic “kit” beyond that: extract only what has proven useful here.
