"""The agent extension pack is where Claude Code loads it AND where the grading looks for it.

Criterion 12 (`docs/grading-criteria.md:45-50`) names the paths reviewers open; Claude Code
loads each element from its own place. This file pins both, so a move breaks a test rather than
a grade or a session.
"""

from __future__ import annotations

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
