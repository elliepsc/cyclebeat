"""The committed plugin is exactly what `make plugin` generates from its sources (criterion 12).

CI also regenerates it and runs `git diff --exit-code` (ci.yml, "Generated plugin matches its
sources"); this test catches the same drift locally, and proves the check can fail.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools import build_plugin


def test_the_committed_plugin_matches_its_sources() -> None:
    assert build_plugin.drift() == [], "run `make plugin`"


def test_it_carries_the_skill_the_four_subagents_and_the_mcp_server() -> None:
    files = build_plugin.expected()
    assert "skills/new-mart/SKILL.md" in files
    assert sorted(p for p in files if p.startswith("agents/")) == [
        "agents/ai-workflow-scribe.md",
        "agents/contract-guardian.md",
        "agents/dbt-reviewer.md",
        "agents/security-auditor.md",
    ]
    servers = json.loads(files[".mcp.json"])["mcpServers"]
    project = json.loads((build_plugin.ROOT / ".mcp.json").read_text())["mcpServers"]
    assert servers == project
    assert json.loads(files[".claude-plugin/plugin.json"])["name"] == "cyclebeat-agent-pack"


def test_the_guardrails_are_not_packaged() -> None:
    """Deny rules and the hook stay in .claude/settings.json, binding every session here."""
    assert not any("hook" in path or "settings" in path for path in build_plugin.expected())


def test_the_check_fails_on_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    copy = tmp_path / "plugin"
    shutil.copytree(build_plugin.OUT, copy)
    monkeypatch.setattr(build_plugin, "OUT", copy)
    assert build_plugin.main(["--check"]) == 0

    (copy / "skills" / "new-mart" / "SKILL.md").write_text("edited by hand\n")
    (copy / "stray.md").write_text("not generated\n")
    (copy / "agents" / "dbt-reviewer.md").unlink()
    assert build_plugin.drift() == [
        "missing: agents/dbt-reviewer.md",
        "not generated: stray.md",
        "differs: skills/new-mart/SKILL.md",
    ]
    assert build_plugin.main(["--check"]) == 1
