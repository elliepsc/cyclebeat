<!--
Provenance: raw final report of the `security-auditor` subagent (.claude/agents/security-auditor.md
at 5e58d8f), run on 2026-10-30 by the main agent (Claude Code) on branch
fix/71-hook-executed-command at HEAD 5e58d8f, over the owner-applied hook patch 0ef6e38
(issue #71). Changes from the raw output, disclosed: the harness indented every line by two
spaces (removed), and it prefixed one harness note line saying the output matched an
instruction-shaped pattern ("settings-json") and that control tags were neutralized (that line
is not the auditor's and is left out). No other edit. Triage follows the report, after the
second rule.
-->

# Security audit: issue #71, PreToolUse hook patch

**Reference branch:** I ran `git branch --show-current` first and got `fix/71-hook-executed-command`. Claims are checked against this branch at HEAD `5e58d8f`, with `69b032e` as the base. I checked that `git diff 69b032e 0ef6e38 -- agent-hooks/` is byte-identical to `security/pr-audits/pr-71-hook.patch` (`diff` returned nothing, so IDENTICAL).

## Executive summary

- **Overall risk: High.** The lexer works and the six false positives are fixed. But four of the new "data" exemptions let through commands the hook at 69b032e refused, and those commands really do write `lake/` or read `.env`.
- The worst one: `${...}` is copied as a literal, so any `$(...)` or backtick inside it is never checked (`echo ${x:-$(rm -rf lake)}`).
- Candidate 7 fails open when `git diff` errors, does not see a `git add X && git commit` in the same command, and can print a token in its own refusal message.
- **Action #1:** before merge, fix H1–H4 and add each command below as a DENIED case. Show each one green on 69b032e and red on 0ef6e38, which is the red-first proof the test docstring promises.

## How I worked

**What I could not run:**
- My Bash list is closed, so I did not run `uv run python -c`/`python -` against `decide()`, and I did not run `gh issue view 71` (I could not read comments 6518839171/6518942958). Every finding below comes from reading the code at the cited lines, traced by hand against the old code (`git show 69b032e:agent-hooks/pre_tool_use.py`). There is a script to confirm them at the end.
- `make audit` was not run: it is outside this brief's scope.

**What I ran:**
- `uv run pytest tests/unit/test_agent_hook.py -q` → exit 0. The summary line was not captured, so I give no count.

**A hook refusal during this audit:**
- My command `grep -rn ... --include=*.md .` was refused: "grep over . reaches .env: exclude it explicitly...". That is the rule working as designed. I did not retry. The stale line I was looking for is already in CLAUDE.md, which I had in context (see L8).

## Findings

### High

**H1. `${...}` hides the command substitutions inside it.** This is a regression.
- **Where:** `agent-hooks/pre_tool_use.py:401-406` (`_Lexer._word`).
- **Evidence:**
  ```python
  elif s.startswith("${", self.i):
      end = s.find("}", self.i)
      ...
      buf.append(s[self.i : end + 1])
  ```
  The text up to the first `}` is copied literally. `tok.subs` is never filled, so `_walk` never sees the `$(...)` inside it.
- **Commands:**
  - `echo ${x:-$(rm -rf lake)}`
  - `echo ${x:-$(cat .env)}`
  - ``: ${x:=`git push --force`}``
- **Old hook:** `_tokens` replaced every `$(` and backtick with ` ; `, so `rm -rf lake)}` became a segment of its own and was refused.
- **New hook:** `echo` plus one literal word, with no `/` → allowed.
- Inside double quotes it is handled, because `_double` scans `$(`. Unquoted heredoc bodies are also handled, because `_heredoc_subs` scans character by character.
- **Impact:** deletes `lake/`, reads `.env`, force-pushes. Any command can be hidden this way.
- **Fix:** in the `${` branch, scan with brace depth and quotes. Treat `$(` and backticks inside it as in `_double` (`_dollar_paren`/`_backtick` into `tok.subs`). Refuse an unclosed one.
- **Effort:** S.

**H2. A grep/rg/`git grep` pattern given with an attached `-e` makes the file look like the pattern.** This is a regression: `.env` can be read.
- **Where:** `pre_tool_use.py:1102-1127` (`_pattern_words`), used by `_data_words:1065-1066`.
- **Evidence:** only `-e`, `--regexp` and `--regexp=` count as an explicit pattern. `-e.` or `-ie.` do not. The first positional is then marked inert, and here that positional is the file.
- **Commands:**
  - `grep -e. .env` (grep prints every non-empty line of `.env`)
  - `rg -e. .env`
  - `git grep --no-index -e. -- .env`
- **Old hook:** the `.env` word was checked and refused. The new hook skips it.
- **Fix:** treat any short-option bundle containing `e` (or `f`) as explicit. Simpler and safer: never mark a word inert when `is_secret(word)` is true. A grep *pattern* that is exactly a secrets filename is rare, and the cost is one false positive. The same idea applies to the `git log -S/-G/--grep` and exclude-value exemptions.
- **Effort:** S.

**H3. echo/printf arguments are inert, but bash pipes them into a program that opens them.** This is a regression: `.env` can be read.
- **Where:** `pre_tool_use.py:1063-1064`.
- **Evidence:**
  ```python
  if head in ("echo", "printf"):
      inert.update(range(1, len(cmd)))
  ```
- **Commands:**
  - `echo .env | xargs cat`
  - `printf '%s\n' .env | xargs -I{} cp {} /tmp/leak`
  - `echo cat .env | sh`
- **Old hook:** refused all three on the `.env` word. The new hook allows them, because the `xargs`/`sh` segment holds no secret word and nothing links the pipe.
- **Fix:** exempt echo/printf only when the segment is not followed by `|`/`|&` into `xargs`, a shell or python. Or apply the "never inert when `is_secret`" rule from H2, which closes H2 and H3 together.
- **Effort:** S.

**H4. Multi-line scripts given to an interpreter the new hook does not model are no longer seen.** This is a regression: the old hook's line split caught them by accident.
- **Where:** `pre_tool_use.py:998-1011` (`_nested_script`), and the whole-command lexing at `run()`.
- **Evidence:** `_nested_script` returns `None` at the first non-dash word. So in `bash -euo pipefail -c '...'` the word `pipefail` stops the search for `-c`, and the script is never checked. The old hook split the command on `\n` before shlex, so the script's inner lines were parsed as commands and refused.
- **Commands:**
  - `bash -euo pipefail -c '\nrm -rf lake\n'` (`\n` = a real newline). A very common agent idiom.
  - `find /tmp -maxdepth 0 -exec sh -c '\ncat .env\n' \;`
  - `ssh localhost '\ncat ~/projets/cyclebeat/.env\n'`
- **Single-line forms** (`bash -o pipefail -c 'rm -rf lake'`) already passed at 69b032e. That part is a gap, not a regression, but it contradicts the claim "the script of `bash -c` ... checked".
- **Fix:**
  - In `_nested_script`, skip option values (`-o X`, `-O X`, `+o X`, `--rcfile X`, `--init-file X`) and look for `c` in every short bundle.
  - For `find -exec/-execdir <shell> -c`, `sudo [-u U] <shell> -c`, `ssh` and `watch`, run the script argument through `_nested`.
  - Or, failing that, keep the old fallback: refuse a multi-line quoted argument of a non-modelled program when one of its lines would be refused.
- **Effort:** M.

### Medium

**M1. A `for` list is no longer checked as paths, and the loop-variable substitute that replaces that check leaks.** This is a regression: the old hook refused any `for` line naming `data/`/`lake/` with a `/`.
- **Where:** `pre_tool_use.py:1333-1340` and `1373-1389`.
- **(a) Silent cap at 64 values.** `variants = [...][:64]` silently drops values beyond 64.
  - Command: `for d in x0 x1 ... x63 lake/raw; do rm -rf $d; done`
- **(b) The variable is not bound after the loop.** Bash keeps the last value; the hook does not.
  - Command: `for d in lake/raw; do :; done; rm -rf $d`
- **(c) A `cd` through the loop variable is not followed.** The cwd update at `:1354-1369` uses the unbound `variables`.
  - Command: `for d in lake/raw; do cd $d && rm -f a.parquet; done`
- **Impact:** files in `lake/` are deleted.
- **Fix:** refuse rather than truncate when the variants exceed the cap. Keep the old for-list path check for items that resolve inside `DATA_ZONES + SELF_ZONES` (or settings files). The false positive in fp6 came from `agent-hooks/guard.py` in a read loop; the body is still checked through the variable, so a list item in a protected zone with a read-only body could be allowed specifically.
- **Effort:** S.

**M2. Candidate 7 fails open when `git diff` fails.**
- **Where:** `pre_tool_use.py:680-688`.
- **Evidence:** `check=False`, and `result.returncode` is never read. Only `OSError`/`SubprocessError` are caught (`:721-724`).
- **Command:** `cd "$(git rev-parse --show-toplevel)" && git commit -m x` with a staged `ghp_` token. The hook's cwd becomes `ROOT/"$(git rev-parse --show-toplevel)"`, which does not exist. `git -C` exits 128 with empty stdout, so the commit is allowed. The same happens for any unresolved `cd $VAR`, and for `git diff HEAD` on an unborn branch.
- **Fix:** refuse ("could not be read for secrets") when any `returncode != 0`.
- **Effort:** S.

**M3. Candidate 7 does not see the dominant idiom, and its parser can print the secret.**
- **Where:** `_commit_diff:667-688`, `_secret_in_diff:691-707`.
- **(a) Same-command staging.** The hook runs before the whole command. In `git add f && git commit -m x` (as in fixture fp4/fp5), the change from `git add` is not yet in the index, and an untracked new file appears in no `git diff`. So the most common commit form is never checked. The docs say "the index, plus what `-a` or pathspecs add", which is accurate but silent on this.
- **(b) A content line starting with `++ ` is read as a header.** The added row is then `+++ ...`, which `_secret_in_diff` takes as a file header. That line is not scanned, and `path` is set to the line's text. With the content `"++ " + TOKEN + "\n" + TOKEN + "\n"`, the second line triggers the refusal, which prints `({path}:{line})` with path equal to the first token. **The secret reaches the agent transcript through stderr.**
- **Fix:**
  - (a) Collect the pathspecs of earlier `git add` segments in the same `_walk`. Add `git diff HEAD -- <them>`, plus `git ls-files -o --exclude-standard -z -- <them>` read as files (secrets names excluded). Or document the gap explicitly.
  - (b) Treat `+++ ` as a header only when it directly follows a `--- ` line that follows a `diff --git` line. Print a sanitized path, or only the file index.
- **Effort:** M for (a), S for (b).

**M4. "An issue state change through `gh api`" is narrower than the docstring and README claim.**
- **Where:** `pre_tool_use.py:758-760`, `_gh_api_call:764-798`.
- **Evidence:** only `-f/-F/--field/--raw-field` key names are read.
- **Commands that pass:**
  - `gh api -X PATCH repos/o/r/issues/71 --input body.json`. The file holds the state; the key recorded is the filename.
  - `gh api -X PATCH repos/o/r/issues/71 -fstate=closed`. The attached short form is ignored.
  - `gh api graphql -f query='mutation{closeIssue(input:{issueId:"I"}){clientMutationId}}'`. `closeIssue`, `reopenIssue`, `deleteIssue` and `transferIssue` are not in `GH_GRAPHQL_WRITES`.
  - an endpoint with a `?query` suffix.
- **Same parser, older gap:** `gh api repos/o/r/pulls -fhead=x -fbase=main -ftitle=t` is seen as a GET, so a PR can be created. This is pre-existing at 69b032e, not a regression. Whether gh accepts `-fvalue` (pflag shorthand) is under "Unable to verify".
- **Fix:**
  - Parse attached `-f/-F` values.
  - Refuse any non-GET call on `.../issues/N` with `--input` (or one carrying the state).
  - Add `closeIssue|reopenIssue|deleteIssue|transferIssue` to the GraphQL refusal.
  - Strip the query string before matching the endpoint regex.
- **Effort:** S.

**M5. A heredoc fed to a shell or python with an option value is treated as data.** This contradicts the claim, but is not a regression: the old hook stripped every heredoc body.
- **Where:** `_shell_reads_stdin:1014-1019`, `_python_reads_stdin:1036-1045`.
- **Commands:**
  - `bash -o pipefail <<'X'\nrm -rf lake\nX`
  - `bash -euo pipefail <<'X' ...`
  - `python3 -W ignore - <<'X'\nimport shutil; shutil.rmtree('lake')\nX`
- **Related:** `_python_code:1029-1030` also does not skip the value of `-W`/`-X`, so `python -X dev -c "..."` is never parsed with `ast`.
- **Fix:** share one option parser that knows which options take a value (`-o`, `-O`, `--rcfile` for shells; `-W`, `-X` for python).
- **Effort:** S.

### Low

**L1. `case ... )` pops the subshell scope.** This is a regression for the subshell form.
- **Where:** `run():327-330` and `_walk:1318-1321`. A `case` pattern's `)` is treated as a subshell close. Inside `$( )` it also ends the substitution early.
- **Commands:**
  - `(cd lake; case x in *) rm -f a.parquet;; esac)`
  - `echo $(cd lake; case x in *) rm -f a.parquet;; esac)`
- The old hook kept the cwd at `lake` and refused both.
- **Fix:** track `case`/`esac`. A `)` while inside a `case` is a pattern terminator.

**L2. `\r` is a separator for the lexer but not for bash.**
- **Where:** `:315`, `:370`.
- **Command:** `echo x\r#$(rm -rf lake)`. The lexer sees `#` as a comment; bash sees one word and runs the substitution. The old hook refused it.
- **Fix:** treat `\r` as an ordinary character, as bash does.

**L3. cyclebeat.cli: argparse abbreviations, and a doc claim that does not match the code.**
- **Where:** `_cli_rule:816-855`.
- **Commands:**
  - `python -m cyclebeat.cli --la lake ingest`. argparse `allow_abbrev` is on by default; `--la` is not recognised, so the subcommand is taken to be `lake`. Pre-existing.
  - `python -m cyclebeat.cli --lake /tmp/x ingest --liv`. `--liv` is `--live` and fills `data/spike/.cache` (`cyclebeat/cli.py:24,48-51`). Old allowed it too.
- **Doc mismatch:** `docs/permissions.md` says "`--lake <dir outside the repo zones>`", but the code checks `DATA_ZONES` only. `--lake agent-hooks ingest` writes parquet files under `agent-hooks/`. Old allowed it too.
- **Fix:** match long-option prefixes the way argparse does. Check `--lake` with `_write_refusal`.

**L4. python `ast` heuristic: attached forms and aliases are missed.** All pre-existing; not regressions.
- **Missed forms:**
  - `python "-cimport shutil;shutil.rmtree('lake')"` (attached `-c`)
  - `import shutil as s; s.rmtree('lake')` (`PY_FUNC_MODULES` holds module names, not aliases)
  - `import duckdb as d; d.connect('data/x.duckdb')`
  - `import subprocess as sp; sp.run([...])`
- **Fix:** resolve `import ... as` aliases from the AST.

**L5. Long-standing gaps, already present at 69b032e.**
- `$'\x2eenv'` and `$".env"` are not decoded.
- `${x:-.env}` / `${x:-lake}` defaults are not checked.
- A brace with more than 256 alternatives hides `.env` (`_brace_expand` limit).
- A digit-only argument before a redirect is dropped (`rm -rf 2024 >/dev/null` inside `lake/`).
- `D=lake; D=/tmp | true; rm -rf $D` and `cd lake; cd /tmp | true; rm -f x`: a pipeline element is a subshell, but the hook keeps its assignment and its cd.
- `_current_branch` returns `None` on a timeout, so a bare push from `main` is allowed (fail-open).

**L6. Candidate 7 excludes `*.pem`/`*.key`/`id_*` from its read.**
- **Where:** `:673`.
- A key file staged through a directory (`git add certs/`, which passes because no word is a secret name) is never checked.
- **Fix:** add `git diff --cached --name-only`. It reads names only, no content. Refuse any staged path where `is_secret` is true.

**L7. Pathological inputs: all fail closed.**
- `BRACE` (`\{([^{}]*,[^{}]*)\}`) is O(n²) on `{` followed by many commas. Pre-existing.
- `_py_strings` fans out across many reassignments of the same name, up to N³ at depth 3.
- Deep `$(` nesting gives a `RecursionError`, which `main()` turns into exit 2.
- So none of these lets a command through, but they can burn the 10 s budget. Budget: `_roots` 3 s + up to 3×2 s of `git diff` + 3 s for `_current_branch`, plus one `_staged_rule` per loop variant when the commit uses the loop variable. A timeout then falls back to `onFailure: "block"`; that semantics is under "Unable to verify".
- The new secret regexes (`:172-175`) carry no catastrophic backtracking risk: each repetition is delimited by a space.

**L8. Tests and docs: the evidence and the wording do not match.**
- The test docstring (`tests/unit/test_agent_hook.py`, header) says the `pin:` mutations are recorded in `docs/ai-workflow.md`, but `grep -n '#71' docs/ai-workflow.md` returns nothing on this branch. The red-first and mutation evidence is not there yet.
- `pin: cyclebeat.cli ingest, scratch lake` and `pin: ... load, scratch db` pin verdicts the old hook gave only through its misparse (`sub = "/tmp/..."`), not through a guard.
- CLAUDE.md's pitfall "issue #45: the hook refuses `gh issue close` only, not reopen, delete, transfer or `gh api` state changes" is now stale. Hook docstring `:63` ("an issue state change through `gh api`") overclaims; see M4.
- None of H1–H4 or M1–M3 is covered by a test.

## Fail-closed and secret handling (priorities 2 and 3), summary

- **What holds:**
  - `Unparsable` returns a refusal (`:1309-1310`).
  - `ast` `SyntaxError`/`ValueError` returns a refusal (`:1260-1261`).
  - Any other exception becomes exit 2 (`:1546-1547`).
  - A `TimeoutExpired` in `_commit_diff` is a `SubprocessError`, which gives a refusal.
  - Non-UTF-8 output goes through `errors="replace"`.
  - The hook never names `.env` to git except as `:(exclude,glob)**/.env`. `tests/...::test_the_change_to_commit_never_includes_env` holds this.
  - The refusal text omits the matched value. One exception: M3(b).
- **Open:** a git error is ignored (M2).

## Unable to verify

- **Comments 6518839171 and 6518942958 on issue #71:** `gh issue view` is outside my list, so the owner's decisions were not compared with the code.
- **The H/M/L reproductions through `decide()`:** `uv run python` is outside my list. Script for the main agent: a quoted heredoc, so bash executes none of the strings.
  ```bash
  uv run python - <<'EOF'
  import importlib.util
  spec = importlib.util.spec_from_file_location("hook", "agent-hooks/pre_tool_use.py")
  hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)
  items = " ".join(f"x{i}" for i in range(64))
  cases = [
      "echo ${x:-$(rm -rf lake)}", "echo ${x:-$(cat .env)}",
      "grep -e. .env", "rg -e. .env", "echo .env | xargs cat", "echo cat .env | sh",
      "bash -euo pipefail -c '\nrm -rf lake\n'",
      "find /tmp -maxdepth 0 -exec sh -c '\ncat .env\n' \\;",
      f"for d in {items} lake/raw; do rm -rf $d; done",
      "for d in lake/raw; do :; done; rm -rf $d",
      "for d in lake/raw; do cd $d && rm -f a.parquet; done",
      "(cd lake; case x in *) rm -f a.parquet;; esac)",
      "echo $(cd lake; case x in *) rm -f a.parquet;; esac)",
      "echo x\r#$(rm -rf lake)",
      "bash -o pipefail <<'X'\nrm -rf lake\nX",
      "gh api -X PATCH repos/o/r/issues/71 -fstate=closed",
      "gh api graphql -f query='mutation{closeIssue(input:{issueId:\"I\"}){clientMutationId}}'",
      "uv run python -m cyclebeat.cli --la lake ingest",
      "uv run python -m cyclebeat.cli --lake /tmp/x ingest --liv",
  ]
  for c in cases:
      ev = {"tool_name": "Bash", "tool_input": {"command": c}, "cwd": str(hook.ROOT)}
      print(repr(c[:70]), "->", hook.decide(ev, branch_of=lambda _c: "feature", staged_of=lambda _c, _a: ""))
  EOF
  ```
  Expected per this report: `None` for every case.
- **The same cases against 69b032e,** to confirm the regressions. Run the same loop on a copy of `git show 69b032e:agent-hooks/pre_tool_use.py` saved in the scratchpad, and drop `staged_of` (the old `decide` has no such parameter).
- **The red-first claim for each #71 case.** I traced about 20 by hand; they are consistent, except that the two cli `pin:` cases rest on the old misparse (L8). A full replay needs the old module, as above.
- **`onFailure: "block"`, and how a hook timeout is handled in Claude Code:** not checked against the official docs.
- **gh/pflag `-fvalue` attached shorthand** (M4 and the `-fhead=` PR creation): needs the gh manual or a dry run against a fake host.
- **When bash reads a heredoc that opens on a line containing a multi-line `$(`,** and whether a `$'EOF'` delimiter is decoded: needs the bash manual or a test.

## Prioritized action plan

1. **Quick win.** H2 + H3: never mark a word inert when `is_secret(word)`. One line in `_segment_rule`/`_data_words`; closes `grep -e. .env` and `echo .env | xargs cat`.
2. **Quick win.** H1: lex `${...}` with depth, recording `$(`/backticks into `tok.subs`.
3. **Quick win.** M2: refuse when `git diff` returns non-zero.
4. **Quick win.** M1: refuse when the variants exceed 64, and restore the protected-path check on for-list items.
5. **Quick win.** M3(b): stricter header parsing in `_secret_in_diff`; never print a content-derived path.
6. H4 + M5: one shell/python option parser (`-o X`, `-O X`, `+o`, `-W X`, `-X X`). Add `find -exec <shell> -c`, `sudo ... <shell> -c` and `ssh` to the nested-script analysis.
7. M4: attached `-f`, `--input`, the GraphQL issue mutations, and the query string in the endpoint.
8. M3(a): include same-command `git add` paths, or document the gap in `docs/permissions.md` and the README.
9. Tests: add every command above as DENIED, shown green on 69b032e where this report says it was refused there, and red on 0ef6e38. Record the replay and the `pin:` mutations in `docs/ai-workflow.md`.
10. Docs: fix "outside the repo zones" (L3) and the stale CLAUDE.md pitfall about #45 (L8).
11. L1, L2, L4–L7 as a follow-up issue.

## Relevant files

- /home/ellie/projets/cyclebeat/agent-hooks/pre_tool_use.py
- /home/ellie/projets/cyclebeat/security/pr-audits/pr-71-hook.patch
- /home/ellie/projets/cyclebeat/tests/unit/test_agent_hook.py
- /home/ellie/projets/cyclebeat/tests/fixtures/hook_false_positives.json
- /home/ellie/projets/cyclebeat/docs/permissions.md
- /home/ellie/projets/cyclebeat/agent-hooks/README.md
- /home/ellie/projets/cyclebeat/cyclebeat/cli.py
- /home/ellie/projets/cyclebeat/.claude/settings.json
- /home/ellie/projets/cyclebeat/CLAUDE.md

---

## Triage (main agent, not part of the raw output)

Not done yet: the auditor's reproduction script is to be run against 0ef6e38 and 69b032e
before any finding is accepted or rejected, then the owner decides the fixes (a second patch,
owner-applied as the first). Raw output first, at the owner's request.
