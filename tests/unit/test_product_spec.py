"""product-spec.md is a real spec, and its references have the right shape (issue #44).

Offline by design: no network, so the test checks the FORMAT of the references (`PR #N` for merged
work, `issue #N` for remaining work), never that a PR is merged or an issue open.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "product-spec.md"
STATUSES = {"Delivered", "Partial", "Planned"}
PR_REF = re.compile(r"\bPR #\d+\b")
ISSUE_REF = re.compile(r"\bissue #\d+\b")


def requirements(text: str) -> list[dict[str, str]]:
    """Rows of the FR / NFR tables: ID, requirement, criteria, status, evidence."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 5 and re.fullmatch(r"N?FR-\d{2}", cells[0]):
            keys = ("id", "requirement", "criteria", "status", "evidence")
            rows.append(dict(zip(keys, cells, strict=True)))
    return rows


def problems(row: dict[str, str]) -> list[str]:
    found = []
    if not row["requirement"] or not row["criteria"]:
        found.append("a requirement and at least one acceptance criterion")
    if row["status"] not in STATUSES:
        found.append(f"a status among {sorted(STATUSES)}, got {row['status']!r}")
    needs_pr = row["status"] in ("Delivered", "Partial")
    needs_issue = row["status"] in ("Planned", "Partial")
    if needs_pr and not PR_REF.search(row["evidence"]):
        found.append("a `PR #N` reference for the merged part")
    if needs_issue and not ISSUE_REF.search(row["evidence"]):
        found.append("an `issue #N` reference for the remaining part")
    return found


ROWS = requirements(SPEC.read_text()) if SPEC.is_file() else []


def test_the_spec_exists_and_has_requirements() -> None:
    assert SPEC.is_file()
    ids = [r["id"] for r in ROWS]
    assert any(i.startswith("FR-") for i in ids) and any(i.startswith("NFR-") for i in ids)
    assert len(ids) == len(set(ids)), "requirement IDs are unique"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_every_requirement_is_complete(row: dict[str, str]) -> None:
    assert problems(row) == [], f"{row['id']} needs " + "; ".join(problems(row))


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"status": "Delivered", "evidence": "PR 14"}, "PR #N"),
        ({"status": "Delivered", "evidence": "#14"}, "PR #N"),
        ({"status": "Planned", "evidence": "see the issues"}, "issue #N"),
        ({"status": "Partial", "evidence": "PR #35"}, "issue #N"),
        ({"status": "Done", "evidence": "PR #1"}, "a status"),
    ],
)
def test_a_malformed_row_is_reported(row: dict[str, str], expected: str) -> None:
    full = {"id": "FR-99", "requirement": "r", "criteria": "c", **row}
    assert any(expected in p for p in problems(full))


def test_the_spec_says_what_and_points_to_the_issues() -> None:
    text = SPEC.read_text()
    assert "says WHAT" in text
    assert "github.com/elliepsc/cyclebeat/issues" in text


@pytest.mark.parametrize("doc", ["README.md", "CLAUDE.md"])
def test_readme_and_claude_md_link_the_spec(doc: str) -> None:
    assert "(product-spec.md)" in (ROOT / doc).read_text()


def test_the_issue_template_has_every_section() -> None:
    template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "work-block.md").read_text()
    for section in (
        "**Context**",
        "**Acceptance criteria**",
        "**Out of scope**",
        "**Requirements served**",
        "**Definition of done**",
    ):
        assert section in template, section
