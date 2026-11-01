<!--
Provenance: raw final report of the `security-auditor` subagent, second pass on issue #71
(delta 0ef6e38..bffb593, hook patch 2 = f618410), returned on 2026-10-30. Committed as returned,
with two changes: the harness indentation is removed, and the harness frame lines around the
report are left out. Paths under /tmp/claude-1000/... are the auditor's scratchpad and no
longer exist. Triage: pending (owner decision, see issue #71).
-->

# Security audit, second pass: issue #71, hook patch 2 (f618410)

**Reference branch.** `git branch --show-current` returned `fix/71-hook-executed-command`. I checked every claim against this branch at HEAD `bffb593`. The delta is `0ef6e38..HEAD`, and `69b032e` is the regression baseline. I loaded the 69b032e and 0ef6e38 hooks from `git show <rev>:agent-hooks/pre_tool_use.py` into memory (exec into a module whose `__file__` is the real path, so `ROOT` is the same). I wrote no copy of the hook to disk.

## Executive summary

- **Overall risk: Medium-High.** f618410 closes H1, H2, M2, M4 (cited forms), M5, L2, L3 and L6. Every case in the owner's replay table reproduces. But H3, H4, M1 and L1 are only partly closed: **21 commands that 69b032e refused now pass** (listed below). Two families still read `.env` or delete `lake/`.
- The new commit check fails closed on git errors. It misses several ways of staging in the same command. Its refusal message can still print a secret: with crafted content it echoes a token (proven, `leak=True`).
- No new false positive in 44 normal-work probes. The `git hash-object` false positive is fixed. 351 hook tests pass.
- **Action #1:** before merge, close regression families R1 (echo/printf feeding through any pipeline stage) and R2 (multi-line scripts given to runners the hook does not model). Add the 21 commands as DENIED cases, green on 69b032e, red on HEAD.

## What I ran

- `uv run pytest tests/unit/test_agent_hook.py -q -p no:warnings` → exit 0, 351 dots, all passed. The `-q` in addopts plus `-q` hides the count line; I counted the progress lines: 4×72 + 63.
- `uv run python <scratchpad>/replay2.py`, `replay3.py`, `replay4.py` → exit 0. They call `decide()` only and never run a case. Full text is under "Unable to verify".
- **Two hook refusals during this audit. I stopped and did not work around either:**
  - `git check-ignore -v .env certs/x.pem x.key` → "secrets files are never read or written by the agent (.env)".
  - Then `git check-ignore -v certs/x.pem x.key` → refused on `x.pem`. That second command dropped `.env` but kept a secrets name, so it was arguably a retry of the first; I disclose it.
  - So I did **not** check that `.gitignore` covers `.env`; that is an owner check. Instead I ran `grep -n "pem\|key\|id_" .gitignore` (exit 1: no key pattern is ignored) and `git ls-files | grep -c env.example` → 1.

## Status of the first-pass findings (executed, HEAD = f618410 + docs commits)

| Finding | Status | Proof (decide verdicts, 69b032e / 0ef6e38 / HEAD) |
|---|---|---|
| H1 `${...}` hides `$(...)` | **Closed** | 3 cited cases R/A/R. Also R: ``${x:-`…`}``, nested `${x:-${y:-$(rm -rf lake)}}`, and the double-quoted form |
| H2 attached `-e` | **Closed** for cited forms | `grep -e. .env`, `rg -e. .env`, `git grep --no-index -e. -- .env`, `-Ee.` all R/A/R. Residual, pre-existing in all three: `grep -f.env x` allowed (N6) |
| H3 echo/printf to executor | **Partly closed** | The 3 direct-pipe cases are R/A/R. Six variants pass (R1) |
| H4 nested scripts | **Partly closed** | `bash -euo pipefail -c`, `+o`, `-O`, `--norc`, `-c --`, `find -exec` (incl. `/bin/sh`, `bash -o`), `ssh -p`, `watch -n1`, `sudo -u`, `timeout -s`, `nice -n`, `env -i` all R. Nine other runners pass (R2) |
| M1 for loops | **Partly closed** | (a) 65 values R. 4096 combinations allowed, 65×64 = 4160 refused "this loop is too large to check". (b) and (c) R/A/R. Residual: `${d%/}`, `${d:-x}` (R3) |
| M2 fail-open on git error | **Closed** | Not a repo → "could not be read for secrets: refused (fail closed)". `cd "$(git rev-parse --show-toplevel)" && git commit -m x` with a staged token → refused. Unborn branch + pathspec → refused |
| M3a same-command `git add` | **Closed for `git add`** at the same nesting level, unborn branch included | Gaps in N1 |
| M3b `++ ` header confusion | **Closed for the cited case** (refused, no leak) | Residual echo through a forged header (N2) |
| M4 gh issue state | **Closed for the cited forms**, plus `--raw-field=`, `-XPATCH`, `--field`, `--method=` | `updateIssue(state:)` and `-F query=@file` pass (N5) |
| M5 heredoc with option values | **Closed** | 4 cases A/A/R |
| L1 `case )` | **Closed for `;;`** | `;&` fall-through regresses (R4) |
| L2 `\r` | **Closed** | `echo x\r#$(rm -rf lake)` R/A/R |
| L3 cli prefixes, `--lake agent-hooks` | **Closed** | 3 cases A/A/R |
| L4, L5, L7 | **Open as documented** (ROADMAP line) | Replay-table cases still allowed in all three, consistent with `docs/ROADMAP.md` |
| L6 key staged via a directory | **Closed** | `git add certs/ && git commit` → "a secrets file is staged (certs/s.pem)" |
| L8 docs/tests | **Partly closed** | CLAUDE.md pitfall updated. The test docstring (`tests/unit/test_agent_hook.py:13-14`) still points to "docs/ai-workflow.md, #71", and `grep -c "#71" docs/ai-workflow.md` → 0 (expected at task end, not yet true) |
| hash-object false positive | **Fixed** | `git hash-object agent-hooks/pre_tool_use.py` R/R/A; `-w` R/R/R |

## Regressions against 69b032e

All 21 come from executed verdicts. Every one is `69b032e=R 0ef6e38=A HEAD=A`.

- **R1 (High), echo/printf words reach an executor through something other than the very next `xargs` or shell.** It reads `.env`.
  - `echo .env | tee /dev/null | xargs cat`
  - `echo .env | cat | xargs cat`
  - `printf '%s' .env | sed s/x/x/ | xargs cat`
  - `echo .env | /usr/bin/xargs cat`
  - `echo .env | while read f; do cat "$f"; done`
  - `echo .env > /tmp/l; xargs cat < /tmp/l`
- **R2 (High), a multi-line script given to a runner the hook does not model.** It deletes `lake/`. Each script is `'⏎rm -rf lake⏎'`, passed to:
  - `stdbuf -oL bash -c`
  - `flock /tmp/l -c`
  - `script -qc … /dev/null`
  - `su -c`
  - `setsid bash -c`
  - `tmux new -d`
  - `parallel :::`
  - `git rebase -x … HEAD~1`
  - `git bisect run sh -c`
  - The single-line `git bisect run rm -rf lake` is allowed too; that one is a gap, not a regression.
- **R3 (Medium), the loop variable used through a parameter operator.**
  - `for d in lake/raw; do rm -rf ${d%/}; done`
  - `for d in lake/raw; do rm -rf ${d:-x}; done`
  - `while read d; do rm -rf $d; done < <(echo lake/raw)`
- **R4 (Low), `case` fall-through `;&`.**
  - `(cd lake; case x in a) :;& b) rm -f a.parquet;; esac)`
  - `echo $(cd lake; case x in a) :;& *) rm -f a.parquet;; esac)`
- **No impact:** `rg --files .env`. It lists the name only and reads no content.

The replay table's line "Cases 69b032e refused that the fixed copy lets through: 0" (`security/pr-audits/pr-71-hook-2-replay.md`, last line) is true only for its 51 cases.

## Findings

### High

**R1. echo/printf feed: the link is checked one stage deep, and only for a literal `xargs` word.**
- **Where:** `agent-hooks/pre_tool_use.py`, `_walk`: `piped_in, feed = feed, []`, then `if "xargs" in words:` and `feed = cmd[1:]` only when `seg.piped and _base(cmd[0]) in ("echo", "printf")`. `_data_words` still marks echo/printf words inert.
- **Evidence:** the six R1 commands above are allowed at HEAD and refused at 69b032e.
- **Impact:** `.env` is printed to the transcript.
- **Fix:** keep echo/printf words checked whenever the segment's output goes anywhere other than the terminal. That means piped (`seg.piped`) or redirected to a file, so the word is not inert. Test `xargs` with `_base(word) == "xargs"`. This is the first pass's "never inert when `is_secret`" restricted to segments that feed something. `echo .env` alone stays allowed.
- **Effort:** S.

**R2. Multi-line scripts to runners the hook does not model.**
- **Where:** `_segment_rule`. Only `_nested_script` (shells, eval), `_remote_script` (ssh, watch), `_find_runs` and the `WRAPPERS` set are modelled. `stdbuf`, `setsid`, `flock`, `script`, `su`, `tmux`, `parallel`, `git rebase -x/--exec` and `git bisect run` are not.
- **Evidence:** the nine R2 commands.
- **Impact:** deletes `lake/` (or anything else the script does).
- **Fix:** either:
  - (a) Restore 69b032e's net as a fallback: any quoted argument holding a newline, given to a program that is not modelled, is run through `_nested` and refused if a line would be.
  - (b) Or extend the models: add `stdbuf`, `setsid` and `flock` (valued, `-c`) to the wrappers; add `su -c`, `script -c`, `git rebase -x/--exec` and `git bisect run`.
  - (a) is the safer of the two.
- **Effort:** S for (a), M for (b).

### Medium

**R3. A loop variable used through `${d%…}` or `${d:-…}` is not substituted.**
- **Where:** `_loop_variants`: `if f"${name}" not in text and f"${{{name}}}" not in text: continue`.
- **Evidence:** the R3 commands. `while read d … < <(echo lake/raw)` is refused at 69b032e only by accident (the old line split), and `… <<< lake/raw` passes in all three.
- **Impact:** deletes `lake/`.
- **Fix:** match `re.search(rf"\$\{{?{name}\b", text)`, and expand a `${name<op>…}` word to the item for the path check. Refusing `rm`/`cd` on a word whose variable is unbound (`read VAR`) is an owner decision.
- **Effort:** S.

**N1. The commit check misses several ways of staging in the same command.** Not a regression, since 69b032e had no commit check, but it contradicts `docs/permissions.md`: "a `git add` earlier in the same command".
- **Where:**
  - `_walk`: `_sub(...)[0] == "add"` only.
  - `_added_paths` returns `[str(git_dir)]`, i.e. the cwd, for `-A`, `-u` or no path.
  - `_commit_diff` uses `ls-files -o --exclude-standard`.
  - `_staged_rule` reads only `-C`; `--git-dir`/`--work-tree` are skipped.
  - `_commit_paths` ignores `--pathspec-from-file`.
- **Evidence (real `_commit_diff`, throwaway repos, staged or untracked fake `ghp_` token), all allowed:**
  - `git stage c.py && git commit -m x`
  - `bash -c 'git add c.py' && git commit -m x`
  - `git add -A && git commit -m x` run from `docs/` (the token is at the repo root; the control `git add .` from the root is refused)
  - `git add -f certs/ && git commit -m x` (the key file is ignored by that repo's `.gitignore`; cyclebeat's `.gitignore` ignores no key pattern, so this one is theoretical here)
  - `git --git-dir=B/.git --work-tree=B commit -m x`
  - `GIT_DIR=B/.git git commit -m x` (the control `git -C B commit` is refused)
  - `git commit --pathspec-from-file=list -m x` (the control `git commit -m x README` is refused)
  - `.gitattributes` `*.txt binary` (git prints "Binary files differ")
  - an untracked file with the token after 1 MB (`UNTRACKED_READ_LIMIT`)
- **Impact:** a secret reaches the remote. gitleaks catches it after the push.
- **Fix:**
  - Treat `stage` like `add`.
  - Resolve `-A`/`-u`/no-path against `git rev-parse --show-toplevel`.
  - For `add -f`, list ignored names too (names only, no content read).
  - Refuse (fail closed) when `--git-dir`, `--work-tree`, `--pathspec-from-file`, or a `GIT_DIR=`/`GIT_WORK_TREE=`/`GIT_INDEX_FILE=` prefix is present.
  - Document the binary and 1 MB limits in the "narrow" bullet.
- **Effort:** M.

**N2. The refusal can echo a secret, and line splitting fails open.**
- **Where:** `_secret_in_diff`: `for row in diff.splitlines()`, `path = row.rsplit(" b/", 1)[-1]`, and `_safe_name`, which uses the `\b`-anchored `STAGED_SECRETS`.
- **Evidence:**
  - **Echo.** File content `"x\x0cdiff --git a/q b/z"+TOK+"\n\x0c@@\n"+TOK`:
    - `splitlines()` breaks on `\x0c`, so the content forges a header.
    - `path = "z"+TOK`. `\b` does not match between `z` and `ghp_`, so `_safe_name` does not sanitize it.
    - Message: `… looks like a GitHub token in zghp_a1B2…: unstage it (the value is not shown)` (`leak=True`). The token is fake, built by concatenation.
  - **Echo from a file name.** A staged file named `id_` + TOK is reported as `a secrets file is staged (id_ghp_…)`. The name is already visible to the agent, so the impact is lower.
  - **Fail-open, CR-only line endings.** Staged content `"a\r"+TOK+"\r"` → allowed: the row `TOK` has no `+`.
  - **Fail-open, form feed.** `"x\x0cdiff --git a/q b/q\n"+TOK` → allowed: the rows that follow are taken for a header.
- **Impact:** a secret reaches the transcript through stderr, the same class as M3b. Both the echo and the form-feed case need crafted content; CR-only files occur naturally.
- **Fix:**
  - Split on `"\n"` only.
  - Take paths from the `--name-only -z` list, not from content.
  - Sanitize with unanchored patterns (`(ghp|gho|ghu|ghs|ghr)_`, `github_pat_`, `AKIA|ASIA`), or print only "file k of n".
- **Effort:** S.

### Low

**R4. `case` fall-through `;&` desynchronises the lexer.**
- **Where:** the `_Lexer` case state. Only `;;` returns from body to pattern. `;&` lexes as `;` `&`, so the next pattern's `)` is read as a subshell close and the scope is popped.
- **Evidence:** the R4 commands.
- **Fix:** treat `;&` and `;;&` like `;;` in the body state.
- **Effort:** S.

**N3. The hook's own git calls run a program the repo's config names.**
- **Where:** `_commit_diff` runs `git diff`/`ls-files` in the target repo with no `-c core.fsmonitor=false`.
- **Evidence:** in a throwaway repo with `core.fsmonitor=<scratch>/fsmon.sh` (it touches a marker file), `decide("git commit -m x")` → allowed, and "fsmonitor program executed by the hook: True".
- **Impact:** a program runs before the hook decides, with no check of what it does. No new capability beyond the documented "a script built at runtime is not seen", but the program now runs inside the guardrail itself.
- **Fix:** prefix every hook git call with `-c core.fsmonitor=false`.
- **Effort:** S.

**N4. The 6 s budget is per commit segment, not per hook call.**
- **Where:** `deadline = time.monotonic() + STAGED_BUDGET_S` is set inside `_commit_diff`. `_staged_rule` runs once per loop variant and once per commit segment.
- **Evidence:**
  - `for m in a b c d; do git commit -m $m; done` → 4 `staged_of` calls (worst case 24 s).
  - `git commit -m a; git commit -m b; git commit -m c` → 3 calls.
  - On top of that, `_roots()` takes up to 3 s at import, and `_current_branch` 3 s.
  - Measured cost is 0.00–0.16 s per check, so the risk is theoretical.
  - Past 10 s the result depends on `onFailure: "block"`, which I have not verified (see below).
- **Fix:** one deadline per `decide()` call, carried in `_Ctx`, and memoise identical `(git_dir, args, added)`.
- **Effort:** S.

**N5. Issue-state coverage gaps.** The docs match the code; the gap is in the policy itself.
- **Evidence:** both allowed in all three:
  - `gh api graphql -f query='mutation{updateIssue(input:{id:"I",state:CLOSED}){…}}'`
  - `gh api graphql -F query=@m.graphql` (the file is not read)
- **Fix:** add `updateIssue` with a `state` argument to `GH_GRAPHQL_ISSUE_STATE`. Whether an `@file` GraphQL query should be refused is the owner's decision.
- **Effort:** S.

**N6. Pattern exemption residue.**
- `grep -f.env x` is allowed in all three; it was never refused, so it is not a regression. grep reads its patterns from `.env`, so a match can reveal a value.
- **Fix:** read an attached `-f` value as a file.
- **Effort:** S.

**N7. Docs against code.**
- `docs/permissions.md` "Limits" and the docstring say echo/printf words "piped into `xargs` or a shell" are checked. True only for the next stage and a literal `xargs` (R1).
- "Checks every string bash runs" leaves out the runners in R2, and they are not listed as limits.
- "The refusal names the pattern and the file, never a line of content" (docstring, `docs/permissions.md` "Commit a secret" row, README row) is falsified by N2.
- "A `git add` earlier in the same command" has the N1 exceptions.
- "A git error or the 6 s budget refuses the commit": verified for git errors; the budget is per commit (N4).
- The CLAUDE.md #45 pitfall now matches `_gh_rule`, and the README/permissions issue-state lists match the code exactly.
- The ROADMAP line (L4/L5/L7) matches the replay. It does not list R1–R4 or N1–N6.
- The test docstring's `docs/ai-workflow.md` reference (L8) has no entry yet.

### False positives on normal work

No new false positive. All 44 probes are allowed at HEAD, including:
- `git hash-object`, `--stdin`
- `case … a|b)`
- `for` over `tests/*.py`, `agent-hooks/*.py`, `lake/raw/*.parquet` (the last two were false positives at 69b032e)
- `bash -o pipefail -c`, `-euo pipefail`, `-lc`, `-O extglob`
- `ssh host ls`, `ssh -p 22 -i …`, `watch -n 1 ls`
- `find /tmp … -exec rm`
- `echo ls | sh`, `echo .env.example | xargs cat`
- `gh api … -f title=`, comments, GraphQL queries
- `python3 -W ignore -c`, `-X importtime`
- clean `git add a.py && git commit` and `git add -A && git commit` in a real throwaway repo

Pre-existing false positives, refused in all three:
- `find . -name '*.py' -exec grep -l TODO {} \;` and `-exec ruff check {} +` (rule: `find .` with `-exec`)
- `find lake … -exec ls`
- `case "$p" in data/*|lake/*) …`
- `case "$f" in .env) …`

The `case` patterns are lexed into the `case` command's words.

## Unable to verify

- **`.gitignore` covers `.env`:** refused by the hook (above). Owner check, along with her `git log --all --oneline -- .env` result. I have no newer result than the 13 October 2026 one cited in my brief.
- **`onFailure: "block"`** and what Claude Code does when the hook passes its 10 s `timeout`: not checked against https://code.claude.com/docs/en/hooks.
- **GitHub's `UpdateIssueInput` has a `state` field** (N5): from memory, not checked against https://docs.github.com/en/graphql/reference/input-objects#updateissueinput.
- **gh/pflag accepts attached `-fkey=value`:** not checked.
- **Bash behaviour of `;&` and `< <(…)`:** taken from the bash manual's grammar, not executed.
- **`make audit`, pip-audit, npm audit:** not run, outside this delta's scope.
- **Scripts run, verbatim** (`/tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay2.py`, `…/replay3.py`, `…/replay4.py`; each run with `uv run python <path>` from the repo root; `replay4.py` reuses the `repos/staged` repo that `replay2.py` builds):

```python
# replay2.py
"""Second-pass replay for #71: calls decide() of 69b032e, 0ef6e38 and HEAD; never runs a case."""
import importlib.util, inspect, os, subprocess, sys, time, types
from pathlib import Path

REPO = Path("/home/ellie/projets/cyclebeat")
HOOKP = REPO / "agent-hooks/pre_tool_use.py"
SCR = Path(__file__).resolve().parent
NL = "\n"

def load_head():
    spec = importlib.util.spec_from_file_location("hook_head", HOOKP)
    m = importlib.util.module_from_spec(spec); sys.modules["hook_head"] = m
    spec.loader.exec_module(m); return m

def load_rev(rev):
    src = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:agent-hooks/pre_tool_use.py"],
                         capture_output=True, text=True, check=True).stdout
    name = f"hook_{rev}"
    m = types.ModuleType(name); m.__file__ = str(HOOKP); sys.modules[name] = m
    exec(compile(src, f"{rev}:agent-hooks/pre_tool_use.py", "exec"), m.__dict__)
    return m

HOOKS = {"69b032e": load_rev("69b032e"), "0ef6e38": load_rev("0ef6e38"), "HEAD": load_head()}

def verdict(m, cmd, cwd=REPO, staged=None, tool="Bash"):
    ev = {"tool_name": tool, "tool_input": {"command": cmd}, "cwd": str(cwd)}
    kw = {"branch_of": lambda _c: "feature"}
    if "staged_of" in inspect.signature(m.decide).parameters:
        kw["staged_of"] = staged if staged is not None else (lambda *a: "")
    try:
        r = m.decide(ev, **kw)
    except Exception as exc:  # main() turns this into exit 2
        r = f"guardrail error ({type(exc).__name__})"
    return r

def table(title, cases):
    print(f"\n## {title}")
    for c in cases:
        cells = []
        for k, m in HOOKS.items():
            r = verdict(m, c)
            cells.append(f"{k}={'R' if r else 'A'}")
        r = verdict(HOOKS["HEAD"], c)
        print(f"{' '.join(cells)} | {c!r}" + (f"  -> {r[:90]}" if r else ""))

items = " ".join(f"x{i}" for i in range(64))
FIRST_PASS = [
    "echo ${x:-$(rm -rf lake)}", "echo ${x:-$(cat .env)}", ": ${x:=`git push --force`}",
    "grep -e. .env", "rg -e. .env", "git grep --no-index -e. -- .env",
    "echo .env | xargs cat", "printf '%s\\n' .env | xargs -I{} cp {} /tmp/leak", "echo cat .env | sh",
    f"bash -euo pipefail -c '{NL}rm -rf lake{NL}'",
    f"find /tmp -maxdepth 0 -exec sh -c '{NL}cat .env{NL}' \\;",
    f"ssh localhost '{NL}cat ~/projets/cyclebeat/.env{NL}'",
    "bash -o pipefail -c 'rm -rf lake'",
    f"for d in {items} lake/raw; do rm -rf $d; done",
    "for d in lake/raw; do :; done; rm -rf $d",
    "for d in lake/raw; do cd $d && rm -f a.parquet; done",
    "gh api -X PATCH repos/o/r/issues/71 --input body.json",
    "gh api -X PATCH repos/o/r/issues/71 -fstate=closed",
    "gh api graphql -f query='mutation{closeIssue(input:{issueId:\"I\"}){clientMutationId}}'",
    "gh api -X PATCH 'repos/o/r/issues/71?x=1' -f state=closed",
    "gh api repos/o/r/pulls -fhead=x -fbase=main -ftitle=t",
    f"bash -o pipefail <<'X'{NL}rm -rf lake{NL}X",
    f"bash -euo pipefail <<'X'{NL}rm -rf lake{NL}X",
    f"python3 -W ignore - <<'X'{NL}import shutil; shutil.rmtree('lake'){NL}X",
    "python3 -X dev -c \"import shutil; shutil.rmtree('lake')\"",
    "(cd lake; case x in *) rm -f a.parquet;; esac)",
    "echo $(cd lake; case x in *) rm -f a.parquet;; esac)",
    "echo x\r#$(rm -rf lake)",
    "uv run python -m cyclebeat.cli --la lake ingest",
    "uv run python -m cyclebeat.cli --lake /tmp/x ingest --liv",
    "uv run python -m cyclebeat.cli --lake agent-hooks ingest",
    "git hash-object agent-hooks/pre_tool_use.py", "git hash-object -w agent-hooks/pre_tool_use.py",
]
REGRESSION_PROBES = [
    "echo .env | tee /dev/null | xargs cat", "echo .env | cat | xargs cat",
    "printf '%s' .env | sed s/x/x/ | xargs cat", "echo .env | /usr/bin/xargs cat",
    "echo .env | while read f; do cat \"$f\"; done",
    "echo .env > /tmp/l; xargs cat < /tmp/l", "echo 'cat .env' > /tmp/s.sh; bash /tmp/s.sh",
    "echo 'cat .env' | source /dev/stdin", "echo 'cat .env' | . /dev/stdin",
    "echo rm -rf lake | xargs -I{} sh -c {}",
    "(cd lake; case x in a) :;& b) rm -f a.parquet;; esac)",
    "echo $(cd lake; case x in a) :;& *) rm -f a.parquet;; esac)",
    "for d in lake/raw; do rm -rf ${d%/}; done", "for d in lake/raw; do rm -rf ${d:-x}; done",
    "for d in lake/raw; do rm -rf \"$d\"; done", "for d in lake/raw; do rm -rf ${d}; done",
    "for f in .env; do cat $f; done", "for f in .env; do cat ${f%x}; done",
    "select d in lake/raw; do rm -rf $d; break; done",
    "while read d; do rm -rf $d; done <<< lake/raw",
    "while read d; do rm -rf $d; done <<< .env",
    "xargs rm -rf <<< lake/raw", "IFS= read -r d <<< lake/raw; rm -rf \"$d\"",
    "while read d; do rm -rf $d; done < <(echo lake/raw)", "diff <(cat .env) /dev/null",
    "grep --file=.env x", "grep -f.env x", "grep -f .env x", "grep -A1 . .env", "grep -e x -- .env",
    "grep -ve x .env", "rg --files .env", "git grep --no-index -Ee. .env",
    f"uv run bash -c '{NL}rm -rf lake{NL}'", f"stdbuf -oL bash -c '{NL}rm -rf lake{NL}'",
    f"flock /tmp/l -c '{NL}rm -rf lake{NL}'", f"script -qc '{NL}rm -rf lake{NL}' /dev/null",
    f"su -c '{NL}rm -rf lake{NL}'", f"setsid bash -c '{NL}rm -rf lake{NL}'",
    f"tmux new -d '{NL}rm -rf lake{NL}'", f"parallel ::: '{NL}rm -rf lake{NL}'",
    f"git rebase -x '{NL}rm -rf lake{NL}' HEAD~1", f"git bisect run sh -c '{NL}rm -rf lake{NL}'",
    f"docker run --rm -v $PWD:/w alpine sh -c '{NL}rm -rf /w/lake{NL}'",
    f"make -f /dev/stdin <<'X'{NL}all:{NL}\trm -rf lake{NL}X",
    f"awk 'BEGIN{{{NL}system(\"rm -rf lake\"){NL}}}'",
    f"perl -e '{NL}system(\"rm -rf lake\"){NL}'",
    f"uv run python -c '{NL}import shutil{NL}shutil.rmtree(\"lake\"){NL}'",
    f"node -e '{NL}require(\"fs\").rmSync(\"lake\",{{recursive:true}}){NL}'",
    f"watch -n1 '{NL}rm -rf lake{NL}'", f"ssh -p 22 host '{NL}rm -rf ~/projets/cyclebeat/lake{NL}'",
    f"sudo -u x bash -c '{NL}rm -rf lake{NL}'", f"timeout -s KILL 5 bash -c '{NL}rm -rf lake{NL}'",
    f"xargs -n1 bash -c '{NL}rm -rf lake{NL}' <<< x",
    f"find . -maxdepth 0 -exec bash -o pipefail -c '{NL}rm -rf lake{NL}' \\;",
    f"find . -maxdepth 0 -exec /bin/sh -c '{NL}rm -rf lake{NL}' \\;",
    f"env -i bash -c '{NL}rm -rf lake{NL}'", f"nice -n 5 bash -c '{NL}rm -rf lake{NL}'",
    f"bash --norc -c '{NL}rm -rf lake{NL}'", f"bash -c -- '{NL}rm -rf lake{NL}'",
    f"bash +o posix -c '{NL}rm -rf lake{NL}'", f"bash -O extglob -c '{NL}rm -rf lake{NL}'",
    "echo ${x:-`rm -rf lake`}", "echo \"${x:-$(rm -rf lake)}\"", "echo ${x:-${y:-$(rm -rf lake)}}",
    "rm -rf ${x:-lake}", "cd lake && rm -rf 2024 >/dev/null",
    "find . -exec rm -rf {} +", "find lake -exec rm {} \\;",
    "x=$(cat .env)", "cat .e{n,}v", "git clean -fdx",
]
FP_PROBES = [
    "git hash-object agent-hooks/pre_tool_use.py", "git hash-object --stdin < README.md",
    "case \"$x\" in a|b) echo yes;; *) echo no;; esac",
    "case \"$p\" in data/*|lake/*) echo protected;; esac",
    "case \"$f\" in .env) echo skip;; esac",
    "for f in tests/*.py; do wc -l \"$f\"; done", "for f in a b c; do echo $f; done",
    "for f in agent-hooks/*.py; do grep -c def \"$f\"; done",
    "for f in lake/raw/*.parquet; do ls -l \"$f\"; done",
    "for d in lake data; do du -sh $d; done",
    "bash -o pipefail -c 'make test-unit | tail -5'", "bash -euo pipefail -c 'uv run pytest -q'",
    "set -o pipefail; make lint 2>&1 | tail -3", "bash -lc 'ls'", "bash -O extglob -c 'ls'",
    "bash scripts/x.sh", "bash -x scripts/x.sh",
    "find . -name '*.py' -exec grep -l TODO {} \\;", "find . -name '*.py' -exec ruff check {} +",
    "find /tmp -type f -name '*.tmp' -exec rm {} \\;", "find lake -name '*.parquet' -exec ls -l {} \\;",
    "find . -maxdepth 1 -execdir ls {} \\;",
    "ssh host ls", "ssh -p 22 -i ~/.ssh/k host uptime", "ssh host", "watch -n 1 ls",
    "git add README.md && git commit -m 'docs: x'",
    "git add -A && git commit -m x", "git commit -am 'x'",
    "echo hello | xargs echo", "printf '%s\\n' a b | xargs -n1 echo", "echo ls | sh",
    "echo .env.example | xargs cat", "grep -rn foo src/", "grep -e foo -e bar README.md",
    "gh api -X PATCH repos/o/r/issues/71 -f title=x", "gh api repos/o/r/issues/71/comments -f body=x",
    "gh api graphql -f query='query{repository(owner:\"o\",name:\"r\"){issue(number:1){title}}}'",
    "uv run python -m cyclebeat.cli --help", "uv run python -m cyclebeat.cli --lake /tmp/x ingest",
    "python3 -W ignore -c 'print(1)'", "python3 -X importtime -c 'import json'",
    "printf 'a\\r\\nb' > /tmp/x",
]
table("First-pass findings (69b032e / 0ef6e38 / HEAD)", FIRST_PASS)
table("Regression probes", REGRESSION_PROBES)
table("False-positive probes", FP_PROBES)
table("gh issue-state probes", [
    "gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",state:CLOSED}){clientMutationId}}'",
    "gh api graphql -F query=@m.graphql",
    "gh api -X PATCH repos/o/r/issues/71 --raw-field=state=closed",
    "gh api --method=PATCH /repos/o/r/issues/71 -F state_reason=completed",
    "gh api -XPATCH repos/o/r/issues/71 -f state=closed",
    "gh api -X PATCH repos/o/r/issues/71 --field state=closed",
    "gh issue close 71", "gh issue edit 71 --add-label x",
])

H = HOOKS["HEAD"]
TOK = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0" + "kLmNoPqRsTuVwXyZ12"
PEM = "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----"
REPOS = SCR / "repos"
subprocess.run(["rm", "-rf", str(REPOS)], check=True)
REPOS.mkdir()
G = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]

def repo(name, born=True):
    d = REPOS / name; d.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feature", str(d)], check=True)
    if born:
        (d / "README").write_text("x\n")
        subprocess.run(["git", "-C", str(d), *G, "add", "README"], check=True)
        subprocess.run(["git", "-C", str(d), *G, "commit", "-qm", "init"], check=True)
    return d

def git(d, *a):
    subprocess.run(["git", "-C", str(d), *G, *a], check=True, capture_output=True)

def commit_case(label, d, cmd, cwd=None):
    t = time.monotonic()
    r = verdict(H, cmd, cwd=cwd or d, staged=H._commit_diff)
    dt = time.monotonic() - t
    leak = bool(r) and any(p in r for p in (TOK, TOK[4:], PEM))
    print(f"{'R' if r else 'A'} {dt:5.2f}s leak={leak} | {label} | {cmd!r}" + (f" -> {r}" if r else ""))

print("\n## Commit check (HEAD, real _commit_diff, throwaway repos)")
d = repo("staged"); (d / "c.py").write_text(f"T = '{TOK}'\n"); git(d, "add", "c.py")
commit_case("staged token", d, "git commit -m x")
d = repo("addsame"); (d / "c.py").write_text(f"T = '{TOK}'\n")
commit_case("git add same command", d, "git add c.py && git commit -m x")
commit_case("git stage same command", d, "git stage c.py && git commit -m x")
commit_case("git add in bash -c, commit outside", d, "bash -c 'git add c.py' && git commit -m x")
d = repo("plusplus"); (d / "c.py").write_text(f"++ {TOK}\n{TOK}\n"); git(d, "add", "c.py")
commit_case("M3b ++ line", d, "git commit -m x")
d = repo("certs"); (d / "certs").mkdir(); (d / "certs/s.pem").write_text("x\n")
commit_case("L6 add certs/", d, "git add certs/ && git commit -m x")
d = repo("forced"); (d / ".gitignore").write_text("*.pem\n"); git(d, "add", ".gitignore"); git(d, "commit", "-qm", "gi")
(d / "certs").mkdir(); (d / "certs/s.pem").write_text(PEM + "\nabc\n")
commit_case("git add -f of an ignored key", d, "git add -f certs/ && git commit -m x")
d = repo("pub"); (d / "id_ed25519.pub").write_text("ssh-ed25519 AAAA x\n"); git(d, "add", "id_ed25519.pub")
commit_case("id_ed25519.pub staged", d, "git commit -m x")
d = repo("cr"); (d / "c.txt").write_bytes(f"a\r{TOK}\r".encode()); git(d, "add", "c.txt")
commit_case("CR-only line ending", d, "git commit -m x")
d = repo("ff"); (d / "c.txt").write_bytes(f"x\x0cdiff --git a/q b/q\n{TOK}\n".encode()); git(d, "add", "c.txt")
commit_case("form feed forges a diff header", d, "git commit -m x")
d = repo("ffleak")
(d / "c.txt").write_bytes(f"x\x0cdiff --git a/q b/z{TOK}\n\x0c@@\n{TOK}\n".encode()); git(d, "add", "c.txt")
commit_case("forged header carries the token as path", d, "git commit -m x")
d = repo("namedleak"); (d / f"id_{TOK}").write_text("x\n"); git(d, "add", "-A")
commit_case("staged id_* name holding a token", d, "git commit -m x")
d = repo("attr"); (d / ".gitattributes").write_text("*.txt binary\n"); git(d, "add", ".gitattributes"); git(d, "commit", "-qm", "a")
(d / "c.txt").write_text(f"{TOK}\n"); git(d, "add", "c.txt")
commit_case(".gitattributes binary", d, "git commit -m x")
d = repo("pathspecfile"); (d / "README").write_text(f"{TOK}\n"); (d / "list").write_text("README\n")
commit_case("--pathspec-from-file", d, "git commit --pathspec-from-file=list -m x")
commit_case("pathspec (control)", d, "git commit -m x README")
d = repo("unborn", born=False); (d / "c.py").write_text(f"{TOK}\n")
commit_case("unborn, add same command", d, "git add c.py && git commit -m x")
dA = repo("A"); dB = repo("B"); (dB / "c.py").write_text(f"{TOK}\n"); git(dB, "add", "c.py")
commit_case("--git-dir/--work-tree to B", dA, f"git --git-dir={dB}/.git --work-tree={dB} commit -m x")
commit_case("GIT_DIR= prefix to B", dA, f"GIT_DIR={dB}/.git git commit -m x")
commit_case("-C B (control)", dA, f"git -C {dB} commit -m x")
d = repo("sub"); (d / "docs").mkdir(); (d / "docs/a.md").write_text("a\n"); (d / "c.py").write_text(f"{TOK}\n")
commit_case("git add -A from a subdirectory", d, "git add -A && git commit -m x", cwd=d / "docs")
commit_case("git add . (control, root)", d, "git add . && git commit -m x")
commit_case("not a repo (fail closed)", d, "git commit -m x", cwd=SCR)
big = repo("big"); (big / "c.py").write_text(("x = 1\n" * 200000) + TOK + "\n")
commit_case("untracked file, token after 1 MB", big, "git add c.py && git commit -m x")
d = repo("fsmon"); marker = SCR / "fsmonitor-ran"; marker.unlink(missing_ok=True)
prog = SCR / "fsmon.sh"; prog.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n"); prog.chmod(0o755)
git(d, "config", "core.fsmonitor", str(prog)); (d / "c.py").write_text("x\n"); git(d, "add", "c.py")
marker.unlink(missing_ok=True)
commit_case("core.fsmonitor configured", d, "git commit -m x")
print("fsmonitor program executed by the hook:", marker.exists())
calls = []
def counting(*a):
    calls.append(a); return ""
verdict(H, "for m in a b c d; do git commit -m $m; done", staged=counting)
print("\nstaged_of calls for a 4-value loop:", len(calls), "-> worst case", len(calls) * H.STAGED_BUDGET_S, "s of git budget")
calls.clear()
verdict(H, "git commit -m a; git commit -m b; git commit -m c", staged=counting)
print("staged_of calls for 3 commits in one command:", len(calls))
```

```python
# replay3.py
import importlib.util, sys
spec = importlib.util.spec_from_file_location("h", "/home/ellie/projets/cyclebeat/agent-hooks/pre_tool_use.py")
h = importlib.util.module_from_spec(spec); sys.modules["h"] = h; spec.loader.exec_module(h)
def v(c):
    return h.decide({"tool_name": "Bash", "tool_input": {"command": c}, "cwd": str(h.ROOT)},
                    branch_of=lambda _c: "feature", staged_of=lambda *a: "")
a = " ".join(f"a{i}" for i in range(64)); b = " ".join(f"b{i}" for i in range(65))
print("4096 combos:", v(f"for x in {a}; do for y in {a}; do echo $x$y; done; done"))
print("4160 combos:", v(f"for x in {a}; do for y in {b}; do echo $x$y; done; done"))
print("bisect run one line:", v("git bisect run rm -rf lake"))
print("echo|tee|sh:", v("echo cat .env | tee /dev/null | sh"))
```
Output:
```
4096 combos: None
4160 combos: this loop is too large to check (more than 4096 loop values): refused
bisect run one line: None
echo|tee|sh: None
```

```python
# replay4.py (reuses repos/staged built by replay2.py)
import importlib.util, subprocess, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("h", "/home/ellie/projets/cyclebeat/agent-hooks/pre_tool_use.py")
h = importlib.util.module_from_spec(spec); sys.modules["h"] = h; spec.loader.exec_module(h)
SCR = Path(__file__).resolve().parent
TOK = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0" + "kLmNoPqRsTuVwXyZ12"
G = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
def v(c, cwd):
    return h.decide({"tool_name": "Bash", "tool_input": {"command": c}, "cwd": str(cwd)},
                    branch_of=lambda _c: "feature", staged_of=h._commit_diff)
d = SCR / "repos" / "staged"
print("M2 cd $(rev-parse):", v('cd "$(git rev-parse --show-toplevel)" && git commit -m x', d))
u = SCR / "repos" / "unborn2"
subprocess.run(["rm", "-rf", str(u)], check=True)
subprocess.run(["git", "init", "-q", str(u)], check=True)
(u / "c.py").write_text(TOK + "\n"); subprocess.run(["git", "-C", str(u), *G, "add", "c.py"], check=True)
print("M2 unborn pathspec:", v("git commit -m x c.py", u))
c = SCR / "repos" / "clean"
subprocess.run(["rm", "-rf", str(c)], check=True)
subprocess.run(["git", "init", "-q", str(c)], check=True)
(c / "a.py").write_text("print(1)\n")
print("FP clean add+commit:", v("git add a.py && git commit -m 'feat: a'", c))
print("FP clean add -A + commit:", v("git add -A && git commit -m x", c))
```
Output: both M2 cases are refused ("adds what looks like a GitHub token in c.py"); both clean cases → `None`.

The full replay2 output is in `/tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay2.out`. The scratchpad does not survive a WSL shutdown.

## Prioritized action plan

1. **Quick win.** R1: echo/printf words stay checked when the segment is piped or redirected; test `xargs` by `_base`. S.
2. R2: restore the multi-line-argument fallback for programs the hook does not model (69b032e's net). S/M.
3. **Quick win.** N2: split the diff on `"\n"`, take paths from `--name-only -z`, sanitize names with unanchored patterns. Closes the proven echo. S.
4. **Quick win.** R3: match `${name<op>…}` in `_loop_variants`. S.
5. **Quick win.** R4: `;&` / `;;&` in the case lexer. S.
6. **Quick win.** N3: `-c core.fsmonitor=false` on every hook git call. S.
7. N1: `git stage`; top-level for `-A`/`-u`; ignored names for `add -f`; fail closed on `--git-dir`, `--work-tree`, `GIT_DIR=`, `--pathspec-from-file`. M.
8. N4: one deadline per `decide()` call, plus memoisation. S.
9. N5/N6: `updateIssue` with `state`; attached `-f` value for grep. Owner decision on `query=@file`. S.
10. Tests: the 21 regression commands, plus the N1/N2 commit cases, as DENIED: green on 69b032e where it refused them, red on HEAD.
11. Docs (N7): narrow the "echo piped into xargs or a shell", "never a line of content" and "a `git add` earlier in the same command" sentences, or fix the code. List the unmodelled runners and the binary/1 MB limits under "Limits". Restrict the replay table's "0" line to its 51 cases. Add the `docs/ai-workflow.md` #71 entry that the test docstring cites.

## Relevant files

- /home/ellie/projets/cyclebeat/agent-hooks/pre_tool_use.py
- /home/ellie/projets/cyclebeat/agent-hooks/README.md
- /home/ellie/projets/cyclebeat/docs/permissions.md
- /home/ellie/projets/cyclebeat/docs/ROADMAP.md
- /home/ellie/projets/cyclebeat/CLAUDE.md
- /home/ellie/projets/cyclebeat/tests/unit/test_agent_hook.py
- /home/ellie/projets/cyclebeat/security/pr-audits/pr-71-hook-2-replay.md
- /home/ellie/projets/cyclebeat/security/pr-audits/pr-71-security-auditor.md
- /home/ellie/projets/cyclebeat/.claude/agents/security-auditor.md
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay2.py
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay2.out
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay3.py
- /tmp/claude-1000/-home-ellie-projets-cyclebeat/1caddae0-3162-40e7-b26a-65de1b0da5c2/scratchpad/replay4.py
