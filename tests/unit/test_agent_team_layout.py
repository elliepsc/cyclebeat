"""One test command, and one description of the agent team (issue #45).

`make test` is driven for real, with `RUN` and `IT_COMPOSE` replaced by `true` / `false`, so the
chaining and the exit status are checked offline: no pytest run, no Docker.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEAM = ROOT / "docs" / "agent-team.md"
AGENTS_DIR = ROOT / ".claude" / "agents"


def _make_test(**overrides: str) -> subprocess.CompletedProcess[str]:
    args = ["make", "--no-print-directory", "-C", str(ROOT), "test"]
    args += [f"{name}={value}" for name, value in overrides.items()]
    # A parent `make -i` (or any MAKEFLAGS) would leak into the child make and hide its status.
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL")}
    return subprocess.run(args, capture_output=True, text=True, timeout=60, check=False, env=env)


def test_make_test_stops_on_a_unit_failure_and_names_it() -> None:
    result = _make_test(RUN="false", IT_COMPOSE="echo INTEGRATION-STARTED")
    assert result.returncode != 0
    assert "FAILED in the unit suite" in result.stderr
    assert "INTEGRATION-STARTED" not in result.stdout + result.stderr


def test_make_test_fails_when_the_integration_suite_fails() -> None:
    # `IT_COMPOSE=false` is what a missing Docker looks like to the recipe: `up` fails.
    result = _make_test(RUN="true", IT_COMPOSE="false")
    assert result.returncode != 0
    assert "FAILED in the integration suite" in result.stderr


def test_make_test_passes_when_both_suites_pass() -> None:
    result = _make_test(RUN="true", IT_COMPOSE="true")
    assert result.returncode == 0, result.stderr
    assert "unit and integration suites passed" in result.stdout


def test_make_test_runs_the_suites_in_order_not_as_prerequisites() -> None:
    """Prerequisites would run in parallel under `make -j`."""
    makefile = (ROOT / "Makefile").read_text()
    match = re.search(r"^test:(.*)\n((?:\t.*\n)+)", makefile, flags=re.MULTILINE)
    assert match, "no `test` target in the Makefile"
    assert match.group(1).strip() == "", "`make test` must not list the suites as prerequisites"
    recipe = match.group(2)
    assert recipe.index("test-unit") < recipe.index("test-integration")


def test_agent_team_page_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "docs/agent-team.md"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tracked.returncode == 0, "docs/agent-team.md must be tracked by git"


def test_agent_team_page_names_every_subagent_and_the_owner() -> None:
    text = TEAM.read_text()
    agents = sorted(path.stem for path in AGENTS_DIR.glob("*.md"))
    assert agents, "no subagent definition found"
    missing = [name for name in agents if f"`{name}`" not in text]
    assert not missing, f"subagents missing from docs/agent-team.md: {missing}"
    for section in ("## Roles", "## The process", "## What only the owner", "## Where each trace"):
        assert section in text, f"docs/agent-team.md lost its section {section!r}"
    for trace in ("security/pr-audits/", "docs/ai-workflow.md", "issue"):
        assert trace in text


@pytest.mark.parametrize(
    ("source", "link"),
    [("CLAUDE.md", "(docs/agent-team.md)"), ("AGENTS.md", "(docs/agent-team.md)")],
)
def test_entry_points_link_to_the_agent_team_page(source: str, link: str) -> None:
    assert link in (ROOT / source).read_text(), f"{source} must link to docs/agent-team.md"
