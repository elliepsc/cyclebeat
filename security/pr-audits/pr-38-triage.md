# Triage — audits of PR #38 (phase 7, agent extension pack)

Written by the main agent, not by the auditor. The raw report is [pr-38.md](pr-38.md) (new
definition, 15 October 2026). An earlier pass ran on 13 October 2026 on the OLD definition
(the one that held Write and wrote to `docs/security/`); its output was not committed because it
stopped on a hook refusal (`git log --all -- .env`, now an owner action: result "no line",
13 October 2026). Its findings H1 to H4 are carried here, marked "pass 1 (old definition)",
because the owner asked for them to be attached to their fix.

Verdicts: **fixed** (PR, commit), **patch pending** (the hook patch
[pr-38-hook.patch](pr-38-hook.patch), which only the owner applies: `agent-hooks/` is hers),
**accepted** (reason) or **recorded** (where).

## Pass on the new definition ([pr-38.md](pr-38.md))

| Finding | Verdict | Reference |
|---|---|---|
| C1 (critical) — `LATERAL sniff_csv(...)` passed the guard; DuckDB 0.10.2 lets `sniff_csv` read a file (CVE-2024-41672): the first line of any file the MCP server could read, `.env` included | **Fixed in the guard** — PR #41, f7d651d (only named tables, subqueries and VALUES as sources; table-function names refused anywhere). **Recorded** for the engine: ROADMAP `[présentable]`, first line (DuckDB upgrade); two `xfail(strict)` tests. The exposure window (PR #38 merge to PR #41 merge) is described in [agent-security.md](../agent-security.md#exposure-window-pr-38-to-pr-41) with a line for the owner's decision | |
| H1 — a CTE name whitelisted a real table from any scope | **Fixed** — PR #41, 4ac9ed8 (per-scope check), then 2980b7f (exposure database: tables off the allowlist do not exist where the SQL runs) | |
| H2 — deletions the hook did not stop: `git clean -fdx/-fdX`, `rm -rf` on a glob or braces, `find . -delete`; `rm -rf *` refused only by accident at PR #38, allowed since aee9512 | **Patch pending** — `git clean` (every form), recursive `rm` on a pattern, `find -delete/-exec` from a start path containing `data/`/`lake/`; 11 refused cases in the patch's tests. `git stash -u`: **recorded** in [agent-security.md](../agent-security.md#what-the-guardrails-do-not-stop) | patch measured: all 32 new refused cases passed the hook at HEAD |
| M1 — catalogue / settings functions and unbounded builders | **Fixed** — PR #41, 4ac9ed8, 2d2f008, feae0a7 | |
| M2 — secret reads through `grep -r`, `rg -uu`, `tar`, braces, `$'.env'`, the Grep tool's `glob` | **Patch pending** for the textual rule (recursive search or archive of the repo root, a parent or `~`, unless `.env*` is excluded) and for braces. **Recorded**: `$'...'` quoting and the Grep tool's `glob` parameter, in [agent-security.md](../agent-security.md#what-the-guardrails-do-not-stop) | owner decision: purely textual rule, no file lookup |
| M3 — `gh api` routes to a merge, a PR or `main` | **Patch pending** — GraphQL `mergePullRequest` / `createPullRequest` / `createCommitOnBranch`, `POST .../pulls` (explicit or implied by `-f`), `PUT`/`DELETE .../contents/...` on `main`. Branch protection on `main`: unverified, owner setting | |
| L1 — machine paths in tool errors | **Fixed** — PR #41, f7d651d, feae0a7 | |
| L2 — external strings (`title`, `artist`, `preview_url`) reach the agent unlabelled | **Recorded**, not fixed (owner decision) — [agent-security.md](../agent-security.md#prompt-injection-through-the-data) | |
| L3 — `.mcp.json` and `Makefile` editable by the agent | **Recorded**, not fixed (owner decision) — [agent-security.md](../agent-security.md#what-the-guardrails-do-not-stop) | |
| L4 — security-auditor shipped with Write | **Fixed** — a8d9830 (phase-10, ported as 263ccb9 in PR #41) | |
| Info — `git show HEAD:.env` passes the hook | **Recorded**, not fixed (owner decision): no effect while `.env` was never tracked (owner check, 13 October 2026) | |
| Unable to verify — exploitation during the window; branch protection; Grep tool and deny rules; permission mode | **Recorded** in [agent-security.md](../agent-security.md) | |

## Pass 1 (old definition, 13 October 2026, not committed)

| Finding | Verdict | Reference |
|---|---|---|
| H1 — allowlist bypass through a nested CTE name | **Fixed** — PR #41, 4ac9ed8 (then 2980b7f) | same as H1 above |
| H2 — the hook did not re-parse `bash -c`, `sh -c`, `eval` | **Patch pending** — the script of `bash`/`sh`/`zsh`/`dash`/`ksh -c` and of `eval` goes through the same rules, nesting capped at 3; 5 refused cases | |
| H3 — destructive commands that never name `data/`/`lake/` (`git clean -fdx`, `rm -rf` of a parent, `rm -rf ./*`) | **Patch pending** — as H2 of the new pass. A recursive `rm` of a parent folder named literally (no pattern) is **recorded** as remaining in [agent-security.md](../agent-security.md#what-the-guardrails-do-not-stop) | |
| H4 — secret reads through brace expansion, recursive grep, `find -name` / `--include` fnmatch, the Grep tool's `glob` | **Patch pending** for braces and recursive search; **recorded** for `find -name`/`--include` patterns and the Grep tool's `glob` | |
| M1 (pass 1) — GitHub routes to a merge or a force-move of `main`: `gh api graphql`, `PATCH .../git/refs/heads/main`, `curl` to the merge API, `git -c push.default`, `git pull` on `main` | **Patch pending** for GraphQL; **recorded** for `PATCH git/refs`, `curl`, `push.default` and `git pull` on `main` | |
| M2 (pass 1) — prompt injection through mart rows | **Recorded** — as L2 above | |
| M3 (pass 1) — hook parsing gaps (`pushd`, dbt global options, `${D}ta`, `git apply`, `git restore .claude`) | **Recorded** in [agent-security.md](../agent-security.md#what-the-guardrails-do-not-stop) | |
| L1 (pass 1) — no memory or thread limit on the locked engine | **Fixed** — PR #41, 2980b7f (`memory_limit` on the exposure database); process-level limit **recorded** in ROADMAP | |
| L2 (pass 1) — `build_plugin` follows symlinks | **Recorded** | |
| L3 (pass 1) — subagents with Bash described as read-only | **Accepted** — read-only by instruction and by the hook, not by construction; stated in [agent-security.md](../agent-security.md#subagents) | |
| L4 (pass 1) — deny rules are prefix-only | **Recorded**, with the new false positive of 20 October 2026 (a `cp` whose SOURCE is in `agent-hooks/` refused as a write) | |
| L5 (pass 1) — a refusal was once worked around | **Accepted** — the rule "a refusal is a stop" is in CLAUDE.md since e02666f, and was applied twice during phase 10 | |
