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

Added with issue #71 (owner decisions, 2026-10-30): the hook analyses what bash executes, not
the text inside its strings.

* The command is lexed whole, quotes spanning lines included; a newline outside quotes ends a
  command. An unbalanced quote, `$(` or backtick is refused: bash would refuse it too.
* Every string bash runs goes through the same rules: the script of `bash -c` and `eval`, a
  command substitution `$(...)` or backtick outside single quotes (inside double quotes too),
  a heredoc or here-string fed to a shell, and the substitutions of an unquoted heredoc body.
* `python -c` code and a heredoc fed to python are read with `ast`, never run. Refused: a
  secrets file name; a protected path given to a write call (`open` for writing, pathlib, `os`
  and `shutil` writes, `duckdb.connect` without `read_only=True`, ...); a `subprocess` or
  `os.system` call whose literal command these rules refuse. A heuristic that reads the code: a
  path built at runtime, `exec`, `getattr` or an encoding is not seen.
* What bash hands over as data is not read as paths or commands: the message of `git commit
  -m`, a heredoc body fed to a program that is neither a shell nor python (fed to `xargs`, it
  is checked as the arguments it becomes), a `for` list (its items are checked through the
  loop variable in the body). The pattern of grep, rg and `git
  log --grep`, and the arguments of echo and printf, are not read as secrets files.
* `( ... )` scopes `cd` and variables; `NAME=value` and `export NAME=value` are expanded in
  paths.
* `python -m cyclebeat.cli`: `--help` passes; `ingest --lake <dir outside data/ and lake/>`
  passes (not `--live`, which fills `data/spike/.cache`); `load --db <path outside data/>`
  passes; `--lake lake` no longer hides the subcommand.
* `gh issue reopen`, `delete` and `transfer`, and an issue state change through `gh api`.
* `git commit` when the change it records adds a private key header or a known token prefix
  (GitHub, AWS). Secrets files are left out of that read by pathspec: the hook never reads
  `.env`. gitleaks in CI stays the net for everything else.

It stops mistakes, not an adversary. The deny rules of `.claude/settings.json` and the
auto-mode classifier are the other layers. Standard library only, so it runs before any
virtualenv exists.
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
REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<", "<<", "<<-", "<<<", "<>", ">&", "<&"}
WRAPPERS = {"sudo", "env", "command", "time", "nohup", "nice", "exec", "xargs", "timeout"}
# Shell reserved words that can open a command; the real command follows them.
RESERVED = {"do", "done", "then", "else", "elif", "fi", "if", "while", "until", "!", "{", "}"}

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
GIT_LOG_PATTERNS = {"--grep", "-S", "-G"}
COMMIT_VALUED = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c",
                 "--reedit-message", "--author", "--date", "--fixup", "--squash", "--cleanup",
                 "--trailer", "-t", "--template", "--pathspec-from-file"}

# python -c (issue #71, owner decision P1): calls that write what their arguments name.
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

# Candidate 7 (issue #71, owner decision A): high-confidence secrets only, one test each.
# Private key headers: RFC 7468 (https://www.rfc-editor.org/rfc/rfc7468), plus the OpenSSH and
# PGP labels. GitHub prefixes: https://docs.github.com/en/authentication/keeping-your-account-
# and-data-secure/about-authentication-to-github#githubs-token-formats. AWS key ID prefixes:
# https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-prefixes
STAGED_SECRETS = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("AWS access key ID", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
)

BranchOf = Callable[[Path], str | None]
StagedOf = Callable[[Path, list[str]], str]


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


class Unparsable(ValueError):
    """An unbalanced quote, `$(` or backtick: bash would refuse the command too."""


class _Tok:
    """A word (quotes removed) or an operator, with the scripts bash runs to build it."""

    __slots__ = ("op", "text", "subs", "body", "body_subs", "delimiter")

    def __init__(self, text: str = "", op: bool = False) -> None:
        self.op = op
        self.text = text
        self.subs: list[str] = []
        self.body: str | None = None  # a heredoc body, once read
        self.body_subs: list[str] = []
        self.delimiter: tuple[str, bool, bool] | None = None  # (word, strip tabs, expands)


OP_CHARS = frozenset(";&|()<>")
OPS = sorted(OPERATORS | REDIRECTS, key=len, reverse=True)


class _Lexer:
    """Bash words and operators over the whole command (issue #71).

    A newline outside quotes ends a command; a quoted string keeps its newlines. Heredoc bodies
    are read at the end of their line and attached to their delimiter word.
    """

    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.pending: list[_Tok] = []

    def run(self, nested: bool = False) -> list[_Tok]:
        s = self.s
        out: list[_Tok] = []
        depth = 0
        while self.i < len(s):
            ch = s[self.i]
            if s.startswith("\\\n", self.i):
                self.i += 2
            elif ch in " \t\r":
                self.i += 1
            elif ch == "\n":
                self.i += 1
                self._bodies()
                out.append(_Tok(";", op=True))
            elif ch == "#":
                end = s.find("\n", self.i)
                self.i = len(s) if end < 0 else end
            elif ch in OP_CHARS:
                op = next(o for o in OPS if s.startswith(o, self.i))
                self.i += len(op)
                if op == ")" and nested and depth == 0:
                    return out
                depth += {"(": 1, ")": -1}.get(op, 0)
                out.append(_Tok(op, op=True))
                if op in ("<<", "<<-"):
                    while self.i < len(s) and s[self.i] in " \t":
                        self.i += 1
                    word, quoted = self._word()
                    word.delimiter = (word.text, op == "<<-", not quoted)
                    self.pending.append(word)
                    out.append(word)
            else:
                out.append(self._word()[0])
        if nested:
            raise Unparsable("unclosed $(")
        self._bodies()
        return out

    def _bodies(self) -> None:
        s = self.s
        for tok in self.pending:
            assert tok.delimiter is not None
            word, strip, expands = tok.delimiter
            lines: list[str] = []
            while self.i < len(s):
                end = s.find("\n", self.i)
                line = s[self.i : len(s) if end < 0 else end]
                self.i = len(s) if end < 0 else end + 1
                if (line.lstrip("\t") if strip else line) == word:
                    break
                lines.append(line)
            tok.body = "\n".join(lines) + "\n"
            if expands:
                tok.body_subs = _heredoc_subs(tok.body)
        self.pending = []

    def _word(self) -> tuple[_Tok, bool]:
        s = self.s
        tok = _Tok()
        buf: list[str] = []
        quoted = False
        while self.i < len(s):
            ch = s[self.i]
            if ch in " \t\r\n" or ch in OP_CHARS:
                break
            if ch == "\\":
                if s.startswith("\\\n", self.i):
                    self.i += 2
                    continue
                buf.append(s[self.i + 1 : self.i + 2])
                self.i += 2
                quoted = True
            elif ch == "'":
                end = s.find("'", self.i + 1)
                if end < 0:
                    raise Unparsable("unclosed '")
                buf.append(s[self.i + 1 : end])
                self.i = end + 1
                quoted = True
            elif ch == '"':
                self.i += 1
                self._double(buf, tok)
                quoted = True
            elif s.startswith("$'", self.i):
                j = self.i + 2
                while j < len(s) and s[j] != "'":
                    j += 2 if s[j] == "\\" else 1
                if j >= len(s):
                    raise Unparsable("unclosed $'")
                buf.append(s[self.i + 2 : j])
                self.i = j + 1
                quoted = True
            elif s.startswith("$(", self.i):
                buf.append(self._dollar_paren(tok))
            elif s.startswith("${", self.i):
                end = s.find("}", self.i)
                if end < 0:
                    raise Unparsable("unclosed ${")
                buf.append(s[self.i : end + 1])
                self.i = end + 1
            elif ch == "`":
                buf.append(self._backtick(tok))
            else:
                buf.append(ch)
                self.i += 1
        tok.text = "".join(buf)
        return tok, quoted

    def _double(self, buf: list[str], tok: _Tok) -> None:
        s = self.s
        while self.i < len(s):
            ch = s[self.i]
            if ch == '"':
                self.i += 1
                return
            if ch == "\\" and self.i + 1 < len(s):
                following = s[self.i + 1]
                if following != "\n":
                    buf.append(following if following in '"\\$`' else "\\" + following)
                self.i += 2
            elif s.startswith("$(", self.i):
                buf.append(self._dollar_paren(tok))
            elif ch == "`":
                buf.append(self._backtick(tok))
            else:
                buf.append(ch)
                self.i += 1
        raise Unparsable('unclosed "')

    def _dollar_paren(self, tok: _Tok) -> str:
        start = self.i
        self.i += 2
        self.run(nested=True)
        tok.subs.append(self.s[start + 2 : self.i - 1])
        return self.s[start : self.i]

    def _backtick(self, tok: _Tok) -> str:
        s = self.s
        j = self.i + 1
        while j < len(s) and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        if j >= len(s):
            raise Unparsable("unclosed `")
        tok.subs.append(s[self.i + 1 : j].replace("\\`", "`"))
        raw = s[self.i : j + 1]
        self.i = j + 1
        return raw


def _heredoc_subs(body: str) -> list[str]:
    """The substitutions bash runs in an unquoted heredoc body (`<<EOF`, not `<<'EOF'`)."""
    lexer = _Lexer(body)
    subs: list[str] = []
    holder = _Tok()
    while lexer.i < len(body):
        if body[lexer.i] == "\\":
            lexer.i += 2
        elif body.startswith("$(", lexer.i):
            lexer._dollar_paren(holder)
        elif body[lexer.i] == "`":
            lexer._backtick(holder)
        else:
            lexer.i += 1
    subs.extend(holder.subs)
    return subs


class _Seg:
    """One simple command: its words, redirections, stdin bodies and substitutions."""

    __slots__ = ("words", "redirects", "stdin", "subs", "mark")

    def __init__(self, mark: str = "") -> None:
        self.words: list[str] = []
        self.redirects: list[tuple[str, str]] = []
        self.stdin: list[str] = []
        self.subs: list[str] = []
        self.mark = mark  # "(" or ")" for a subshell boundary


def _segments(tokens: list[_Tok]) -> list[_Seg]:
    """Split on shell operators; `(` and `)` become subshell markers."""
    segments: list[_Seg] = []
    seg = _Seg()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.op and tok.text in OPERATORS:
            if seg.words or seg.redirects:
                segments.append(seg)
            seg = _Seg()
            if tok.text in ("(", ")"):
                segments.append(_Seg(mark=tok.text))
        elif tok.op:
            target = tokens[i + 1] if i + 1 < len(tokens) else None
            if target is not None and not target.op:
                seg.redirects.append((tok.text, target.text))
                seg.subs.extend(target.subs)
                if tok.text == "<<<":
                    seg.stdin.append(target.text)
                elif target.body is not None:
                    seg.stdin.append(target.body)
                    seg.subs.extend(target.body_subs)
                i += 1
            if seg.words and seg.words[-1].isdigit():
                seg.words.pop()
        else:
            seg.words.append(tok.text)
            seg.subs.extend(tok.subs)
        i += 1
    if seg.words or seg.redirects:
        segments.append(seg)
    return segments


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


def _sub_index(words: list[str], takes_value: set[str]) -> int:
    """Index of the first non-option word after `words[0]`, or len(words)."""
    i = 1
    while i < len(words):
        word = words[i]
        if word in takes_value:
            i += 2
            continue
        if word.startswith("-"):
            i += 1
            continue
        return i
    return len(words)


def _sub(words: list[str], takes_value: set[str]) -> tuple[str, list[str]]:
    """First non-option word after `words[0]` (skipping options that take a value)."""
    i = _sub_index(words, takes_value)
    if i >= len(words):
        return "", []
    return words[i], words[i + 1 :]


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _expand(word: str, variables: dict[str, str]) -> str:
    """`$NAME` and `${NAME}` set earlier in the command; others stay for `_resolve`."""
    def value(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return variables.get(name, match.group(0))

    return VARIABLE.sub(value, word) if "$" in word else word


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


def _commit_diff(cwd: Path, args: list[str]) -> str:
    """The lines `git commit <args>` would add: the index, plus what `-a` or pathspecs stage.

    Secrets files are left out by pathspec: the hook never reads `.env`.
    """
    paths, everything = _commit_paths(args)
    excludes = [f":(exclude,glob)**/{name}" for name in SECRET_NAMES + SECRET_GLOBS]
    runs = [(["diff", "--cached"], [])]
    if everything:
        runs.append((["diff"], []))
    if paths:
        runs.append((["diff", "HEAD"], paths))
    out: list[str] = []
    for diff, spec in runs:
        result = subprocess.run(
            ["git", "-C", str(cwd), *diff, "-U0", "--no-color", "--no-ext-diff",
             "--no-textconv", "--", *spec, *excludes],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2,
            check=False,
        )
        out.append(result.stdout)
    return "".join(out)


def _secret_in_diff(diff: str) -> str | None:
    path, line = "", 0
    for row in diff.splitlines():
        if row.startswith("+++ "):
            path = row[6:] if row.startswith("+++ b/") else row[4:]
        elif row.startswith("@@"):
            match = re.search(r"\+(\d+)", row)
            line = int(match.group(1)) if match else 0
        elif row.startswith("+"):
            for rule, pattern in STAGED_SECRETS:
                if pattern.search(row):
                    return (
                        f"the change to commit adds what looks like a {rule} ({path}:{line}): "
                        "unstage it (the value is not shown)"
                    )
            line += 1
    return None


def _staged_rule(cmd: list[str], cwd: Path, staged_of: StagedOf) -> str | None:
    """Candidate 7 (#71): a commit whose change adds a high-confidence secret."""
    git_dir = cwd
    i = 1
    while i < len(cmd) and cmd[i].startswith("-"):
        if cmd[i] == "-C" and i + 1 < len(cmd):
            git_dir = _resolve(cmd[i + 1], git_dir)
        i += 2 if cmd[i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    args = cmd[i + 1 :]
    if {"--dry-run", "-h", "--help"} & set(args):
        return None
    try:
        diff = staged_of(git_dir, args)
    except (OSError, subprocess.SubprocessError):
        return "the change to commit could not be read for secrets: refused (fail closed)"
    return _secret_in_diff(diff)


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
        if action in ("reopen", "delete", "transfer"):  # issue #71, M1b
            return f"gh issue {action} changes an issue's state: not the agent's action"
        # gh 2.45 has no `issue edit --state`; the branch stays for a later gh (issue #71).
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
    method, endpoint, fields = _gh_api_call(rest)
    if method == "POST" and re.search(r"(^|/)repos/[^/]+/[^/]+/pulls/?$", endpoint):
        return "opening a PR through the GitHub API is the owner's action"
    if method in ("PUT", "DELETE") and "/contents/" in endpoint:
        if fields.get("branch", "main") == "main":
            return "writing a file on main through the GitHub API is refused: open a PR"
    if method != "GET" and re.search(r"(^|/)repos/[^/]+/[^/]+/issues/\d+/?$", endpoint):
        if {"state", "state_reason"} & set(fields):  # issue #71, M1b
            return "changing an issue's state through the GitHub API is the merged PR's job"
    return None


def _gh_api_call(rest: list[str]) -> tuple[str, str, dict[str, str]]:
    """(HTTP method, endpoint, fields) of `gh api ...`, as gh itself defaults them."""
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
        elif word in ("-f", "-F", "--field", "--raw-field", "--input"):
            has_body = True
            key, _, value = following.partition("=")
            fields[key] = value
            i += 2
        elif word.startswith(("--field=", "--raw-field=")):
            has_body = True
            key, _, value = word.split("=", 1)[1].partition("=")
            fields[key] = value
            i += 1
        elif word in GH_API_VALUED:
            i += 2
        else:
            if not word.startswith("-") and not endpoint:
                endpoint = word
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


def _cli_rule(env: dict[str, str], args: list[str], cwd: Path) -> str | None:
    """`python -m cyclebeat.cli [--lake DIR] <command> ...` (cyclebeat/cli.py, issue #71)."""
    if "-h" in args or "--help" in args:
        return None  # argparse prints the usage and exits before any command runs
    lake = ""
    sub = ""
    rest: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--lake":
            lake = args[i + 1] if i + 1 < len(args) else ""
            i += 2
            continue
        if word.startswith("--lake="):
            lake = word.split("=", 1)[1]
        elif not word.startswith("-"):
            sub, rest = word, args[i + 1 :]
            break
        i += 1
    if sub in CLI_WRITES_LAKE:
        # `ingest` writes only the lake root it is given; `--live` and `resolve` also fill the
        # HTTP cache under data/spike/, and `extract-app` reads the app store under data/.
        outside = bool(lake) and not _inside(_resolve(lake, cwd), DATA_ZONES)
        if sub == "ingest" and outside and "--live" not in rest:
            return None
        return f"cyclebeat.cli {sub} writes lake/ and data/"
    if sub in CLI_WRITES_DB:
        db = ""
        for j, word in enumerate(rest):
            if word == "--db" and j + 1 < len(rest):
                db = rest[j + 1]
            elif word.startswith("--db="):
                db = word.split("=", 1)[1]
        if db and not _inside(_resolve(db, cwd), DATA_ZONES):
            return None
        if not db and _db_outside_data(env, cwd):
            return None
        return "cyclebeat.cli load writes data/: pass --db or RUNTIME_DB_PATH= outside data/"
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
        start = cmd.index("-m")
        module = cmd[start + 1] if start + 1 < len(cmd) else ""
        if module == "ingest.ingest_pipeline":
            return "the ingest pipeline writes lake/"
        if module == "cyclebeat.cli":
            return _cli_rule(env, cmd[start + 2 :], cwd)
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


def _shell_reads_stdin(cmd: list[str]) -> bool:
    """`bash`, `bash -s`, `sh -`: the heredoc fed to it is the script."""
    if not cmd or _base(cmd[0]) not in SHELLS or _nested_script(cmd) is not None:
        return False
    args = cmd[1:]
    return all(w.startswith("-") for w in args) or "-s" in args


def _python_code(cmd: list[str]) -> int | None:
    """Index in `cmd` of the code of `python -c CODE`, else None."""
    if not cmd or not PYTHON.fullmatch(_base(cmd[0])):
        return None
    for i, word in enumerate(cmd[1:], 1):
        if word == "-c" or (re.fullmatch(r"-[bBdEhiIOPqsSuv]*c", word)):
            return i + 1 if i + 1 < len(cmd) else None
        if word in ("-W", "-X"):
            continue
        if not word.startswith("-") or word == "-" or "m" in word:
            return None
    return None


def _python_reads_stdin(cmd: list[str]) -> bool:
    """`python` or `python -`: the heredoc fed to it is the program."""
    if not cmd or not PYTHON.fullmatch(_base(cmd[0])) or _python_code(cmd) is not None:
        return False
    for word in cmd[1:]:
        if word == "-":
            return True
        if not word.startswith("-") or "m" in word:
            return False
    return True


def _data_words(cmd: list[str]) -> tuple[set[int], set[int]]:
    """(message, inert) indexes in `cmd`.

    Message: what `git commit -m` records, never a path nor a command. Inert: words that name no
    file to open (a search pattern, echo/printf arguments, an exclusion value, python code that
    `_python_rule` reads instead); the secrets check skips both sets.
    """
    message: set[int] = set()
    inert = set(_excluded(cmd))
    if not cmd:
        return message, inert
    head = _base(cmd[0])
    code = _python_code(cmd)
    if code is not None:
        inert.add(code)
    if head in ("echo", "printf"):
        inert.update(range(1, len(cmd)))
    if head in GREP_HEADS or head == "rg":
        inert.update(_pattern_words(cmd, 0))
    if head == "git":
        at = _sub_index(cmd, {"-C", "-c", "--git-dir", "--work-tree"})
        sub = cmd[at] if at < len(cmd) else ""
        if sub == "commit":
            message.update(_message_words(cmd, at))
        elif sub == "grep":
            inert.update(_pattern_words(cmd, at))
        elif sub in GIT_READ:
            for i in range(at + 1, len(cmd)):
                word = cmd[i]
                if word in GIT_LOG_PATTERNS and i + 1 < len(cmd):
                    inert.add(i + 1)
                elif word.startswith(("--grep=", "-S", "-G")) and word not in GIT_LOG_PATTERNS:
                    inert.add(i)
    return message, inert


def _message_words(cmd: list[str], at: int) -> set[int]:
    """Indexes of the commit message given with -m, --message or -m attached (`-am msg`)."""
    out: set[int] = set()
    for i in range(at + 1, len(cmd)):
        word = cmd[i]
        if word == "--":
            break
        if word in ("-m", "--message") and i + 1 < len(cmd):
            out.add(i + 1)
        elif word.startswith("--message="):
            out.add(i)
        elif re.fullmatch(r"-[a-zA-Z]+", word) and "m" in word[1:] and i - 1 not in out:
            out.add(i + 1 if word.endswith("m") else i)
        elif word.startswith("-m") and len(word) > 2 and i - 1 not in out:
            out.add(i)
    return {i for i in out if i < len(cmd)}


def _pattern_words(cmd: list[str], at: int) -> set[int]:
    """Indexes of the search pattern of grep, rg or `git grep` (the `-e` values, else the first
    positional); a `-f` value is a file and stays checked."""
    valued = RG_VALUED if _base(cmd[0]) == "rg" else GREP_VALUED
    out: set[int] = set()
    explicit = False
    for i in range(at + 1, len(cmd)):
        if cmd[i] in ("-e", "--regexp") and i + 1 < len(cmd):
            out.add(i + 1)
            explicit = True
        elif cmd[i].startswith("--regexp="):
            out.add(i)
            explicit = True
        elif cmd[i] in ("-f", "--file") or cmd[i].startswith("--file="):
            explicit = True
    if explicit:
        return out
    i = at + 1
    while i < len(cmd):
        if cmd[i] in valued:
            i += 2
            continue
        if not cmd[i].startswith("-"):
            return {i}
        i += 1
    return out


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
        return sub in GIT_READ
    if head == "sed":
        return not any(w == "-i" or w.startswith(("-i", "--in-place")) for w in cmd[1:])
    if head == "ruff":
        return "check" in cmd and "--fix" not in cmd
    return True


# ── python -c (issue #71, owner decision P1) ────────────────────────────────────────────


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


def _python_rule(code: str, cwd: Path, ctx: _Ctx) -> str | None:
    """`python -c` code or a python heredoc, read with `ast`, never run.

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
            refusal = _nested(command, cwd, ctx)
            if refusal:
                return refusal
        for target in _py_write_targets(node):
            for text in _py_strings(target, names):
                if _pathlike(text):
                    refusal = _write_refusal(_resolve(text, cwd))
                    if refusal:
                        return refusal
    return None


# ── The command walk ────────────────────────────────────────────────────────────────────


class _Ctx:
    __slots__ = ("branch_of", "staged_of", "depth")

    def __init__(self, branch_of: BranchOf, staged_of: StagedOf, depth: int = 0) -> None:
        self.branch_of = branch_of
        self.staged_of = staged_of
        self.depth = depth

    def deeper(self) -> _Ctx:
        return _Ctx(self.branch_of, self.staged_of, self.depth + 1)


def _nested(
    script: str, cwd: Path, ctx: _Ctx, variables: dict[str, str] | None = None
) -> str | None:
    if ctx.depth >= MAX_NESTING:
        return "shells nested this deep are refused"
    return _walk(script, cwd, ctx.deeper(), dict(variables or {}))


def _walk(command: str, cwd: Path, ctx: _Ctx, variables: dict[str, str]) -> str | None:
    try:
        segments = _segments(_Lexer(command).run())
    except Unparsable as exc:
        return f"this command does not parse ({exc}): refused, bash would refuse it too"
    scopes: list[tuple[Path, dict[str, str]]] = []
    loops: list[tuple[str, list[str]] | None] = []
    switched_to_main = False
    for seg in segments:
        if seg.mark == "(":
            scopes.append((cwd, dict(variables)))
            continue
        if seg.mark == ")":
            if scopes:
                cwd, variables = scopes.pop()
            continue
        for script in seg.subs:
            refusal = _nested(script, cwd, ctx, variables)
            if refusal:
                return refusal
        words = list(seg.words)
        while words and words[0] in RESERVED:
            if words[0] == "done" and loops:
                loops.pop()
            elif words[0] in ("while", "until"):
                loops.append(None)
            words = words[1:]
        if words and words[0] in ("for", "select"):
            # The list is data bound to the loop variable: checked through it in the body.
            items = words[3:] if words[2:3] == ["in"] else []
            loops.append((words[1], items) if len(words) > 1 else None)
            refusal = _secret_words(items, set())
            if refusal:
                return refusal
            continue
        if not words and not seg.redirects:
            continue
        checked = words
        if "xargs" in words:  # xargs turns the heredoc it is fed into arguments
            checked = words + [w for body in seg.stdin for w in body.split()]
        for bound in _loop_variants(variables, loops, checked, seg.redirects):
            refusal = _segment_rule(
                [_expand(w, bound) for w in checked],
                [(op, _expand(t, bound)) for op, t in seg.redirects],
                seg.stdin, cwd, ctx, switched_to_main, bound,
            )
            if refusal:
                return refusal
        env, cmd = _command([_expand(w, variables) for w in words])
        if not cmd:
            variables.update({k: _expand(v, variables) for k, v in env.items()})
            continue
        head = _base(cmd[0])
        if head == "export":
            for word in cmd[1:]:
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", word):
                    name, value = word.split("=", 1)
                    variables[name] = value
        if head == "git":
            sub, rest = _sub(cmd, {"-C", "-c"})
            if sub in ("checkout", "switch") and "main" in rest:
                switched_to_main = True
        if head == "cd" and len(cmd) > 1:
            cwd = _resolve(cmd[1], cwd)
    return None


def _loop_variants(
    variables: dict[str, str],
    loops: list[tuple[str, list[str]] | None],
    words: list[str],
    redirects: list[tuple[str, str]],
) -> list[dict[str, str]]:
    """One variable set per value of each enclosing `for` variable the command uses."""
    text = " ".join(words + [t for _, t in redirects])
    variants = [dict(variables)]
    for loop in loops:
        if loop is None or not loop[1] or not VARIABLE.search(text):
            continue
        name, items = loop
        if f"${name}" not in text and f"${{{name}}}" not in text:
            continue
        variants = [{**v, name: item} for v in variants for item in items][:64]
    return variants


def _secret_words(words: list[str], skip: set[int]) -> str | None:
    for index, word in enumerate(words):
        if index in skip:
            continue  # `--exclude='.env*'` keeps a secret out; a pattern or a message reads nothing
        for part in (word, word.split("=", 1)[-1]):
            for variant in _brace_expand(part):
                if is_secret(variant):
                    name = _base(variant)
                    return f"secrets files are never read or written by the agent ({name})"
    return None


def _segment_rule(
    words: list[str],
    redirects: list[tuple[str, str]],
    stdin: list[str],
    cwd: Path,
    ctx: _Ctx,
    switched_to_main: bool,
    variables: dict[str, str],
) -> str | None:
    env, cmd = _command(words)
    offset = len(words) - len(cmd)
    message, inert = _data_words(cmd)
    skip = {offset + i for i in message | inert}
    refusal = _secret_words(words + [t for _, t in redirects], skip)
    if refusal:
        return refusal
    script = _nested_script(cmd)
    if script is not None:
        refusal = _nested(script, cwd, ctx)
        if refusal:
            return refusal
    code = _python_code(cmd)
    if code is not None:
        refusal = _python_rule(cmd[code], cwd, ctx)
        if refusal:
            return refusal
    for body in stdin:
        if _shell_reads_stdin(cmd):
            refusal = _nested(body, cwd, ctx, variables)
        elif _python_reads_stdin(cmd):
            refusal = _python_rule(body, cwd, ctx)
        else:
            continue  # a heredoc fed to cat, git commit -F -, ...: data
        if refusal:
            return refusal
    for op, target in redirects:
        if ">" in op and target and not target.startswith("&"):
            refusal = _write_refusal(_resolve(target, cwd))
            if refusal:
                return refusal
    visible = [w for i, w in enumerate(words) if i - offset not in message]
    for rule in (
        _render_rule(visible, redirects),
        _gh_rule(cmd) if cmd and _base(cmd[0]) == "gh" else None,
        _pipeline_rule(env, cmd, cwd),
    ):
        if rule:
            return rule
    head = _base(cmd[0]) if cmd else ""
    if head == "git":
        refusal = _git_rule(cmd[1:], cwd, ctx.branch_of, switched_to_main)
        if refusal:
            return refusal
        if _sub(cmd, {"-C", "-c", "--git-dir", "--work-tree"})[0] == "commit":
            refusal = _staged_rule(cmd, cwd, ctx.staged_of)
            if refusal:
                return refusal
    for rule in (_destructive_rule(head, cmd, cwd), _search_rule(head, cmd, cwd)):
        if rule:
            return rule
    operands = [w for w in cmd[1:] if w and not w.startswith("-")]
    for index, word in enumerate(cmd[1:], 1):
        if index in message or index == code:
            continue
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
    return None


def _bash(
    command: str,
    cwd: Path,
    branch_of: BranchOf,
    depth: int = 0,
    staged_of: StagedOf = _commit_diff,
) -> str | None:
    return _walk(command, cwd, _Ctx(branch_of, staged_of, depth), {})


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
    """The refusal reason for this tool call, or None to let it through."""
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
