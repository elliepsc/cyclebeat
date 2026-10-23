# Triage — security-auditor review of the issue #45 branch

Written by the main agent, not by the auditor. The raw report is
[pr-45-security-auditor.md](pr-45-security-auditor.md) (23 October 2026, on `origin/main..9df6133`).

Verdicts: **fixed** (commit), **owner** (a guardrail change: `agent-hooks/` and
`.claude/settings*.json` belong to the owner), **recorded** (where).

| Finding | Verdict | Reference |
|---|---|---|
| M1 — `docs/agent-team.md` overstated the issue-state guardrail (`gh issue edit --state` does not exist on gh 2.45; `reopen`, `delete`, `transfer` and `gh api ... state=closed` pass the hook) | **Fixed** in the doc (M1a): the hook refuses `gh issue close` only, the rest is refused by instruction only; delete and transfer added to the owner-only list. **Owner** for the hook patch (M1b) and the issue row in `docs/permissions.md` (M1c): not done in this PR (out of scope, guardrail files) | this branch, the commit after 428336d |
| L1 — "read-only" and the scribe's write scope are instructions, not per-agent enforcement | **Fixed** in the doc: a sentence under the Roles table says so and points to `docs/permissions.md`. **Owner** for an optional `Edit(/.claude/agents/**)` deny rule | same commit |
| L2 — a parent `MAKEFLAGS` (e.g. `make -i`) leaked into the child make of the test | **Fixed** (L2a): `_make_test` drops `MAKEFLAGS`, `MFLAGS`, `MAKELEVEL`. Measured: `MAKEFLAGS=i` 2 failed before, 8 passed after. `make -i test` exiting 0 (L2b) is **recorded**, not guarded: `-i` is an explicit operator choice | same commit |
| L3 — README says every check runs in CI; `make test` itself does not | **Fixed**: the row says CI runs its two halves in separate jobs | same commit |
| Info — moving `main` through the refs API is not refused by the hook | **Recorded**: the server-side ruleset "main protection" is active (read by the auditor); bypass actors unverified, owner setting | — |
| Hook refusal during the audit (`git check-ignore -v .env`) | **Recorded**: not retried by the auditor; owner check | `docs/ai-workflow.md`, the issue #45 entry |
