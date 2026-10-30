"""Replay of the issue #71 security-auditor findings against three versions of the hook.

    uv run python security/pr-audits/pr-71-replay.py <path/to/candidate/pre_tool_use.py>

Columns: 69b032e (before #71) and f618410 (patch 2), both read with `git show` and executed in
memory as modules whose `__file__` is the repository hook path; the candidate, read from the
path given and executed the same way, so the three columns share the repository's ROOT (a copy
under /tmp would otherwise see its zones under /tmp). Only `decide()` is called: no case is
ever run. The commit-check cases build throwaway git repositories in a temporary directory,
with fake keys built by concatenation.

Rows: the 51 cases of the first table (security/pr-audits/pr-71-hook-2-replay.md) and the 21 of
the second pass (security/pr-audits/pr-71-security-auditor-2.md, "Regressions against 69b032e").
Exit code 1 when a case 69b032e refused is allowed by the candidate (except the false positives
whose goal is "allowed"), or when a "refused" goal is missed.
"""

from __future__ import annotations

import hashlib
import inspect
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "agent-hooks" / "pre_tool_use.py"
NL = "\n"
FAKE = "0123456789abcdefABCDEF0123456789abcd"
TOKEN = "gh" + "p_" + FAKE


def _from_git(rev: str) -> types.ModuleType:
    source = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{rev}:agent-hooks/pre_tool_use.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    module = types.ModuleType(f"hook_{rev}")
    module.__file__ = str(HOOK)
    sys.modules[module.__name__] = module
    exec(compile(source, f"{rev}:agent-hooks/pre_tool_use.py", "exec"), module.__dict__)
    return module


def _from_path(path: Path) -> types.ModuleType:
    module = types.ModuleType("hook_candidate")
    module.__file__ = str(HOOK)
    sys.modules[module.__name__] = module
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    return module


def verdict(hook: types.ModuleType, command: str, cwd: Path | None = None) -> str | None:
    """The hook's refusal for `command`. A real git repo (`cwd`) gets the real commit check."""
    event = {"tool_name": "Bash", "tool_input": {"command": command},
             "cwd": str(cwd or hook.ROOT)}
    kwargs: dict[str, Any] = {"branch_of": lambda _cwd: "feature"}
    if cwd is None and "staged_of" in inspect.signature(hook.decide).parameters:
        kwargs["staged_of"] = lambda *_args: ""
    try:
        return hook.decide(event, **kwargs)
    except Exception as exc:  # main() turns any exception into exit 2
        return f"guardrail error ({type(exc).__name__}), failing closed"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True,
    )


def _repo(files: dict[str, str], stage: bool = True, born: bool = False) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="pr71-"))
    _git(repo, "init", "-q")
    if born:
        (repo / "base.txt").write_text("x\n")
        _git(repo, "add", "base.txt")
        _git(repo, "commit", "-qm", "base")
    for name, content in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(content)
        if stage:
            _git(repo, "add", "-f", name)
    return repo


ITEMS = " ".join(f"x{i}" for i in range(64))
# (finding, command, goal); goal "limit" = a documented gap (ROADMAP), either verdict is shown.
FIRST: list[tuple[str, str, str]] = [
    ("H1", "echo ${x:-$(rm -rf lake)}", "refused"),
    ("H1", "echo ${x:-$(cat .env)}", "refused"),
    ("H1", ": ${x:=`git push --force`}", "refused"),
    ("H2", "grep -e. .env", "refused"),
    ("H2", "rg -e. .env", "refused"),
    ("H2", "git grep --no-index -e. -- .env", "refused"),
    ("H3", "echo .env | xargs cat", "refused"),
    ("H3", "printf '%s\\n' .env | xargs -I{} cp {} /tmp/leak", "refused"),
    ("H3", "echo cat .env | sh", "refused"),
    ("H4", f"bash -euo pipefail -c '{NL}rm -rf lake{NL}'", "refused"),
    ("H4", f"find /tmp -maxdepth 0 -exec sh -c '{NL}cat .env{NL}' \\;", "refused"),
    ("H4", f"ssh localhost '{NL}cat ~/projets/cyclebeat/.env{NL}'", "refused"),
    ("H4", "bash -o pipefail -c 'rm -rf lake'", "refused"),
    ("M1", f"for d in {ITEMS} lake/raw; do rm -rf $d; done", "refused"),
    ("M1", "for d in lake/raw; do :; done; rm -rf $d", "refused"),
    ("M1", "for d in lake/raw; do cd $d && rm -f a.parquet; done", "refused"),
    ("M4", "gh api -X PATCH repos/o/r/issues/71 --input body.json", "refused"),
    ("M4", "gh api -X PATCH repos/o/r/issues/71 -fstate=closed", "refused"),
    ("M4", "gh api graphql -f query='mutation{closeIssue(input:{issueId:\"I\"})"
     "{clientMutationId}}'", "refused"),
    ("M4", "gh api -X PATCH 'repos/o/r/issues/71?x=1' -f state=closed", "refused"),
    ("M4", "gh api repos/o/r/pulls -fhead=x -fbase=main -ftitle=t", "refused"),
    ("M5", f"bash -o pipefail <<'X'{NL}rm -rf lake{NL}X", "refused"),
    ("M5", f"bash -euo pipefail <<'X'{NL}rm -rf lake{NL}X", "refused"),
    ("M5", f"python3 -W ignore - <<'X'{NL}import shutil; shutil.rmtree('lake'){NL}X", "refused"),
    ("M5", "python3 -X dev -c \"import shutil; shutil.rmtree('lake')\"", "refused"),
    ("L1", "(cd lake; case x in *) rm -f a.parquet;; esac)", "refused"),
    ("L1", "echo $(cd lake; case x in *) rm -f a.parquet;; esac)", "refused"),
    ("L2", "echo x\r#$(rm -rf lake)", "refused"),
    ("L3", "uv run python -m cyclebeat.cli --la lake ingest", "refused"),
    ("L3", "uv run python -m cyclebeat.cli --lake /tmp/x ingest --liv", "refused"),
    ("L3", "uv run python -m cyclebeat.cli --lake agent-hooks ingest", "refused"),
    ("L4", "python3 \"-cimport shutil;shutil.rmtree('lake')\"", "limit"),
    ("L4", "python3 -c \"import shutil as s; s.rmtree('lake')\"", "limit"),
    ("L4", "python3 -c \"import duckdb as d; d.connect('data/x.duckdb')\"", "limit"),
    ("L4", "python3 -c \"import subprocess as sp; sp.run(['make','ingest'])\"", "limit"),
    ("L5", "cat $'\\x2eenv'", "limit"),
    ("L5", "cat $\".env\"", "limit"),
    ("L5", "cat ${x:-.env}", "limit"),
    ("L5", "rm -rf ${x:-lake}", "limit"),
    ("L5", "cat {" + ",".join(f"a{i}" for i in range(300)) + ",.env}", "limit"),
    ("L5", "cd lake && rm -rf 2024 >/dev/null", "limit"),
    ("L5", "D=lake; D=/tmp | true; rm -rf $D", "limit"),
    ("L5", "cd lake; cd /tmp | true; rm -f x", "limit"),
    ("hash-object", "git hash-object agent-hooks/pre_tool_use.py", "allowed"),
    ("hash-object", "git hash-object -w agent-hooks/pre_tool_use.py", "refused"),
]
SECOND: list[tuple[str, str, str]] = [
    ("R1", "echo .env | tee /dev/null | xargs cat", "refused"),
    ("R1", "echo .env | cat | xargs cat", "refused"),
    ("R1", "printf '%s' .env | sed s/x/x/ | xargs cat", "refused"),
    ("R1", "echo .env | /usr/bin/xargs cat", "refused"),
    ("R1", "echo .env | while read f; do cat \"$f\"; done", "refused"),
    ("R1", "echo .env > /tmp/l; xargs cat < /tmp/l", "refused"),
    ("R2", f"stdbuf -oL bash -c '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"flock /tmp/l -c '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"script -qc '{NL}rm -rf lake{NL}' /dev/null", "refused"),
    ("R2", f"su -c '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"setsid bash -c '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"tmux new -d '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"parallel ::: '{NL}rm -rf lake{NL}'", "refused"),
    ("R2", f"git rebase -x '{NL}rm -rf lake{NL}' HEAD~1", "refused"),
    ("R2", f"git bisect run sh -c '{NL}rm -rf lake{NL}'", "refused"),
    ("R3", "for d in lake/raw; do rm -rf ${d%/}; done", "refused"),
    ("R3", "for d in lake/raw; do rm -rf ${d:-x}; done", "refused"),
    ("R3", "while read d; do rm -rf $d; done < <(echo lake/raw)", "refused"),
    ("R4", "(cd lake; case x in a) :;& b) rm -f a.parquet;; esac)", "refused"),
    ("R4", "echo $(cd lake; case x in a) :;& *) rm -f a.parquet;; esac)", "refused"),
    ("R (no impact)", "rg --files .env", "refused"),
]


def commit_cases() -> list[tuple[str, str, str, Path]]:
    """The six commit-check cases of the first table, each in its own throwaway repo."""
    staged = _repo({"config.py": f"v = '{TOKEN}'\n"})
    unborn = _repo({"config.py": "v = 'nothing'\n"})
    (unborn / "config.py").write_text(f"v = '{TOKEN}'\n")  # pathspec commit, no HEAD yet
    same = _repo({"config.py": f"v = '{TOKEN}'\n"}, stage=False, born=True)
    plus = _repo({"config.py": "++ " + TOKEN + "\n" + TOKEN + "\n"})
    pem = _repo({"certs/server.pem": "-----BEGIN " + "RSA PRIVATE KEY-----\nabc\n"})
    return [
        ("M2", 'cd "$(git rev-parse --show-toplevel)" && git commit -m x', "refused", staged),
        ("M2", "git commit -m x", "refused", staged),
        ("M2", "git commit -m x config.py  # unborn branch", "refused", unborn),
        ("M3a", "git add config.py && git commit -m x", "refused", same),
        ("M3b", "git commit -m x  # a '++ ' line, the token must not be echoed", "refused", plus),
        ("L6", "git commit -m x  # certs/server.pem staged", "refused", pem),
    ]


def main() -> int:
    candidate_path = Path(sys.argv[1]).resolve()
    hooks = {"69b032e": _from_git("69b032e"), "f618410": _from_git("f618410"),
             "candidate": _from_path(candidate_path)}
    script_commit = subprocess.run(
        ["git", "-C", str(REPO), "log", "-1", "--format=%h", "--", str(Path(__file__).resolve())],
        capture_output=True, text=True, check=False,
    ).stdout.strip() or "uncommitted"
    digest = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
    rows: list[tuple[str, str, str, list[str | None]]] = []
    for finding, command, goal in FIRST + SECOND:
        rows.append((finding, command, goal, [verdict(h, command) for h in hooks.values()]))
    for finding, label, goal, repo in commit_cases():
        command = label.split("  #", 1)[0]
        rows.append((finding, label, goal, [verdict(h, command, repo) for h in hooks.values()]))

    print("# Issue #71: replay of the security-auditor findings\n")
    print(f"Produced by `security/pr-audits/pr-71-replay.py` at commit `{script_commit}`; "
          f"candidate hook sha256 `{digest}`. Only `decide()` is called; no case is run. "
          "⏎ stands for a newline in the command.\n")
    print("| Finding | Case | Goal | 69b032e | f618410 | candidate |\n|---|---|---|---|---|---|")
    bad: list[str] = []
    leaked = False
    for finding, command, goal, verdicts in rows:
        cells = ["refused" if v else "allowed" for v in verdicts]
        shown = command.replace("\n", "⏎").replace("\r", "\\r").replace("|", "\\|")
        if len(shown) > 70:
            shown = shown[:67] + "..."
        print(f"| {finding} | `{shown}` | {goal} | {' | '.join(cells[:2])} | **{cells[2]}** |")
        regression = verdicts[0] and not verdicts[2] and goal != "allowed"
        missed = (goal == "refused" and not verdicts[2]) or (goal == "allowed" and verdicts[2])
        if regression or missed:
            bad.append(f"{finding}: {command!r}")
        if finding == "M3b" and verdicts[2] and FAKE in verdicts[2]:
            leaked = True
            bad.append("M3b: the candidate's refusal echoes the token")
    print(f"\n{len(rows)} cases. Refused by 69b032e and allowed by the candidate (false positives "
          f"aside), or goal missed: {len(bad)}. M3b token echoed by the candidate: {leaked}.")
    for line in bad:
        print(f"- {line}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
