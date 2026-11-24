"""The README's rubric map has one row per criterion of the official grid (issue #70).

The grid is the verbatim copy in docs/grading-criteria.md: its criteria are the `### ` headings
inside the fenced source text. The map is the table under `## Rubric map` in README.md. Offline:
the test compares the two files, never the course repository.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRID = ROOT / "docs" / "grading-criteria.md"
README = ROOT / "README.md"


def grid_criteria(text: str) -> list[str]:
    """The `### ` headings of the grid, in order, after its `## Criteria` heading."""
    section = text.split("\n## Criteria\n", 1)[1].split("\n## ", 1)[0]
    return [m.group(1).strip() for m in re.finditer(r"^### (.+)$", section, re.MULTILINE)]


def map_rows(text: str) -> list[tuple[int, str]]:
    """(#, criterion) of each row of the table under `## Rubric map`."""
    section = text.split("\n## Rubric map\n", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].isdigit():
            rows.append((int(cells[0]), cells[1]))
    return rows


def test_the_grid_has_twelve_criteria() -> None:
    # Guards the parser: a grid read as empty would make the map test pass on anything.
    assert len(grid_criteria(GRID.read_text())) == 12


def test_the_map_has_one_row_per_criterion_with_the_same_name() -> None:
    criteria = grid_criteria(GRID.read_text())
    rows = map_rows(README.read_text())
    assert [name for _, name in rows] == criteria
    assert [number for number, _ in rows] == list(range(1, len(criteria) + 1))
