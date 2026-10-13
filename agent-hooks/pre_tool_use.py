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

It reads command TEXT. It stops mistakes, not an adversary: `python -c` with a computed path
gets through. The deny rules of `.claude/settings.json` and the auto-mode classifier are the
other layers. Standard library only, so it runs before any virtualenv exists.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
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

BranchOf = Callable[[Path], str | None]


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


def _strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: text fed on stdin is data, not paths or commands."""
    lines = command.split("\n")
    out: list[str] = []
    pending: list[tuple[str, bool]] = []
    for line in lines:
        if pending:
            word, dash = pending[0]
            if (line.lstrip("\t") if dash else line) == word:
                pending.pop(0)
            continue
        out.append(line)
        for match in re.finditer(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", line):
            pending.append((match.group(3), match.group(1) == "-"))
    return "\n".join(out)


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
    if sub == "api" and any(re.search(r"/pulls/\d+/merge\b|/merges\b", w) for w in rest):
        return "the GitHub merge API is the owner's action"
    return None


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
        if module == "cyclebeat.cli" and sub in CLI_WRITES_LAKE:
            return f"cyclebeat.cli {sub} writes lake/ and data/"
        if module == "cyclebeat.cli" and sub in CLI_WRITES_DB and not _db_outside_data(env, cwd):
            return "cyclebeat.cli load writes data/: prefix RUNTIME_DB_PATH=<path outside data/>"
    if head == "docker" and "compose" in cmd and set(cmd) & PIPELINE_SERVICES:
        if not ({"down", "ps", "logs", "config"} & set(cmd)):
            return "the compose pipeline profile mounts and writes data/ and lake/"
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
        return sub in GIT_READ
    if head == "sed":
        return not any(w == "-i" or w.startswith(("-i", "--in-place")) for w in cmd[1:])
    if head == "ruff":
        return "check" in cmd and "--fix" not in cmd
    return True


def _bash(command: str, cwd: Path, branch_of: BranchOf) -> str | None:
    switched_to_main = False
    for words, redirects in _segments(_tokens(command)):
        env, cmd = _command(words)
        for word in words + [t for _, t in redirects]:
            for part in (word, word.split("=", 1)[-1]):
                if is_secret(part):
                    return f"secrets files are never read or written by the agent ({_base(part)})"
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
        head = _base(cmd[0]) if cmd else ""
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


def decide(event: dict[str, object], branch_of: BranchOf = _current_branch) -> str | None:
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
        return _bash(str(data.get("command", "")), cwd, branch_of)
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
