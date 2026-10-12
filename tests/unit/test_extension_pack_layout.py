"""The agent extension pack is where Claude Code loads it AND where the grading looks for it.

Criterion 12 (`docs/grading-criteria.md:45-50`) names the paths reviewers open; Claude Code
loads each element from its own place. This file pins both, so a move breaks a test rather than
a grade or a session.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_agents_md_is_a_pointer_with_no_rule_of_its_own() -> None:
    """One rule set: AGENTS.md once carried a diverged copy (V2 plan as a truth source)."""
    text = (ROOT / "AGENTS.md").read_text()
    assert "[`CLAUDE.md`](CLAUDE.md)" in text
    numbered = re.search(r"^\s*\d+\.\s", text, flags=re.MULTILINE)
    assert not numbered, "numbered rules belong in CLAUDE.md"
    assert "V2" not in text and "V3 plan" not in text


# The grading layout (docs/grading-criteria.md:45-50). `plugins/` rather than `custom-agent/`
# (owner decision). docs/demo.md joins this list with the owner's demo session.
GRADING_PATHS = [
    "agent-capabilities/README.md",
    "agent-hooks/pre_tool_use.py",
    "agent-hooks/README.md",
    "mcp-server/cyclebeat_warehouse.py",
    "mcp-server/README.md",
    "plugins/cyclebeat-agent-pack/.claude-plugin/plugin.json",
    "docs/agent-extension-pack.md",
    "docs/permissions.md",
]

# Where Claude Code actually loads each element from.
LOADED_FROM = [
    "CLAUDE.md",
    ".claude/skills/new-mart/SKILL.md",
    ".claude/agents/contract-guardian.md",
    ".claude/agents/dbt-reviewer.md",
    ".claude/settings.json",
    ".mcp.json",
]


def test_every_grading_path_exists() -> None:
    missing = [p for p in GRADING_PATHS if not (ROOT / p).is_file()]
    assert missing == []


def test_every_element_is_where_claude_code_loads_it() -> None:
    missing = [p for p in LOADED_FROM if not (ROOT / p).is_file()]
    assert missing == []


def test_the_pack_document_names_every_grading_path() -> None:
    text = (ROOT / "docs" / "agent-extension-pack.md").read_text()
    for folder in ("agent-capabilities/", "agent-hooks/", "mcp-server/", "plugins/"):
        assert folder in text, folder
    assert "permissions.md" in text


def test_the_settings_run_the_hook_in_the_repo_and_fail_closed() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    (entry,) = settings["hooks"]["PreToolUse"]
    (hook,) = entry["hooks"]
    assert hook["args"][-1] == "${CLAUDE_PROJECT_DIR}/agent-hooks/pre_tool_use.py"
    assert hook["onFailure"] == "block"
    for tool in ("Bash", "Read", "Edit", "Write", "WebFetch"):
        assert tool in entry["matcher"].split("|")
    deny = settings["permissions"]["deny"]
    for rule in ("Read(.env)", "Edit(/data/**)", "Edit(/lake/**)", "Bash(gh pr merge*)",
                 "Edit(/agent-hooks/**)", "Edit(/.claude/settings.json)"):
        assert rule in deny, rule


def test_the_mcp_registration_runs_the_server_in_mcp_server() -> None:
    servers = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]
    args = servers["cyclebeat-warehouse"]["args"]
    assert "mcp-server/cyclebeat_warehouse.py" in args
    assert (ROOT / "mcp-server" / "cyclebeat_warehouse.py").is_file()


def test_the_skill_is_named_and_cites_its_sources() -> None:
    text = (ROOT / ".claude" / "skills" / "new-mart" / "SKILL.md").read_text()
    assert text.startswith("---\nname: new-mart\ndescription: ")
    assert "## Sources this workflow was derived from" in text
