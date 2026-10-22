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
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
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
        return sub in GIT_READ
    if head == "sed":
        return not any(w == "-i" or w.startswith(("-i", "--in-place")) for w in cmd[1:])
    if head == "ruff":
        return "check" in cmd and "--fix" not in cmd
    return True


def _bash(command: str, cwd: Path, branch_of: BranchOf, depth: int = 0) -> str | None:
    switched_to_main = False
    for words, redirects in _segments(_tokens(command)):
        env, cmd = _command(words)
        skip = {len(words) - len(cmd) + i for i in _excluded(cmd)}
        for index, word in enumerate(words + [t for _, t in redirects]):
            if index in skip:
                continue  # `--exclude='.env*'` keeps a secret out; it reads nothing
            for part in (word, word.split("=", 1)[-1]):
                for variant in _brace_expand(part):
                    if is_secret(variant):
                        name = _base(variant)
                        return f"secrets files are never read or written by the agent ({name})"
        script = _nested_script(cmd)
        if script is not None:
            if depth >= MAX_NESTING:
                return "shells nested this deep are refused"
            refusal = _bash(script, cwd, branch_of, depth + 1)
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
