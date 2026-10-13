"""The PreToolUse guardrail (`agent-hooks/pre_tool_use.py`, criterion 12).

Two lists of real tool calls: what must pass and what must be refused. The owner asked for at
least as many "allowed" cases as "refused" ones, because a hook that blocks normal work gets
switched off; `test_the_allowed_list_is_not_shorter` holds that. The branch is injected, so no
case depends on what this checkout has checked out. The last tests run the script as Claude
Code does: JSON on stdin, exit code 2 and a reason on stderr.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-hooks" / "pre_tool_use.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pre_tool_use", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load()


def bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}


def tool(name: str, **tool_input: str) -> dict[str, Any]:
    return {"tool_name": name, "tool_input": tool_input, "cwd": str(ROOT)}


ALLOWED: list[tuple[str, dict[str, Any], str]] = [
    # the owner's explicit cases
    ("git status", bash("git status"), "feature"),
    ("make test-unit", bash("make test-unit"), "feature"),
    ("git log -- data/", bash("git log --oneline -- data/"), "feature"),
    ("ls data/", bash("ls -la data/"), "feature"),
    ("a path that only contains the word data", bash("cat frontend/src/data/zones.ts"), "feature"),
    ("the word data as an argument", bash("pytest -k data tests/unit"), "feature"),
    # reading the protected zones (criterion 6 needs it)
    ("stat the warehouse", bash("stat -c '%n %s %y' data/cyclebeat_runtime.duckdb"), "feature"),
    ("hash the footprint", bash("find data lake -type f -print0 | xargs -0 sha256sum"), "f"),
    ("du on lake", bash("du -sb data lake"), "feature"),
    ("grep in data", bash("grep -c track data/spike/raw_output.json"), "feature"),
    ("copy the warehouse out", bash("cp data/cyclebeat_runtime.duckdb /tmp/w.duckdb"), "f"),
    ("stage the hook", bash("git add agent-hooks/README.md"), "feature"),
    ("stage the settings", bash("git add .claude/settings.json"), "feature"),
    ("commit the settings", bash("git commit -m msg .claude/settings.json"), "feature"),
    ("diff the settings", bash("git diff .claude/settings.json"), "feature"),
    ("show the settings at HEAD", bash("git show HEAD:.claude/settings.json"), "feature"),
    ("log the hook folder", bash("git log --oneline -- agent-hooks/"), "feature"),
    # globs that cannot reach a secret (bash `*` skips dotfiles)
    ("a bare * glob", bash("ls dbt/models/*"), "feature"),
    ("a *.md glob", bash("cat docs/*.md"), "feature"),
    ("a ? glob", bash("ls tests/unit/test_?.py"), "feature"),
    ("a glob under data/", bash("ls -la data/*"), "feature"),
    # pipeline commands pointed away from data/
    ("dbt on a scratch warehouse", bash("RUNTIME_DB_PATH=/tmp/x.duckdb make dbt"), "feature"),
    ("compose without the pipeline", bash("docker compose up -d --build"), "feature"),
    ("compose down with the profile", bash("docker compose --profile pipeline down"), "f"),
    # git and gh, normal work
    ("push the work branch", bash("git push -u origin phase-7/extension-pack"), "phase-7"),
    ("push a refspec to a branch", bash("git push origin HEAD:feature"), "feature"),
    ("merge main into a branch", bash("git merge origin/main"), "feature"),
    ("pull on main", bash("git pull --ff-only"), "main"),
    ("commit message mentions data/", bash('git commit -m "docs: data/ is guarded"'), "f"),
    (
        "heredoc body mentions data/",
        bash("git commit -F - <<'EOF'\nfix: never write data/ or lake/\nEOF"),
        "feature",
    ),
    ("gh pr view", bash("gh pr view 37"), "feature"),
    ("gh run list", bash("gh run list --branch phase-7/extension-pack"), "feature"),
    # deploy code is testable, just not runnable
    ("the deploy tests", bash("uv run pytest tests/unit/test_deploy.py"), "feature"),
    ("reading deploy.py", bash("cat tools/deploy.py"), "feature"),
    # secrets templates and the guardrail's own tests
    ("the env template", bash("cat .env.example"), "feature"),
    ("read the env template", tool("Read", file_path=str(ROOT / ".env.example")), "f"),
    ("lint the hook", bash("uv run ruff check agent-hooks"), "feature"),
    ("run the hook by hand", bash("python3 agent-hooks/pre_tool_use.py < /tmp/e.json"), "f"),
    # file tools
    ("edit API code", tool("Edit", file_path=str(ROOT / "api" / "main.py")), "feature"),
    ("write a doc", tool("Write", file_path=str(ROOT / "docs" / "permissions.md")), "f"),
    ("write a data-named file", tool("Write", file_path=str(ROOT / "docs" / "data.md")), "f"),
    ("read the warehouse", tool("Read", file_path=str(ROOT / "data" / "demo_session.json")), "f"),
    ("read the hook", tool("Read", file_path=str(SCRIPT)), "feature"),
    ("fetch the docs", tool("WebFetch", url="https://code.claude.com/docs/en/hooks"), "f"),
    ("an MCP tool", {"tool_name": "mcp__cyclebeat-warehouse__query_marts"}, "feature"),
]

DENIED: list[tuple[str, dict[str, Any], str]] = [
    # writes to data/ and lake/
    ("Write into data/", tool("Write", file_path=str(ROOT / "data" / "x.json")), "f"),
    ("Edit in lake/", tool("Edit", file_path=str(ROOT / "lake" / "raw" / "x")), "f"),
    ("touch in data/", bash("touch data/probe"), "feature"),
    ("rm -rf lake", bash("rm -rf lake"), "feature"),
    ("copy into data/", bash("cp README.md data/"), "feature"),
    ("move out of data/", bash("mv data/demo_session.json /tmp/"), "feature"),
    ("redirect into data/", bash("echo x > data/probe.txt"), "feature"),
    ("sed -i in data/", bash("sed -i 's/a/b/' data/demo_session.json"), "feature"),
    ("cd then rm", bash("cd data && rm demo_session.json"), "feature"),
    ("find -delete", bash("find lake -name '*.parquet' -delete"), "feature"),
    ("git checkout over data/", bash("git checkout -- data/demo_session.json"), "f"),
    ("make ingest", bash("make ingest"), "feature"),
    ("make dbt on the real warehouse", bash("make dbt"), "feature"),
    ("dbt build", bash("uv run dbt build --project-dir dbt --profiles-dir dbt"), "f"),
    ("the compose pipeline", bash("docker compose --profile pipeline up -d"), "feature"),
    # secrets
    ("Read .env", tool("Read", file_path=str(ROOT / ".env")), "feature"),
    ("cat .env", bash("cat .env"), "feature"),
    ("grep .env.local", bash("grep KEY .env.local"), "feature"),
    ("glob over .env", bash("cat .env*"), "feature"),
    ("a private key", tool("Read", file_path="/home/u/.ssh/id_ed25519"), "feature"),
    # force push, push to main, merge into main
    ("git push --force", bash("git push --force"), "feature"),
    ("option after the branch", bash("git push origin main --force"), "feature"),
    ("-f combined", bash("git push -uf origin feature"), "feature"),
    ("force with lease", bash("git push --force-with-lease origin feature"), "feature"),
    ("plus refspec", bash("git push origin +feature"), "feature"),
    ("push to main", bash("git push origin main"), "feature"),
    ("push HEAD:main", bash("git push origin HEAD:main"), "feature"),
    ("merge on main", bash("git merge feature"), "main"),
    ("switch then merge", bash("git switch main && git merge feature"), "feature"),
    # PRs
    ("gh pr merge", bash("gh pr merge 999999"), "feature"),
    ("gh pr create", bash("gh pr create --fill"), "feature"),
    ("merge API", bash("gh api -X PUT repos/o/r/pulls/1/merge"), "feature"),
    # Render
    ("deploy hook", bash("curl -X POST 'https://api.render.com/deploy/srv-x?key=y'"), "f"),
    ("hook from env", bash('curl -fsS "$RENDER_DEPLOY_HOOK_API"'), "feature"),
    ("tools.deploy", bash("uv run python -m tools.deploy --smoke-only"), "feature"),
    # the guardrails themselves
    ("Edit the hook", tool("Edit", file_path=str(SCRIPT)), "feature"),
    ("sed -i the settings", bash("sed -i 's/a/b/' .claude/settings.json"), "feature"),
    ("redirect into the settings", bash("echo {} > .claude/settings.json"), "feature"),
    ("checkout over the settings", bash("git checkout -- .claude/settings.json"), "feature"),
    ("restore the hook", bash("git restore agent-hooks/pre_tool_use.py"), "feature"),
    # globs that can reach a secret
    ("a dot glob", bash("cat .e*"), "feature"),
    ("an ssh key glob", bash("cat ~/.ssh/id_*"), "feature"),
    ("a pem glob", bash("ls certs/*.pem"), "feature"),
    ("a key glob", bash("cat *.key"), "feature"),
]


def test_the_allowed_list_is_not_shorter() -> None:
    assert len(ALLOWED) >= len(DENIED)


@pytest.mark.parametrize(("case", "event", "branch"), ALLOWED, ids=[c[0] for c in ALLOWED])
def test_allowed(case: str, event: dict[str, Any], branch: str) -> None:
    assert hook.decide(event, branch_of=lambda _cwd: branch) is None


@pytest.mark.parametrize(("case", "event", "branch"), DENIED, ids=[c[0] for c in DENIED])
def test_denied(case: str, event: dict[str, Any], branch: str) -> None:
    assert hook.decide(event, branch_of=lambda _cwd: branch)


@pytest.mark.parametrize(
    "path",
    [".claude/settings.json", ".claude/settings.local.json"],
)
def test_the_settings_files_cannot_be_written(path: str) -> None:
    assert hook.decide(tool("Write", file_path=str(ROOT / path)), branch_of=lambda _c: "f")


def _run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], input=stdin, capture_output=True, text=True,
        timeout=30, check=False,
    )


def test_the_script_blocks_with_exit_2_and_a_reason() -> None:
    out = _run(json.dumps(bash("gh pr merge 999999")))
    assert out.returncode == 2
    assert "gh pr merge is the owner's action" in out.stderr


def test_the_script_lets_a_normal_call_through() -> None:
    out = _run(json.dumps(bash("git status")))
    assert (out.returncode, out.stderr) == (0, "")


def test_the_script_fails_closed_on_garbage() -> None:
    out = _run("this is not json")
    assert out.returncode == 2
    assert "failing closed" in out.stderr
