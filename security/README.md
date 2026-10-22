# security/ — criterion 13 artifacts

The five artifacts the grid asks for, where they are, and what each rests on. The operational
diagnosis lives in [ops/](../ops/README.md), as the grid expects.

| Artifact (grid, criterion 13) | File | Evidence |
|---|---|---|
| PR audit output | [pr-audits/pr-38.md](pr-audits/pr-38.md) (PR #38, the agent extension pack) and its [triage](pr-audits/pr-38-triage.md); the eight pre-merge reviews of PR #41 and their [triage](pr-audits/fix-query-marts-cte-scope-triage.md) | raw `security-auditor` and `contract-guardian` reports, unedited, each under a header naming the diff and the agent definition |
| Deterministic security scan findings | [scans/2026-10-20.md](scans/2026-10-20.md) | Semgrep and gitleaks in CI (`make audit`, job `security`), pip-audit and npm audit; raw outputs in `scans/raw-2026-10-20/` |
| Agent / extension security notes | [agent-security.md](agent-security.md) | threat model of the MCP server, the hook, the deny rules, the subagents and the plugin; the five bypasses fixed in PR #41; the exposure window; what remains |
| Operational diagnosis | [ops/incident-2026-10-15-postgres-down.md](../ops/incident-2026-10-15-postgres-down.md) | reproduced on the `cyclebeat-it` compose project, raw log committed |
| AI tool / data policy | [ai-policy.md](ai-policy.md) | tools proven by `docs/ai-workflow.md`, data rules, human review, source terms |

Also here: [pr-audits/pr-38-hook.patch](pr-audits/pr-38-hook.patch), the hook patch that answers
the PR #38 audit (H2, M2, M3), prepared and tested by the agent and applied by the owner, since
`agent-hooks/` is hers.
