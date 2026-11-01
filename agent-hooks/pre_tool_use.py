#!/usr/bin/env python3
"""PreToolUse guardrail for coding agents on CycleBeat (criterion 12, docs/permissions.md).

Claude Code runs this before every tool call (`.claude/settings.json`) and passes the call as
JSON on stdin. Exit 2 blocks the call and the stderr line is the reason the agent sees; exit 0
lets the normal permission flow decide. Any internal error also exits 2 (fail closed), and the
settings declare `"onFailure": "block"` so a crash, a timeout or a missing interpreter blocks
too.

What it refuses (owner decisions, 2026-10-11):

* any write to `data/` or `lake/`, by a file tool or by a shell command, including the commands
  that write them without naming them (`make ingest`, `make dbt`, `dbt build`, ...) unless
  `RUNTIME_DB_PATH=` points outside `data/`;
* any read or write of a secrets file (`.env` and variants, private keys, `.netrc`, `.pgpass`);
* `git push` with force in any form, and any push to `main`;
* `git merge` into `main`;
* `gh pr create`, `gh pr merge`, and the GitHub merge API;
* any call to the Render API or deploy hooks, and running `tools/deploy.py`;
* any write to this folder or to Claude Code settings files (the agent cannot loosen its own
  guardrails).

Added after the phase-10 audit of PR #38 (owner decisions, 2026-10-20):

* `git clean` in every form (it deletes ignored files: `lake/`, `data/*.duckdb`, `.env`);
* a recursive `rm` on a glob or a brace pattern, and `find` with `-delete` / `-exec` whose start
  path contains `data/` or `lake/` (`rm -rf *` and `find . -delete` from the repo root);
* the script of `bash -c`, `sh -c` (and zsh, dash, ksh) and `eval`, checked by the same rules;
* a brace pattern that expands to a secrets file (`cat .e{n,}v`);
* a recursive search or archive (`grep -r`/`-R`, `rg -uu` or `--hidden --no-ignore`, `tar -c`,
  `zip -r`) run on the repo root, one of its parents or `~`, unless the command excludes
  `.env*` explicitly (`--exclude='.env*'`, `-g '!.env*'`, `-x '.env*'`). Purely textual: no
  file is looked up, so the rule behaves the same in CI;
* `gh api` routes to a merge or to `main`: GraphQL `mergePullRequest` (and `createPullRequest`,
  `createCommitOnBranch`), `POST .../pulls`, and `PUT`/`DELETE .../contents/...` on `main`.

Added with issue #44 (owner decision, 2026-10-22): `gh issue close` and `gh issue edit --state`;
the merged PR closes an issue (`Closes #N`), never the agent. Label edits stay allowed.

Added with issue #71 (owner decisions, 2026-10-30), as rules added to this hook one at a time:

* A1. `git commit` when the change it records adds a private key header or a known token prefix
  (GitHub, AWS), or stages a secrets file by its name (`.env`, `*.pem`, `*.key`, `id_*` but not
  `*.pub`). What it records: the index, `-a`, pathspecs (on an unborn branch too), and a `git
  add` in an earlier segment of the same command. Secrets files are named, never read: the
  hook never reads `.env`. A refusal names the pattern and the file, never a line of content
  nor a file name holding a token. The hook's git calls run no code of the repository
  (`core.fsmonitor` off, no pager, no submodule, no textconv or external diff; a clean or
  process filter in the repository's own config refuses the commit unrun). A git error or the
  6 s budget refuses the commit. gitleaks in CI stays the net for everything else.
* A2. `gh issue reopen`, `delete` and `transfer`; through `gh api`, a non-GET call on
  `repos/O/R/issues/N` (a query string ignored) with a `state` or `state_reason` field (`-f`,
  `-F`, attached `-fkey=`) or any `--input` body; the GraphQL mutations `closeIssue`,
  `reopenIssue`, `deleteIssue`, `transferIssue`, and `updateIssue` with a `state:`; a GraphQL
  query read from a file or stdin (`query=@file`, `--input`), which cannot be checked. An
  attached `-fkey=value` counts as a body, so `gh api .../pulls -fhead=...` is a POST.
* A3. A value glued to a short flag, or to a cluster of them, is checked as a secrets name
  too: `grep -f.env`, `grep -if.env`, `git commit -F.env`, `-aF.env`, `-t.env`, `git tag
  -F.env`.
* A4. `python -m cyclebeat.cli`: the subcommand is read as argparse reads it, after `--lake
  VALUE` and its unique prefixes (`--la lake ingest` is `ingest`). `ingest` passes only with a
  `--lake` outside the protected zones and no `--live`; `resolve` and `extract-app` are refused.
* A5. A heredoc fed to a shell or `eval` (a shell word on the line that opens it: `bash
  <<EOF`, `cat <<EOF | sh`, `{ sh; } <<EOF`) is checked as lines of the script; a heredoc fed
  to `xargs` is checked as the arguments it becomes. Any other heredoc stays data.
* A6. The script of every `$(...)` and backtick outside single quotes, double quotes
  included (`echo "$(rm -rf lake)"`, ``echo "`cat .env`"``), goes through the same rules.
* A7. `python -c` code and a heredoc fed to python are read with `ast`, never run. Refused:
  a secrets file name; a protected path given to a write call (`open` for writing, pathlib,
  `os` and `shutil` writes, `duckdb.connect` without `read_only=True`, ...); a `subprocess` or
  `os.system` call whose literal command these rules refuse; code that does not parse. A
  heuristic that reads the code: a path built at runtime, `exec`, `getattr`, an encoding,
  code attached to `-c` (`-cCODE`) or a module imported under an alias is not seen.
* A8. A segment that starts with a shell keyword (`do`, `then`, `else`, `elif`, `if`,
  `while`, `until`, `!`, `{`) is checked twice, as it is and without the keywords: `for x in
  1; do rm -rf lake; done` is checked as `rm -rf lake` too.

Relaxed with issue #71 (owner decisions, 2026-10-30), one at a time, each kept only with
no regression against 69b032e on the replay (security/pr-audits/pr-71-replay.py) and not put
in question by the fourth security-auditor pass. B1, B2, B4 and B5 were tried and removed
(security/pr-audits/pr-71-security-auditor-4.md); their false positives are listed under
Limits in docs/permissions.md:

* B3. `python -m cyclebeat.cli SUBCOMMAND ... --help` (the exact word `--help` or `-h`, before
  any `--`) is allowed: argparse prints the help and exits before any work. `--hel` stays
  refused.
* B6. `git hash-object` without `-w` (alone or in a short-option cluster) is read-only.

It reads command TEXT. It stops mistakes, not an adversary: `python -c` with a computed path
gets through. The deny rules of `.claude/settings.json` and the auto-mode classifier are the
other layers. Standard library only, so it runs before any virtualenv exists.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_NAMES = (".env", ".ENV", ".netrc", ".pgpass", "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")
SECRET_GLOBS = (".env.*", ".ENV.*", "*.pem", "*.key", "*.p12", "*.pfx")
SECRET_ALLOWED = (".env.example",)
# A shell glob reaches a secret only if it can: bash `*` skips dotfiles, so a glob has to start
# with `.` to hit `.env` (it is then matched against these), or name key material itself
# (`id_*`, `*.pem`, `*.key`, ...).
DOT_PROBES = (".env", ".env.local", ".ENV", ".netrc", ".pgpass")
KEY_SUFFIXES = (".pem", ".key", ".p12", ".pfx")

OPERATORS = {";", "&&", "||", "|", "&", "|&", "(", ")", ";;"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<", "<<", "<<<", "<>", ">&", "<&"}
WRAPPERS = {"sudo", "env", "command", "time", "nohup", "nice", "exec", "xargs", "timeout"}

# Commands allowed to NAME a protected path because they only read it.
READ_ONLY = {
    "ls", "stat", "du", "df", "wc", "file", "find", "cat", "head", "tail", "less", "more",
    "grep", "rg", "egrep", "fgrep", "sha256sum", "sha1sum", "md5sum", "cksum", "diff", "cmp",
    "tree", "realpath", "readlink", "basename", "dirname", "test", "[", "echo", "printf",
    "cd", "pwd", "sed", "awk", "sort", "uniq", "cut", "jq", "git", "ruff", "true",
}
GIT_READ = {
    "status", "diff", "log", "show", "ls-files", "ls-tree", "blame", "rev-parse",
    "check-ignore", "grep", "shortlog", "cat-file", "describe", "whatchanged",
}
# Git subcommands that only touch the index: staging a file does not write it.
GIT_STAGE = {"add", "commit"}
FIND_WRITES = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0",
               "-fprintf", "-fls"}
# Commands whose bare-word arguments (no slash) are paths: `rm -rf data`.
FILE_MUTATORS = {
    "rm", "rmdir", "mv", "cp", "touch", "mkdir", "ln", "chmod", "chown", "truncate", "dd",
    "tee", "install", "rsync", "unlink", "shred", "sed", "patch", "cd", "find",
}
COPIERS = {"cp", "rsync", "install"}
MAKE_WRITES_LAKE = {"ingest", "ingest-live", "compose-pipeline", "compose-build"}
MAKE_WRITES_DB = {"dbt"}
DBT_WRITES = {"build", "run", "seed", "snapshot", "test"}
CLI_WRITES_LAKE = {"ingest", "resolve", "extract-app"}
CLI_WRITES_DB = {"load"}
PIPELINE_SERVICES = {"pipeline", "ingest", "dbt", "airflow"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# A8 (#71): words bash reads before the command of a segment; the command is the next word.
SHELL_KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{"}
PY_VALUED = {"-W", "-X"}
PYTHON = re.compile(r"python(\d+(\.\d+)?)?")
MAX_NESTING = 3
GREP_HEADS = {"grep", "egrep", "fgrep"}
# Options whose value is a pattern or a count, never a search target.
GREP_VALUED = {"-e", "-f", "--regexp", "--file", "-m", "--max-count", "-A", "-B", "-C",
               "--include", "--exclude", "--exclude-dir", "--exclude-from", "--label"}
RG_VALUED = {"-e", "-f", "--regexp", "--file", "-g", "--glob", "--iglob", "-t", "--type",
             "-T", "--type-not", "-m", "--max-count", "-A", "-B", "-C", "-M", "--max-columns"}
# Options whose value excludes paths: a value there is never a read of a secret.
EXCLUDE_OPTIONS = {"--exclude", "--exclude-dir", "-g", "--glob", "--iglob", "-x"}
GH_API_VALUED = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "-H", "--header",
                 "--input", "-q", "--jq", "-t", "--template", "--hostname", "-p", "--preview",
                 "--cache"}
GH_GRAPHQL_WRITES = re.compile(
    r"mergePullRequest|createPullRequest|createCommitOnBranch|enablePullRequestAutoMerge"
)
# A2 (#71): the GraphQL mutations that change an issue's state.
GH_GRAPHQL_UPDATE_STATE = re.compile(r"\bupdateIssue\b[\s\S]*\bstate\s*:")
GH_GRAPHQL_ISSUE_STATE = re.compile(r"\b(?:closeIssue|reopenIssue|deleteIssue|transferIssue)\b")

# A7 (#71): calls that write what their arguments name.
PY_OPEN_WRITE = re.compile(r"[wax+]")
PY_METHOD_WRITES = {"write_text", "write_bytes", "unlink", "rmdir", "mkdir", "touch", "rename",
                    "symlink_to", "hardlink_to", "to_parquet", "to_csv", "to_json",
                    "write_table", "write_dataset"}
PY_FUNC_WRITES = {"remove", "unlink", "rmdir", "removedirs", "makedirs", "mkdir", "rename",
                  "replace", "truncate", "rmtree", "move", "copy", "copy2", "copyfile",
                  "copytree", "symlink", "link", "write_table", "write_dataset"}
PY_FUNC_MODULES = {"os", "shutil", "pq", "pathlib"}
PY_COPIES = {"copy", "copy2", "copyfile", "copytree"}  # the first argument is only read
PY_RUNS = {"run", "call", "check_call", "check_output", "Popen", "system", "popen",
           "getoutput", "getstatusoutput"}
PY_RUN_MODULES = {"subprocess", "os"}


BranchOf = Callable[[Path], str | None]
# (git dir, `git commit` arguments, paths `git add` staged earlier in the same command)
StagedOf = Callable[[Path, list[str], list[str]], str]

# A1 (#71). Private key headers: RFC 7468 (https://www.rfc-editor.org/rfc/rfc7468), plus the
# OpenSSH and PGP labels. GitHub prefixes: https://docs.github.com/en/authentication/keeping-
# your-account-and-data-secure/about-authentication-to-github#githubs-token-formats. AWS key
# ID prefixes: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html
STAGED_SECRETS = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
)
# Any of these in a file name is never printed in a refusal: unanchored on purpose.
STAGED_SANITIZE = re.compile(r"gh[pousr]_|github_pat_|AKIA|ASIA|PRIVATE KEY")
# Every git call of the commit check: no fsmonitor hook, no pager, no submodule recursion.
# textconv and external diff drivers are turned off on the diff command lines themselves.
GIT_SAFE = ["--no-pager", "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false"]
# A line `_commit_diff` adds for each staged file name; git diff never starts a line so.
STAGED_NAME = "staged-name "
# Total time the read of the change to commit may take (the hook has 10 s in all).
STAGED_BUDGET_S = 6.0
UNTRACKED_READ_LIMIT = 1_000_000
COMMIT_VALUED = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c",
                 "--reedit-message", "--author", "--date", "--fixup", "--squash", "--cleanup",
                 "--trailer", "-t", "--template", "--pathspec-from-file"}


# ── Paths ───────────────────────────────────────────────────────────────────────────────


def _roots() -> list[Path]:
    """This checkout and, from a worktree, the main checkout: both hold a real `data/`."""
    roots = [ROOT]
    try:
        common = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=3, check=False,
        ).stdout.strip()
        if common:
            main_root = Path(common).parent
            if main_root != ROOT:
                roots.append(main_root)
    except (OSError, subprocess.SubprocessError):
        pass
    return roots


ROOTS = _roots()
DATA_ZONES = [r / name for r in ROOTS for name in ("data", "lake")]
SELF_ZONES = [r / "agent-hooks" for r in ROOTS]


def _resolve(token: str, cwd: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(token)))
    if not path.is_absolute():
        path = cwd / path
    return path.resolve(strict=False)


def _inside(path: Path, zones: list[Path]) -> bool:
    return any(path == zone or path.is_relative_to(zone) for zone in zones)


def is_secret(token: str) -> bool:
    name = token.rstrip("/").rsplit("/", 1)[-1]
    if name in SECRET_ALLOWED:
        return False
    if name in SECRET_NAMES or any(fnmatch.fnmatchcase(name, g) for g in SECRET_GLOBS):
        return True
    if any(ch in name for ch in "*?["):
        return _secret_glob(name)
    return False


def _secret_glob(name: str) -> bool:
    if name.startswith("."):
        return any(fnmatch.fnmatchcase(probe, name) for probe in DOT_PROBES)
    return name.startswith("id_") or name.lower().endswith(KEY_SUFFIXES)


BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")


def _brace_expand(word: str, limit: int = 256) -> list[str]:
    """Bash brace expansion, enough to see `.e{n,}v` or `{.,}env` spell a secret."""
    match = BRACE.search(word)
    if not match:
        return [word]
    head, tail = word[: match.start()], word[match.end() :]
    out: list[str] = []
    for alternative in match.group(1).split(","):
        out.extend(_brace_expand(head + alternative + tail, limit))
        if len(out) >= limit:
            break
    return out[:limit]


def _is_pattern(word: str) -> bool:
    return any(ch in word for ch in "*?[") or bool(BRACE.search(word))


def _is_settings(path: Path) -> bool:
    return path.parent.name == ".claude" and path.name in ("settings.json", "settings.local.json")


def _write_refusal(path: Path) -> str | None:
    if _inside(path, DATA_ZONES):
        return f"writes to data/ and lake/ are refused ({path.name})"
    if _inside(path, SELF_ZONES):
        return "the guardrail itself (agent-hooks/) can only be changed by the owner"
    if _is_settings(path):
        return "Claude Code settings files can only be changed by the owner"
    return None


# ── Shell parsing ───────────────────────────────────────────────────────────────────────


def _heredoc_reader(line: str) -> str:
    """What reads a heredoc opened on `line` (A5, #71): "script" when a shell or `eval` is a
    word of the line (`bash <<EOF`, `cat <<EOF | sh`, `{ sh; } <<EOF`), "args" when `xargs`
    is, else "" (data)."""
    names = {_base(w) for w in re.findall(r"[A-Za-z0-9_./-]+", line)}
    if names & (SHELLS | {"eval"}):
        return "script"
    return "args" if "xargs" in names else ""


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: text fed on stdin is data, not paths or commands. A5 (#71): a body
    fed to a shell is kept as lines of the script; a body fed to `xargs` becomes words of the
    line that opened it, the arguments xargs turns it into."""
    lines = command.split("\n")
    out: list[str] = []
    pending: list[tuple[str, bool, str, int]] = []
    for line in lines:
        if pending:
            word, dash, reader, at = pending[0]
            if (line.lstrip("\t") if dash else line) == word:
                pending.pop(0)
            elif reader == "script":
                out.append(line)
            elif reader == "args":
                out[at] += " " + line
            continue
        out.append(line)
        for match in re.finditer(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", line):
            pending.append(
                (match.group(3), match.group(1) == "-", _heredoc_reader(line), len(out) - 1)
            )
    return "\n".join(out)


def _substitutions(text: str) -> list[str]:
    """A6 (#71): the scripts of `$(...)` and backticks outside single quotes, double quotes
    included (`echo "$(rm -rf lake)"`), which `_tokens` leaves inside a quoted word. A span
    left open runs to the end of the text."""
    spans: list[str] = []
    single = double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        elif not single and text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            spans.append(text[i + 2 : j - 1 if not depth else j])
            i = j
            continue
        elif not single and ch == "`":
            j = text.find("`", i + 1)
            j = len(text) if j < 0 else j
            spans.append(text[i + 1 : j])
            i = j + 1
            continue
        i += 1
    return spans


def _tokens(command: str) -> list[str]:
    text = _strip_heredocs(command).replace("\\\n", " ")
    text = text.replace("$(", " ; ").replace("`", " ; ")
    tokens: list[str] = []
    for line in text.split("\n"):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        try:
            tokens.extend(lexer)
        except ValueError:
            tokens.extend(line.split())
        tokens.append(";")
    return tokens


def _segments(tokens: list[str]) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """Split on shell operators. Each segment: (words, [(redirect op, target)])."""
    segments: list[tuple[list[str], list[tuple[str, str]]]] = []
    words: list[str] = []
    redirects: list[tuple[str, str]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in OPERATORS:
            if words or redirects:
                segments.append((words, redirects))
            words, redirects = [], []
        elif tok in REDIRECTS or (tok[-1:] in "<>" and tok.strip("<>&|") == ""):
            target = tokens[i + 1] if i + 1 < len(tokens) else ""
            if target not in OPERATORS:
                redirects.append((tok, target))
                i += 1
            if words and words[-1].isdigit():
                words.pop()
        else:
            words.append(tok)
        i += 1
    if words or redirects:
        segments.append((words, redirects))
    return segments


def _with_keywords_skipped(
    segments: list[tuple[list[str], list[tuple[str, str]]]],
) -> list[tuple[list[str], list[tuple[str, str]]]]:
    """A8 (#71): a segment that starts with shell keywords (`do rm -rf lake`) is checked twice,
    as it is and without them, so a rule can only add a refusal. As it is, its head is the
    keyword: no `cd`, `git` or other state change happens through it."""
    out: list[tuple[list[str], list[tuple[str, str]]]] = []
    for words, redirects in segments:
        out.append((words, redirects))
        i = 0
        while i < len(words) and words[i] in SHELL_KEYWORDS:
            i += 1
        if i and i < len(words):
            out.append((words[i:], redirects))
    return out


def _command(words: list[str]) -> tuple[dict[str, str], list[str]]:
    """Leading NAME=value assignments, then the words from the real command on."""
    env: dict[str, str] = {}
    i = 0
    while i < len(words) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i]):
        name, value = words[i].split("=", 1)
        env[name] = value
        i += 1
    rest = words[i:]
    while rest and rest[0] in WRAPPERS:
        rest = rest[1:]
        while rest and (rest[0].startswith("-") or re.fullmatch(r"[0-9.]+[smhd]?", rest[0])):
            rest = rest[1:]
        while rest and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", rest[0]):
            name, value = rest[0].split("=", 1)
            env[name] = value
            rest = rest[1:]
    if rest[:2] == ["uv", "run"]:
        rest = rest[2:]
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in ("--directory", "--project", "--with", "--group", "--extra", "--python"):
                rest = rest[1:]
    return env, rest


def _sub(words: list[str], takes_value: set[str]) -> tuple[str, list[str]]:
    """First non-option word after `words[0]` (skipping options that take a value)."""
    i = 1
    while i < len(words):
        word = words[i]
        if word in takes_value:
            i += 2
            continue
        if word.startswith("-"):
            i += 1
            continue
        return word, words[i + 1 :]
    return "", []


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


# ── Rules ───────────────────────────────────────────────────────────────────────────────


def _db_outside_data(env: dict[str, str], cwd: Path) -> bool:
    target = env.get("RUNTIME_DB_PATH", "")
    return bool(target) and not _inside(_resolve(target, cwd), DATA_ZONES)


def _git_rule(
    args: list[str], cwd: Path, branch_of: BranchOf, switched_to_main: bool
) -> str | None:
    sub, rest = _sub(["git", *args], {"-C", "-c", "--git-dir", "--work-tree"})
    if sub == "clean":
        return "git clean deletes ignored files (lake/, data/, .env): the owner's action"
    if sub == "merge":
        if switched_to_main or branch_of(cwd) == "main":
            return "merging into main is the owner's action"
    if sub != "push":
        return None
    positional: list[str] = []
    skip = False
    for word in rest:
        if skip:
            skip = False
            continue
        if word in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            skip = True
            continue
        if word.startswith("--"):
            name = word.split("=", 1)[0]
            if name in ("--force", "--force-with-lease", "--force-if-includes", "--mirror"):
                return f"force push is refused ({name})"
            if name == "--all":
                return "git push --all would push main"
            continue
        if word.startswith("-") and len(word) > 1:
            if "f" in word[1:]:
                return f"force push is refused ({word})"
            continue
        positional.append(word)
    refspecs = positional[1:]
    for spec in refspecs:
        if spec.startswith("+"):
            return f"force push is refused ({spec})"
        dst = spec.split(":", 1)[-1]
        if dst in ("main", "refs/heads/main"):
            return "pushing to main is refused: open a PR, the owner merges it"
        if dst == "HEAD" and branch_of(cwd) == "main":
            return "pushing to main is refused: open a PR, the owner merges it"
    if not refspecs and branch_of(cwd) == "main":
        return "pushing from main is refused: work on a branch"
    return None


def _gh_rule(words: list[str]) -> str | None:
    sub, rest = _sub(words, {"-R", "--repo", "--hostname"})
    if sub == "pr":
        action, _ = _sub(["pr", *rest], {"-R", "--repo"})
        if action in ("create", "new", "merge"):
            return f"gh pr {action} is the owner's action"
    if sub == "issue":
        # Issue #44: the merged PR closes an issue, never the agent. Label edits stay allowed.
        action, _ = _sub(["issue", *rest], {"-R", "--repo"})
        if action == "close":
            return "closing an issue is the merged PR's job, not the agent's"
        if action in ("reopen", "delete", "transfer"):  # A2 (#71)
            return f"gh issue {action} changes an issue's state: not the agent's action"
        if action == "edit" and any(w == "--state" or w.startswith("--state=") for w in rest):
            return "changing an issue's state is the merged PR's job, not the agent's"
        return None
    if sub != "api":
        return None
    if any(re.search(r"/pulls/\d+/merge\b|/merges\b", w) for w in rest):
        return "the GitHub merge API is the owner's action"
    text = " ".join(rest)
    if "graphql" in rest and GH_GRAPHQL_WRITES.search(text):
        return "this GraphQL mutation merges, opens a PR or commits to a branch: the owner's action"
    if "graphql" in rest and (
        GH_GRAPHQL_ISSUE_STATE.search(text) or GH_GRAPHQL_UPDATE_STATE.search(text)
    ):  # A2 (#71)
        return "this GraphQL mutation changes an issue's state: the merged PR's job"
    method, endpoint, fields = _gh_api_call(rest)
    if "graphql" in rest and (fields.get("query", "").startswith("@") or "--input" in fields):
        return "a GraphQL query read from a file or stdin cannot be checked: refused (A2)"
    if method == "POST" and re.search(r"(^|/)repos/[^/]+/[^/]+/pulls/?$", endpoint):
        return "opening a PR through the GitHub API is the owner's action"
    if method in ("PUT", "DELETE") and "/contents/" in endpoint:
        if fields.get("branch", "main") == "main":
            return "writing a file on main through the GitHub API is refused: open a PR"
    if method != "GET" and re.search(r"(^|/)repos/[^/]+/[^/]+/issues/\d+/?$", endpoint):
        if {"state", "state_reason", "--input"} & set(fields):  # A2 (#71) and M4
            return "changing an issue's state through the GitHub API is the merged PR's job"
    return None


def _gh_api_call(rest: list[str]) -> tuple[str, str, dict[str, str]]:
    """(HTTP method, endpoint without its query, fields) of `gh api ...`, as gh defaults them.

    `-fkey=value` attached and `--input FILE` count as a body (A2, #71); `--input` is recorded
    as a field of its own, since the file may set any key.
    """
    method = ""
    endpoint = ""
    fields: dict[str, str] = {}
    has_body = False
    i = 0
    while i < len(rest):
        word = rest[i]
        following = rest[i + 1] if i + 1 < len(rest) else ""
        if word in ("-X", "--method"):
            method, i = following.upper(), i + 2
        elif word.startswith("--method="):
            method, i = word.split("=", 1)[1].upper(), i + 1
        elif word.startswith("-X") and len(word) > 2:
            method, i = word[2:].upper(), i + 1
        elif word in ("--input",) or word.startswith("--input="):
            has_body = True
            fields["--input"] = word.split("=", 1)[1] if "=" in word else following
            i += 1 if "=" in word else 2
        elif word in ("-f", "-F", "--field", "--raw-field"):
            has_body = True
            key, _, value = following.partition("=")
            fields[key] = value
            i += 2
        elif word.startswith(("--field=", "--raw-field=")):
            has_body = True
            key, _, value = word.split("=", 1)[1].partition("=")
            fields[key] = value
            i += 1
        elif word.startswith(("-f", "-F")) and not word.startswith("--") and len(word) > 2:
            has_body = True
            key, _, value = word[2:].partition("=")
            fields[key] = value
            i += 1
        elif word in GH_API_VALUED:
            i += 2
        else:
            if not word.startswith("-") and not endpoint:
                endpoint = word.split("?", 1)[0]
            i += 1
    if not method:
        method = "POST" if has_body else "GET"
    return method, endpoint, fields


def _render_rule(words: list[str], redirects: list[tuple[str, str]]) -> str | None:
    text = " ".join(words + [t for _, t in redirects])
    if re.search(r"api\.render\.com|render\.com/deploy|dashboard\.render\.com", text):
        return "calls to the Render API or deploy hooks are refused"
    if re.search(r"\$\{?RENDER_", text):
        return "Render credentials are not used from an agent session"
    if any(w == "tools.deploy" for w in words) or (
        any(w.endswith("tools/deploy.py") for w in words)
        and any(_base(w).startswith("python") for w in words)
        and not any(_base(w) == "pytest" for w in words)
    ):
        return "running tools/deploy.py deploys to Render: the owner's action"
    return None


def _asks_help(args: list[str]) -> bool:
    """B3 (#71): the exact word `--help` or `-h` among the subcommand's words, before any `--`."""
    for word in args:
        if word == "--":
            return False
        if word in ("--help", "-h"):
            return True
    return False


def _cli_rule(args: list[str], cwd: Path) -> str | None:
    """A4 (#71): the real subcommand of `python -m cyclebeat.cli`, read as argparse reads it.

    The only top-level option with a value is `--lake` (`cyclebeat/cli.py`); argparse accepts
    a unique prefix of it (`--la lake`). `ingest` passes only with a `--lake` outside the
    protected zones and no `--live` (nor any other `--l...` word but `--limit`) after it:
    without `--live` it writes the lake it is given and nothing else. Every other writing
    subcommand is refused, whatever its options.
    """
    lake: str | None = None
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if len(args[i]) >= 3 and "--lake".startswith(args[i]) and i + 1 < len(args):
            lake, i = args[i + 1], i + 2
        else:
            i += 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1 :]
    if sub == "ingest":
        live = any(w.startswith("--l") and w.split("=", 1)[0] != "--limit" for w in rest)
        if lake is None or live or _write_refusal(_resolve(lake, cwd)):
            return "cyclebeat.cli ingest writes lake/ and data/"
        return None
    if sub in CLI_WRITES_LAKE:
        return f"cyclebeat.cli {sub} writes lake/ and data/"
    return None


def _pipeline_rule(env: dict[str, str], cmd: list[str], cwd: Path) -> str | None:
    if not cmd:
        return None
    head = _base(cmd[0])
    if head == "make":
        targets = {w for w in cmd[1:] if not w.startswith("-") and "=" not in w}
        if targets & MAKE_WRITES_LAKE:
            return f"make {' '.join(sorted(targets & MAKE_WRITES_LAKE))} writes lake/ and data/"
        if targets & MAKE_WRITES_DB and not _db_outside_data(env, cwd):
            return "make dbt writes data/: prefix RUNTIME_DB_PATH=<path outside data/>"
    if head == "dbt" and set(cmd[1:2]) & DBT_WRITES and not _db_outside_data(env, cwd):
        return "dbt writes data/: prefix RUNTIME_DB_PATH=<path outside data/>"
    if head.startswith("python") and "-m" in cmd:
        module = cmd[cmd.index("-m") + 1] if cmd.index("-m") + 1 < len(cmd) else ""
        sub = next((w for w in cmd[cmd.index("-m") + 2 :] if not w.startswith("-")), "")
        if module == "ingest.ingest_pipeline":
            return "the ingest pipeline writes lake/"
        args = cmd[cmd.index("-m") + 2 :]
        after_sub = args[args.index(sub) + 1 :] if sub in args else []
        if module == "cyclebeat.cli" and _asks_help(after_sub):
            return None  # B3 (#71): argparse prints the help and exits before any work
        if module == "cyclebeat.cli":
            refusal = _cli_rule(cmd[cmd.index("-m") + 2 :], cwd)
            if refusal:
                return refusal
        if module == "cyclebeat.cli" and sub in CLI_WRITES_LAKE:
            return f"cyclebeat.cli {sub} writes lake/ and data/"
        if module == "cyclebeat.cli" and sub in CLI_WRITES_DB and not _db_outside_data(env, cwd):
            return "cyclebeat.cli load writes data/: prefix RUNTIME_DB_PATH=<path outside data/>"
    if head == "docker" and "compose" in cmd and set(cmd) & PIPELINE_SERVICES:
        if not ({"down", "ps", "logs", "config"} & set(cmd)):
            return "the compose pipeline profile mounts and writes data/ and lake/"
    return None


def _short_flags(cmd: list[str]) -> set[str]:
    """Letters of the short options (`-rf` gives r and f)."""
    return {ch for w in cmd[1:] if w.startswith("-") and not w.startswith("--") for ch in w[1:]}


def _contains_zone(path: Path) -> bool:
    return any(zone == path or zone.is_relative_to(path) for zone in DATA_ZONES + SELF_ZONES)


def _destructive_rule(head: str, cmd: list[str], cwd: Path) -> str | None:
    """Deletions that never name data/ or lake/ yet reach them (audit of PR #38, H2)."""
    if head == "rm" and ({"r", "R"} & _short_flags(cmd) or "--recursive" in cmd):
        patterns = [w for w in cmd[1:] if not w.startswith("-") and _is_pattern(w)]
        if patterns:
            return f"a recursive rm on a pattern ({patterns[0]}) can reach data/ and lake/"
    if head == "find" and set(cmd) & FIND_WRITES:
        starts: list[str] = []
        for word in cmd[1:]:
            if word.startswith("-") or word in ("(", "!", ")"):
                break
            starts.append(word)
        for start in starts or ["."]:
            if _contains_zone(_resolve(start, cwd)):
                return f"find {start} with -delete or -exec reaches data/ and lake/"
    return None


def _is_top(path: Path) -> bool:
    """The repo root, one of its parents, or the home folder: places that hold a `.env`."""
    home = Path.home().resolve()
    return any(path == root or root.is_relative_to(path) for root in ROOTS) or (
        path == home or home.is_relative_to(path)
    )


def _excluded(cmd: list[str]) -> set[int]:
    """Indexes of the words that are values of an exclusion option."""
    skip: set[int] = set()
    for i, word in enumerate(cmd):
        if word in EXCLUDE_OPTIONS and i + 1 < len(cmd):
            skip.add(i + 1)
        elif any(word.startswith(f"{opt}=") for opt in EXCLUDE_OPTIONS if opt.startswith("--")):
            skip.add(i)
    return skip


def _excludes_secrets(cmd: list[str]) -> bool:
    """The command excludes `.env*` itself (`--exclude='.env*'`, `-g '!.env*'`, `-x '.env*'`)."""
    for i in _excluded(cmd):
        value = cmd[i].split("=", 1)[1] if cmd[i].startswith("--") else cmd[i]
        value = value.lstrip("!")
        if all(fnmatch.fnmatchcase(probe, value) for probe in (".env", ".env.local")):
            return True
    return False


def _targets(cmd: list[str], valued: set[str], pattern_first: bool) -> list[str]:
    words: list[str] = []
    i = 1
    while i < len(cmd):
        word = cmd[i]
        if word in valued:
            i += 2
            continue
        if not word.startswith("-"):
            words.append(word)
        i += 1
    explicit_pattern = any(w in cmd for w in ("-e", "-f", "--regexp", "--file"))
    if pattern_first and not explicit_pattern:
        words = words[1:]
    return words


def _search_rule(head: str, cmd: list[str], cwd: Path) -> str | None:
    """A recursive search or archive of a place that holds `.env` (audit of PR #38, M2).

    Purely textual, by owner decision: no file is looked up, so the rule is the same in CI.
    """
    flags = _short_flags(cmd)
    if head in GREP_HEADS:
        recursive = bool({"r", "R"} & flags) or bool(
            {"--recursive", "--dereference-recursive"} & set(cmd)
        )
        targets = _targets(cmd, GREP_VALUED, pattern_first=True) if recursive else None
    elif head == "rg":
        unrestricted = any(re.fullmatch(r"-u{2,}", w) for w in cmd[1:]) or cmd.count("-u") >= 2
        unrestricted = unrestricted or {"--hidden", "--no-ignore"} <= set(cmd)
        targets = _targets(cmd, RG_VALUED, pattern_first=True) if unrestricted else None
    elif head == "tar":
        # `tar czf out.tgz .` (old-style mode word) or `tar -czf out.tgz .`; `-C dir` counts.
        mode = cmd[1] if len(cmd) > 1 else ""
        old_style = bool(mode) and not mode.startswith("-")
        creates = "c" in flags or "--create" in cmd or (old_style and "c" in mode)
        targets = None
        if creates:
            targets = _targets(cmd, {"-f", "--file", "-C", "--directory"}, pattern_first=old_style)
            if old_style and "f" in mode and targets:
                targets = targets[1:]  # the archive named after the mode word
            if "-C" in cmd and cmd.index("-C") + 1 < len(cmd):
                targets.append(cmd[cmd.index("-C") + 1])
    elif head == "zip":
        targets = _targets(cmd, {"-x"}, pattern_first=False) if "r" in flags else None
    else:
        return None
    if targets is None or _excludes_secrets(cmd):
        return None
    for target in targets or ["."]:
        if _is_top(_resolve(target, cwd)):
            return (
                f"{head} over {target} reaches .env: exclude it explicitly "
                "(--exclude='.env*', -g '!.env*', -x '.env*') or search a subfolder"
            )
    return None


def _nested_script(cmd: list[str]) -> str | None:
    """The script of `bash -c '...'` (and sh, zsh, dash, ksh) or `eval ...`, else None."""
    if not cmd:
        return None
    head = _base(cmd[0])
    if head == "eval":
        return " ".join(cmd[1:])
    if head in SHELLS:
        for i, word in enumerate(cmd[1:], 1):
            if not word.startswith("-"):
                return None
            if not word.startswith("--") and "c" in word[1:]:
                return cmd[i + 1] if i + 1 < len(cmd) else ""
    return None


def _read_only(cmd: list[str]) -> bool:
    if not cmd:
        return True
    head = _base(cmd[0])
    if head not in READ_ONLY:
        return False
    if head == "find":
        return not (set(cmd) & FIND_WRITES)
    if head == "git":
        sub, _ = _sub(cmd, {"-C", "-c"})
        if sub == "hash-object":  # B6 (#71): only `-w` writes, into .git/objects
            return not any(
                w == "-w" or (w.startswith("-") and not w.startswith("--") and "w" in w)
                for w in cmd[1:]
            )
        return sub in GIT_READ
    if head == "sed":
        return not any(w == "-i" or w.startswith(("-i", "--in-place")) for w in cmd[1:])
    if head == "ruff":
        return "check" in cmd and "--fix" not in cmd
    return True


# ── A1: the secret check at commit ──────────────────────────────────────────────────────


def _commit_paths(args: list[str]) -> tuple[list[str], bool]:
    """(pathspecs, -a/--all) of `git commit <args>`."""
    paths: list[str] = []
    everything = False
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--":
            paths.extend(args[i + 1 :])
            break
        if word in COMMIT_VALUED:
            i += 2
            continue
        if word == "--all":
            everything = True
        elif word.startswith("-") and not word.startswith("--"):
            letters = word[1:]
            everything = everything or "a" in letters.split("m", 1)[0]
            if letters.endswith(("m", "F", "C", "c", "t")):
                i += 1
        elif not word.startswith("-"):
            paths.append(word)
        i += 1
    return paths, everything


def _commit_diff(cwd: Path, args: list[str], added: list[str] | None = None) -> str:
    """What `git commit <args>` would record: the index, plus what `-a`, pathspecs, or a
    `git add` earlier in the same command stage.

    Content is read for files whose name is not a secrets name; every staged name is listed
    (`STAGED_NAME` lines) so a secrets file is refused by name, never read: the hook never reads
    `.env`. A git error or the time budget refuses the commit (fail closed).
    """
    deadline = time.monotonic() + STAGED_BUDGET_S

    def git(*argv: str, ok: tuple[int, ...] = (0,)) -> tuple[int, str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("git", STAGED_BUDGET_S)
        result = subprocess.run(  # bytes: text mode would turn a lone \r into \n
            ["git", *GIT_SAFE, "-C", str(cwd), *argv], capture_output=True,
            timeout=remaining, check=False,
        )
        if result.returncode not in ok:
            raise subprocess.SubprocessError(f"git {argv[0]} exited {result.returncode}")
        return result.returncode, result.stdout.decode("utf-8", errors="replace")

    paths, everything = _commit_paths(args)
    added = list(added or [])
    # A clean or process filter declared in the repository's own config would run while git
    # reads the worktree: refused rather than run.
    scoped = git("config", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|process)$",
                 ok=(0, 1))[1]
    if any(line.split("\t", 1)[0] in ("local", "worktree") for line in scoped.splitlines()):
        raise subprocess.SubprocessError("a filter driver of the repository would run")
    born = git("rev-parse", "--verify", "-q", "HEAD", ok=(0, 1))[0] == 0
    against = ["HEAD"] if born else []  # an unborn branch: the worktree against the index
    excludes = [f":(exclude,glob)**/{name}" for name in SECRET_NAMES + SECRET_GLOBS]
    runs: list[tuple[list[str], list[str]]] = [(["diff", "--cached"], [])]
    if everything:
        runs.append((["diff"], []))
    for spec in (paths, added):
        if spec:
            runs.append((["diff", *against], spec))
    out: list[str] = []
    for diff, spec in runs:
        names = git(*diff, "--name-only", "--diff-filter=d", "--no-ext-diff", "--no-textconv",
                    "--ignore-submodules=all", "-z", "--", *spec)[1]
        out.extend(f"{STAGED_NAME}{name}\n" for name in names.split("\0") if name)
        out.append(git(
            *diff, "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
            "--ignore-submodules=all", "--src-prefix=a/", "--dst-prefix=b/", "--", *spec,
            *excludes,
        )[1])
    if added:
        untracked = git("ls-files", "-o", "--exclude-standard", "-z", "--", *added)[1]
        for name in (n for n in untracked.split("\0") if n):
            if time.monotonic() > deadline:
                raise subprocess.TimeoutExpired("git add", STAGED_BUDGET_S)
            out.append(f"{STAGED_NAME}{name}\n")
            if not is_secret(name):
                out.append(_as_added(cwd / name, name))
    return "".join(out)


def _as_added(file: Path, name: str) -> str:
    """An untracked file `git add` is about to stage, as the lines of a diff that adds it."""
    try:
        data = file.read_bytes()[:UNTRACKED_READ_LIMIT]
    except OSError:
        return ""
    if b"\0" in data[:8000]:
        return ""  # binary
    lines = data.decode("utf-8", errors="replace").split("\n")  # not splitlines()
    body = "".join(f"+{line}\n" for line in lines)
    return f"diff --git a/{name} b/{name}\n--- /dev/null\n+++ b/{name}\n@@ -0,0 +1 @@\n{body}"


def _safe_name(name: str) -> str:
    """A file name fit for a refusal message: never one that holds a secret prefix."""
    if STAGED_SANITIZE.search(name) or any(p.search(name) for _, p in STAGED_SECRETS):
        return "a file whose name holds a secret pattern"
    return name


def _secret_in_diff(diff: str) -> str | None:
    """The refusal for a staged secret. It names the pattern and the file, never a line of
    content. Rows are split on `\n` only: a form feed or a lone `\r` in a file never starts a
    row, so content cannot forge a header nor hide behind one."""
    path, header = "", False
    for row in diff.split("\n"):
        if row.startswith(STAGED_NAME):
            name = row[len(STAGED_NAME) :]
            base = name.rsplit("/", 1)[-1]
            if is_secret(name) or (base.startswith("id_") and not base.endswith(".pub")):
                return f"a secrets file is staged ({_safe_name(name)}): unstage it"
            continue
        if row.startswith("diff --git "):
            path, header = row.rsplit(" b/", 1)[-1], True
            continue
        if header:
            header = not row.startswith("@@")
            continue
        if row.startswith("+"):
            for rule, pattern in STAGED_SECRETS:
                if pattern.search(row):
                    return (
                        f"the change to commit adds what looks like a {rule} in "
                        f"{_safe_name(path)}: unstage it (the value is not shown)"
                    )
    return None


def _git_dir_and_args(cmd: list[str], cwd: Path) -> tuple[Path, list[str]]:
    """The directory `git -C` points to, and the words after the subcommand."""
    git_dir = cwd
    i = 1
    while i < len(cmd) and cmd[i].startswith("-"):
        if cmd[i] == "-C" and i + 1 < len(cmd):
            git_dir = _resolve(cmd[i + 1], git_dir)
        i += 2 if cmd[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    return git_dir, cmd[i + 1 :]


def _added_paths(cmd: list[str], cwd: Path) -> list[str]:
    """The pathspecs of `git add`, absolute: `-A`, `-u` or no path at all mean the whole tree."""
    git_dir, args = _git_dir_and_args(cmd, cwd)
    paths: list[str] = []
    whole = False
    for word in args:
        if word in ("-A", "--all", "-u", "--update"):
            whole = True
        elif word == "--" or word.startswith("-"):
            continue
        else:
            paths.append(str(_resolve(word, cwd)))
    return [str(git_dir)] if whole or not paths else paths


def _staged_rule(
    cmd: list[str], cwd: Path, staged_of: StagedOf, added: list[str]
) -> str | None:
    """A1 (#71): a commit whose change adds a high-confidence secret."""
    git_dir, args = _git_dir_and_args(cmd, cwd)
    if {"--dry-run", "-h", "--help"} & set(args):
        return None
    # `cd "$(git rev-parse --show-toplevel)"` is not resolved: its parent is the same repo.
    while not git_dir.exists() and git_dir != git_dir.parent:
        git_dir = git_dir.parent
    try:
        diff = staged_of(git_dir, args, added)
    except (OSError, subprocess.SubprocessError):
        return "the change to commit could not be read for secrets: refused (fail closed)"
    return _secret_in_diff(diff)


# ── A7: python code, read with ast ────────────────────────────────────────────────────


def _python_args(cmd: list[str]) -> tuple[int | None, bool]:
    """(index of the `-c` code, reads its program on stdin) of `python ...`; `-W x` and `-X x`
    take the next word."""
    i = 1
    while i < len(cmd):
        word = cmd[i]
        if word in PY_VALUED:
            i += 2
            continue
        if word == "-":
            return None, True
        if word.startswith("--"):
            i += 1
            continue
        if word.startswith("-"):
            for k, ch in enumerate(word[1:], 1):
                if ch in "WX":
                    break  # the rest of the word is the value
                if ch == "c":
                    if k == len(word) - 1:
                        return (i + 1 if i + 1 < len(cmd) else None), False
                    return None, False  # code attached to -c: not read (a known limit)
                if ch == "m":
                    return None, False
            i += 1
            continue
        return None, False  # a script file
    return None, True


def _python_code(cmd: list[str]) -> int | None:
    """Index in `cmd` of the code of `python -c CODE`, else None."""
    if not cmd or not PYTHON.fullmatch(_base(cmd[0])):
        return None
    return _python_args(cmd)[0]


def _quote_state(text: str, end: int) -> str:
    """The quote open at `text[end]`: "'", '"' or "" (backslash escapes outside single quotes)."""
    quote, i = "", 0
    while i < end:
        ch = text[i]
        if ch == "\\" and quote != "'":
            i += 2
            continue
        if ch in "'\"" and quote in ("", ch):
            quote = "" if quote else ch
        i += 1
    return quote


def _quoted_value(text: str, start: int) -> str:
    """The value of the quoted word opening at `text[start]`, as bash passes it."""
    quote = text[start]
    if quote == "'":
        end = text.find("'", start + 1)
        return text[start + 1 : end if end >= 0 else len(text)]
    out: list[str] = []
    i = start + 1
    while i < len(text) and text[i] != '"':
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in '"\\$`\n':
            if text[i + 1] != "\n":
                out.append(text[i + 1])
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


PY_WORD = re.compile(r"(?<![\w./-])(?:[\w.-]*/)?python(?:\d+(?:\.\d+)?)?(?=\s)")
PY_TO_CODE = re.compile(r"(?:\s+(?:-[WX]\s*\S+|-[A-Za-bd-z]+))*\s+-c\s+(?=['\"])")


def _python_c_codes(text: str) -> list[str]:
    """A7 (#71): the quoted code of every `python [-W x] [-X x] -c '...'` whose `python` stands
    outside quotes, taken whole as bash passes it (`_tokens` splits a multi-line one)."""
    codes: list[str] = []
    for match in PY_WORD.finditer(text):
        if _quote_state(text, match.start()):
            continue
        to_code = PY_TO_CODE.match(text, match.end())
        if to_code:
            codes.append(_quoted_value(text, to_code.end()))
    return codes


def _python_heredocs(command: str) -> list[str]:
    """A7 (#71): the bodies of the heredocs fed to `python`, `python -`, `python -W x -`."""
    bodies: list[str] = []
    pending: list[tuple[str, bool, bool]] = []
    current: list[str] = []
    for line in command.split("\n"):
        if pending:
            word, dash, python = pending[0]
            if (line.lstrip("\t") if dash else line) == word:
                pending.pop(0)
                if python:
                    bodies.append("\n".join(current))
                current = []
            elif python:
                current.append(line)
            continue
        head = line.split("<<", 1)[0]
        words = head.replace("|", " | ").replace(";", " ; ").split()
        cmd: list[str] = []
        for word in words:
            if word in ("|", ";", "&&", "||"):
                cmd = []
            elif cmd or PYTHON.fullmatch(_base(word)):
                cmd.append(word)
        reads = bool(cmd) and _python_args(cmd)[1]
        for match in re.finditer(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", line):
            pending.append((match.group(3), match.group(1) == "-", reads))
            reads = False  # one program reads one heredoc
    return bodies


def _py_assignments(tree: ast.AST) -> dict[str, list[ast.expr]]:
    names: dict[str, list[ast.expr]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            names.setdefault(node.target.id, []).append(node.value)
    return names


def _py_strings(
    node: ast.AST, names: dict[str, list[ast.expr]], depth: int = 0
) -> Iterator[str]:
    """String literals in `node`; an f-string gives its literal head, a name what it was set to."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            yield node.value
        return
    if isinstance(node, ast.JoinedStr):
        head: list[str] = []
        for part in node.values:
            if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                break
            head.append(part.value)
        if head:
            yield "".join(head)
        return
    if isinstance(node, ast.Name):
        if depth < 3:
            for value in names.get(node.id, []):
                yield from _py_strings(value, names, depth + 1)
        return
    for child in ast.iter_child_nodes(node):
        yield from _py_strings(child, names, depth)


def _pathlike(text: str) -> bool:
    return bool(text) and len(text) < 4096 and not any(ch.isspace() for ch in text)


def _py_call_name(call: ast.Call) -> tuple[str, str]:
    """(owner, name): `os.remove` gives ("os", "remove"), `open` gives ("", "open"), a method on
    an expression gives ("<expr>", name)."""
    func = call.func
    if isinstance(func, ast.Name):
        return "", func.id
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else "<expr>"
        return owner, func.attr
    return "<expr>", ""


def _py_write_targets(call: ast.Call) -> list[ast.expr]:
    """The arguments a call writes to, or [] for a call that writes nothing we know of."""
    owner, name = _py_call_name(call)
    args = list(call.args)
    keywords = {k.arg: k.value for k in call.keywords if k.arg}
    func = call.func
    if name == "open":
        if owner in ("", "io", "builtins"):
            target, mode = (args[:1] or [keywords.get("file")])[0], (
                args[1] if len(args) > 1 else keywords.get("mode")
            )
        elif owner == "os":
            return args[:1]
        else:  # Path(...).open(mode)
            target = func.value if isinstance(func, ast.Attribute) else None
            mode = args[0] if args else keywords.get("mode")
        writes = isinstance(mode, ast.Constant) and PY_OPEN_WRITE.search(str(mode.value))
        return [target] if writes and target is not None else []
    if name == "connect" and owner in ("duckdb", "sqlite3", ""):
        read_only = keywords.get("read_only")
        if isinstance(read_only, ast.Constant) and read_only.value is True:
            return []
        return args[:1] or [v for k, v in keywords.items() if k == "database"]
    if owner in PY_FUNC_MODULES or owner == "":
        if name in PY_FUNC_WRITES:
            return args[1:] if name in PY_COPIES else args
        return []
    if name in PY_METHOD_WRITES and isinstance(func, ast.Attribute):
        return [func.value, *args]
    return []


def _py_command(call: ast.Call, names: dict[str, list[ast.expr]]) -> str | None:
    """The literal command of `subprocess.run([...])`, `os.system("...")` and the like."""
    owner, name = _py_call_name(call)
    if name not in PY_RUNS or owner not in PY_RUN_MODULES | {""}:
        return None
    first = call.args[0] if call.args else next(
        (k.value for k in call.keywords if k.arg in ("args", "cmd", "command")), None
    )
    if first is None:
        return None
    if isinstance(first, (ast.List, ast.Tuple)):
        return shlex.join(next(_py_strings(e, names), "") for e in first.elts)
    return next(_py_strings(first, names), None)


def _python_rule(
    code: str, cwd: Path, branch_of: BranchOf, depth: int, staged_of: StagedOf
) -> str | None:
    """A7 (#71): `python -c` code or a python heredoc, read with `ast`, never run.

    A heuristic that reads the code: a path built at runtime, `exec`, `getattr` or an encoding
    is not seen (docs/permissions.md).
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return "this python code does not parse: refused (python would refuse it too)"
    for text in _py_strings(tree, {}):
        if _pathlike(text) and is_secret(text):
            return f"secrets files are never read or written by the agent ({_base(text)})"
    names = _py_assignments(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        command = _py_command(node, names)
        if command:
            if depth >= MAX_NESTING:
                return "shells nested this deep are refused"
            refusal = _bash(command, cwd, branch_of, depth + 1, staged_of)
            if refusal:
                return refusal
        for target in _py_write_targets(node):
            for text in _py_strings(target, names):
                if _pathlike(text):
                    refusal = _write_refusal(_resolve(text, cwd))
                    if refusal:
                        return refusal
    return None


# ── The walk ────────────────────────────────────────────────────────────────────────────


def _bash(
    command: str,
    cwd: Path,
    branch_of: BranchOf,
    depth: int = 0,
    staged_of: StagedOf = _commit_diff,
) -> str | None:
    switched_to_main = False
    added: list[str] = []  # what `git add` stages before a `git commit` (A1)
    for script in _substitutions(_strip_heredocs(command)):  # A6 (#71)
        if depth >= MAX_NESTING:
            return "shells nested this deep are refused"
        refusal = _bash(script, cwd, branch_of, depth + 1, staged_of)
        if refusal:
            return refusal
    for code in _python_c_codes(_strip_heredocs(command)) + _python_heredocs(command):  # A7
        refusal = _python_rule(code, cwd, branch_of, depth, staged_of)
        if refusal:
            return refusal
    for words, redirects in _with_keywords_skipped(_segments(_tokens(command))):
        env, cmd = _command(words)
        skip = {len(words) - len(cmd) + i for i in _excluded(cmd)}
        for index, word in enumerate(words + [t for _, t in redirects]):
            if index in skip:
                continue  # `--exclude='.env*'` keeps a secret out; it reads nothing
            parts = [word, word.split("=", 1)[-1]]
            if word[:1] == "-" and word[1:2] not in ("-", "") and len(word) > 2:
                # A3 (#71): a value glued to a short flag or a cluster, `-f.env`, `-aF.env`
                parts.extend(word[k:] for k in range(2, len(word)))
            for part in parts:
                for variant in _brace_expand(part):
                    if is_secret(variant):
                        name = _base(variant)
                        return f"secrets files are never read or written by the agent ({name})"
        code = _python_code(cmd)
        if code is not None:  # A7 (#71): single-line code, as the segment holds it
            refusal = _python_rule(cmd[code], cwd, branch_of, depth, staged_of)
            if refusal:
                return refusal
        script = _nested_script(cmd)
        if script is not None:
            if depth >= MAX_NESTING:
                return "shells nested this deep are refused"
            refusal = _bash(script, cwd, branch_of, depth + 1, staged_of)
            if refusal:
                return refusal
        for op, target in redirects:
            if ">" in op and target and not target.startswith("&"):
                refusal = _write_refusal(_resolve(target, cwd))
                if refusal:
                    return refusal
        for rule in (
            _render_rule(words, redirects),
            _gh_rule(cmd) if cmd and _base(cmd[0]) == "gh" else None,
            _pipeline_rule(env, cmd, cwd),
        ):
            if rule:
                return rule
        if cmd and _base(cmd[0]) == "git":
            refusal = _git_rule(cmd[1:], cwd, branch_of, switched_to_main)
            if refusal:
                return refusal
            sub, rest = _sub(cmd, {"-C", "-c"})
            if sub in ("checkout", "switch") and "main" in rest:
                switched_to_main = True
            if sub == "add":
                added.extend(_added_paths(cmd, cwd))
            if sub == "commit":
                refusal = _staged_rule(cmd, cwd, staged_of, added)
                if refusal:
                    return refusal
        head = _base(cmd[0]) if cmd else ""
        for rule in (_destructive_rule(head, cmd, cwd), _search_rule(head, cmd, cwd)):
            if rule:
                return rule
        operands = [w for w in cmd[1:] if w and not w.startswith("-")]
        for word in cmd[1:]:
            value = word.split("=", 1)[-1] if word.startswith("--") else word
            if value.startswith("-") or not value:
                continue
            if "/" not in value and head not in FILE_MUTATORS:
                continue
            path = _resolve(value, cwd)
            if _inside(path, DATA_ZONES + SELF_ZONES) and not _read_only(cmd):
                if head.startswith("python") and path == ROOT / "agent-hooks" / "pre_tool_use.py":
                    continue
                # A copy READS its sources: only the destination (last operand) is written.
                if head in COPIERS and "-t" not in cmd and value != operands[-1]:
                    continue
                # Staging the guardrail's files does not change them.
                if head == "git" and _inside(path, SELF_ZONES):
                    if _sub(cmd, {"-C", "-c"})[0] in GIT_STAGE:
                        continue
                return _write_refusal(path) or "refused"
            if _is_settings(path) and not _read_only(cmd):
                if head == "git" and _sub(cmd, {"-C", "-c"})[0] in GIT_STAGE:
                    continue
                return _write_refusal(path)
        if head == "cd" and len(cmd) > 1:
            cwd = _resolve(cmd[1], cwd)
    return None


def _current_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def decide(
    event: dict[str, object],
    branch_of: BranchOf = _current_branch,
    staged_of: StagedOf = _commit_diff,
) -> str | None:
    """The refusal reason for this tool call, or None to let it through. `staged_of` reads the
    change a `git commit` would record (A1); tests inject it."""
    tool = str(event.get("tool_name", ""))
    raw_input = event.get("tool_input")
    data = raw_input if isinstance(raw_input, dict) else {}
    cwd = Path(str(event.get("cwd") or ROOT))

    if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep", "Glob"):
        target = data.get("file_path") or data.get("notebook_path") or data.get("path") or ""
        if not target:
            return None
        path = _resolve(str(target), cwd)
        if is_secret(str(target)):
            return f"secrets files are never read or written by the agent ({path.name})"
        if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
            return _write_refusal(path)
        return None
    if tool == "Bash":
        return _bash(str(data.get("command", "")), cwd, branch_of, staged_of=staged_of)
    if tool == "WebFetch":
        if re.search(r"^https?://([^/]*\.)?render\.com(/|$)", str(data.get("url", ""))):
            return "calls to the Render API or deploy hooks are refused"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        reason = decide(event if isinstance(event, dict) else {})
    except Exception as exc:  # noqa: BLE001 -- fail closed on anything unexpected
        reason = f"guardrail error ({type(exc).__name__}), failing closed"
    if reason:
        print(f"Blocked by agent-hooks/pre_tool_use.py: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
