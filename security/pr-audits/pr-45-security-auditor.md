# Security audit: `test/45-test-command-agent-team` (issue #45)

Reference: branch `test/45-test-command-agent-team` checked against `origin/main` (fetched). Diff covers commits 5c50786 and 9df6133, 8 files, +201/-3.

## Executive summary

- **Overall risk: Low.** The `make test` target and its unit test add no injection surface, nothing that leaks environment, and no path from the unit suite to Docker or the network. A failing suite always gives a non-zero exit, with one exception: an operator who passes `make -i` (L2).
- **One Medium:** `docs/agent-team.md:61` overstates the issue-state guardrail. `gh issue edit --state` is not a gh 2.45 flag. `gh issue reopen`, `delete`, `transfer` and `gh api ... issues/N -f state=closed` all get through the hook.
- **No secrets.** `make audit` exit 0: "no leaks found" over 175 commits, Semgrep 0 findings.
- **Action #1:** reword `docs/agent-team.md:61` in this PR. Optionally, the owner patches the hook.

## Findings

### Medium

**M1. `docs/agent-team.md` overstates the issue-state guardrail**
- **Where:** `docs/agent-team.md:61`, which says "Closing or reopening issues. The hook refuses `gh issue close` and `gh issue edit --state`."
- **Evidence:** `agent-hooks/pre_tool_use.py:375-382` refuses only two forms:
  - `action == "close"`
  - `action == "edit"` with `--state`

  On the installed gh 2.45.0, `gh issue edit --help` lists no `--state` flag. Its flags are add/remove assignee, label and project, plus body, body-file, milestone and title. So the second rule guards a flag that does not exist.

  `gh issue --help` lists `reopen`, `delete` and `transfer`, and none of them is matched. `_gh_rule` (`pre_tool_use.py:383-396`) checks only these `gh api` routes: merges, the GraphQL merge/PR/commit mutations, `POST .../pulls` and `PUT/DELETE .../contents`. So `gh api -X PATCH repos/elliepsc/cyclebeat/issues/45 -f state=closed` is not refused either.

  `docs/permissions.md`, which line 83 cites as the description of the layers, has no issue row at all in its "What the agent may not do" table.
- **Impact:** The page reads as if the hook enforces "closing or reopening issues". In practice:
  - Reopening is enforced only by instruction and the auto-mode classifier.
  - Closing through the API is enforced the same way.
  - `gh issue delete` is irreversible and is not listed as owner-only.

  A reader, or a grader, would conclude the protection is stronger than it is.
- **Fix:**
  - **(a) In this PR:** reword the doc. Suggested text: "The hook refuses `gh issue close`. Reopening, deleting or transferring an issue, and changing its state through `gh api`, are refused by instruction only." Also add `gh issue delete` and `gh issue transfer` to the owner-only list.
  - **(b) Owner patch, outside the agent:** in `_gh_rule`, refuse `action in ("close", "reopen", "delete", "transfer")`. For `gh api`, refuse a non-GET call on `/issues/\d+$` that carries a `state` field. Keep or drop the `--state` branch after checking the current gh manual: https://cli.github.com/manual/gh_issue_edit
  - **(c)** Add the issue row to the `docs/permissions.md` table.
- **Effort:** (a) 5 min, quick win. (b) about 30 min plus tests in the hook's test file.

### Low

**L1. "Read-only" and "Can write" in the Roles table are instructions, not enforcement**
- **Where:** `docs/agent-team.md:16-19`:
  - the three reviewers are listed as "read-only (Read, Grep, Glob, Bash)" with "Can write: nothing"
  - `ai-workflow-scribe` is listed as "`docs/ai-workflow.md` and `docs/specs/` only"
- **Evidence:**
  - The front matter of `.claude/agents/*.md` gives each reviewer `Bash`, which can write files. It gives the scribe `Edit, Write`, with no path restriction.
  - The hook does not know which agent is calling: `grep -n "agent_type\|subagent" agent-hooks/pre_tool_use.py` returns nothing. It applies the same repo-wide rules to every agent (`data/`, `lake/`, secrets, `agent-hooks/`, settings).
  - `.claude/agents/*.md` itself is protected by neither the deny rules nor the hook (`_write_refusal`, `pre_tool_use.py:197-205`), so the main agent can edit a subagent's tool list.
- **Impact:** The doc presents a write boundary that rests on the subagent prompts, not on code. This matches the "a doc that overstates protection" criterion, but the impact is low because the repo-wide hook still covers the sensitive zones.
- **Fix:** Add a sentence under the table: "Read-only and the scribe's write scope are set by each subagent's instructions; the code-enforced limits are the repo-wide ones in [permissions.md](permissions.md), which apply to every agent alike." Optionally, the owner adds `Edit(/.claude/agents/**)` to the deny rules.
- **Effort:** 5 min, quick win.

**L2. `make -i test` exits 0 and prints "passed" when both suites fail, and the new test inherits the parent's `MAKEFLAGS`**
- **Where:** `Makefile:77-79`, and `tests/unit/test_agent_team_layout.py:20-23`, where `subprocess.run` gets no `env=` argument.
- **Evidence, reproduced with harmless overrides:**
  - `make -i --no-print-directory test RUN=false IT_COMPOSE=true` printed `make[1]: [Makefile:38: test-unit] Error 1 (ignored)`, then `[Makefile:58: test-integration] Error 1 (ignored)`, then `make test: unit and integration suites passed`, and exited 0.
  - `MAKEFLAGS=i uv run pytest -q tests/unit/test_agent_team_layout.py` made `test_make_test_fails_when_the_integration_suite_fails` fail with returncode 0. The child make picked up `-i` from the environment.
- **Impact:**
  - `-i` is a flag the operator chooses explicitly, so this is not a silent default. But the green message is then false.
  - The test is not hermetic: run under `make -i`, or under any `MAKEFLAGS` carrying `-i`, it fails. The failure is loud, not silent and not dangerous.
  - Without `-i`, the exit codes are correct in every case (see "Checked, no finding").
- **Fix:**
  - **(a)** In `_make_test`, pass `env={k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL")}`.
  - **(b) Optional:** in the `test` recipe, refuse `-i`, for example with `$(if $(findstring i,$(firstword -$(MAKEFLAGS))),$(error make test does not run with -i))`.
- **Effort:** 10 min. (a) is a quick win.

**L3. README says every listed check runs in CI, but `make test` itself never does**
- **Where:** `README.md:78` ("Every check below runs in CI on every push"), above the new `make test` row.
- **Evidence:** `.github/workflows/ci.yml:75` runs `make test-unit` and `ci.yml:176` runs `make test-integration`, in separate jobs. No workflow line runs `make test`.
- **Impact:** A minor accuracy issue. CI runs both halves, but not the command the row names.
- **Fix:** Add to the row: "CI runs its two halves in separate jobs (`make test-unit`, `make test-integration`)."
- **Effort:** 2 min, quick win.

### Informational (no action required by this PR)

- **Moving `main` through the refs API is not refused by the hook.** Doc line 59 says "anything that lands on `main`" is owner-only. `gh api -X PATCH repos/.../git/refs/heads/main` matches no hook rule. This is mitigated on the server side, read with GET only:
  - `gh api repos/elliepsc/cyclebeat/rules/branches/main` returns `["deletion","non_fast_forward","pull_request","required_status_checks"]`.
  - The ruleset is "main protection", `enforcement: active`.
  - Bypass actors were not read (see "Unable to verify").

## Checked, no finding

**(1) Injection, environment leak, Docker or network from the unit suite**
- `subprocess.run` takes a list of arguments, with no `shell=True`, `timeout=60` and `check=False` (`test_agent_team_layout.py:21-23`). The override values are literals in the test (`true`, `false`, `echo INTEGRATION-STARTED`), not external input.
- Every Docker call in `test-integration` goes through `IT_COMPOSE` (`Makefile:54`, the only `docker` in the recipe). Every pytest call goes through `RUN`. Both are overridden in all three subprocess tests. GNU make passes command-line variables to the `$(MAKE)` sub-makes through `MAKEFLAGS`.
- The suite ran 8 passed in 0.09 s, which is consistent with no Docker and no real pytest recursion. Command: `uv run pytest tests/unit/test_agent_team_layout.py -v`, exit 0, read through `PIPESTATUS`.
- The new recipe adds no `export` and no new variable.

**(2) A suite failure giving exit 0, or a silent integration skip**
- The recipe is sequential, with no prerequisites, so `make -j` cannot run the suites in parallel. `test_make_test_runs_the_suites_in_order_not_as_prerequisites` asserts this.
- Each line ends in `|| { ...; exit 1; }`, which make reports as exit 2. This matches the "exit 2" in `docs/quality-bar.md`.
- `test-integration` keeps the status of `up` and of pytest in `rc` and ends with `exit $$rc` (`Makefile:58-71`). With Docker missing, `up` fails and so does the target.
- `tests/integration/conftest.py:12-13,36,50` fails rather than skips when the stack is absent. `grep -rn "skip\|xfail\|importorskip" tests/integration/` shows only those docstrings. With no tests collected, pytest exits 5, which is also non-zero.
- The only exception is `-i` (L2).

**(4) Secrets**
- `make audit` exit 0:
  - Semgrep report pass: "Ran 243 rules on 91 files: 0 findings".
  - Semgrep gate on ERROR: "Ran 89 rules on 91 files: 0 findings".
  - gitleaks on every ref: "175 commits scanned … no leaks found".
- `git diff origin/main..HEAD | grep -nEi "(api[_-]?key|secret|token|password|passwd|bearer|gsk_|sk-|ghp_|AKIA|-----BEGIN|https?://[^ )]*@)"` matched only two prose lines: the CLAUDE.md context line "secret hygiene", and `agent-team.md` "Secrets (`.env`, keys) … refused".
- `.env` history: per the owner's latest result, `git log --all --oneline -- .env` returned no line (owner check, 13 October 2026). I did not run it.

**Other claims checked**
- Both new files are tracked (`git ls-files`).
- The files the doc links to exist and are tracked: `security/pr-audits/pr-38-triage.md`, `security/pr-audits/pr-38-hook.patch`, `security/scans/`.
- "Four passes" is backed by `security/pr-audits/fix-query-marts-cte-scope-triage.md:15`.
- The doc's account of the deny rules matches `.claude/settings.json` and `pre_tool_use.py`, apart from M1 and L1: force push, push or merge to `main`, `gh pr create/merge`, Render, `agent-hooks/` and settings files, secrets, and the auto-mode classifier as a layer.

## Hook refusal during this audit (reported, not worked around)

The PreToolUse hook refused `git ls-files .env.example; git check-ignore -v .env; git ls-files docs/agent-team.md; grep -n "^test:" -n Makefile` with "secrets files are never read or written by the agent (.env)". The trigger was the `.env` argument to `git check-ignore`.

That command reads no file content, so this may be a false positive (`check-ignore` is in the hook's git list at `pre_tool_use.py:81`). I did not retry it or any equivalent. If the owner wants this check open to agents, the hook would need to allow secret names as arguments to read-only git subcommands.

## Unable to verify

- **The `.env.example` and `.gitignore` check:** whether `.env.example` is tracked and whether `.gitignore` covers `.env`. The command was refused (above). This is an owner check: `git check-ignore -v .env`.
- **The figures in `docs/quality-bar.md`:** "793 unit + 13 integration passed", and the exit codes with the Docker daemon down, local on 23 Oct at 5c50786. I did not re-run the full `make test`, which builds the compose stack.
- **Ruleset bypass actors on `main`:** whether the owner's token, and so the agent's `gh`, can bypass "main protection". This bears on the informational refs-API point.
- **Whether a newer gh has `gh issue edit --state`:** only gh 2.45.0 was checked. https://cli.github.com/manual/gh_issue_edit should be consulted before deciding the fate of that hook branch.
- **"Lessons … applied by the owner"** (`agent-team.md:94`) and the process steps in general: these are process claims. Nothing in code stops the agent from editing `CLAUDE.md`, and this very diff adds a link to it.
- **Pass 2 (`uv run pytest tests/unit/test_copilot_guards.py -v`) and pip-audit / npm audit:** not run. This diff does not touch the copilot guards or the dependencies.

## Prioritized action plan

1. **Quick win, this PR:** reword `docs/agent-team.md:61` and add `gh issue delete/transfer` to the owner-only list (M1a).
2. **Quick win, this PR:** add the "by instruction" sentence under the Roles table (L1).
3. **Quick win, this PR:** strip `MAKEFLAGS`/`MFLAGS`/`MAKELEVEL` from the environment of `_make_test` (L2a).
4. **Quick win, this PR:** clarify the README `make test` row about CI (L3).
5. **Owner, follow-up issue:** hook patch covering `gh issue reopen/delete/transfer` and API issue-state changes, plus an issue row in `docs/permissions.md` (M1b, M1c). Optionally a `-i` guard in the `test` recipe (L2b) and `Edit(/.claude/agents/**)` in the deny rules (L1).

## Files

- /home/ellie/projets/cyclebeat/Makefile
- /home/ellie/projets/cyclebeat/tests/unit/test_agent_team_layout.py
- /home/ellie/projets/cyclebeat/docs/agent-team.md
- /home/ellie/projets/cyclebeat/docs/permissions.md
- /home/ellie/projets/cyclebeat/agent-hooks/pre_tool_use.py
- /home/ellie/projets/cyclebeat/.claude/settings.json
- /home/ellie/projets/cyclebeat/README.md
- /home/ellie/projets/cyclebeat/.github/workflows/ci.yml
- Raw `make audit` output: /tmp/claude-1000/-home-ellie-projets-cyclebeat/205e710c-ed42-452b-b776-8359dc55aa91/scratchpad/audit.txt
