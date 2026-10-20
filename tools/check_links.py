"""Fail on any dead relative link in the repo's Markdown files.

Standard library only (no new dependency). Checks inline links and images
``[text](target)`` whose target is a relative path, and ``#anchor`` fragments
against the headings of the target file. External URLs are not fetched: the
Zero cost rule (E.8) keeps the check offline and deterministic.

A target must be TRACKED by git (`git ls-files`, staged files included), not merely on
disk: an ignored file passes every local check and is missing in CI. Phase 10 hit it with
`ops/evidence/*.log`, kept out of git by `*.log`. A folder counts as tracked when git
tracks a file under it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:")


def markdown_files() -> list[Path]:
    """Tracked and untracked-but-not-ignored Markdown files (git is the source of truth)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in out.splitlines() if (ROOT / line).is_file()]


def tracked() -> tuple[set[str], set[str]]:
    """Files git tracks under ROOT (POSIX, relative), and every folder holding one."""
    out = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = set(out.splitlines())
    folders = {str(Path(f).parents[i]) for f in files for i in range(len(Path(f).parents) - 1)}
    return files, folders


def is_tracked(dest: Path, files: set[str], folders: set[str]) -> bool:
    try:
        rel = dest.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return False
    return rel in files or rel in folders or rel == "."


def slug(heading: str) -> str:
    """GitHub-style anchor: lowercase, drop punctuation, spaces to hyphens."""
    text = re.sub(r"[`*_]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (m := HEADING.match(line)):
            found.add(slug(m.group(1)))
    return found


def links(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            line = re.sub(r"`[^`]*`", "", line)
            found.extend((number, m.group(1)) for m in LINK.finditer(line))
    return found


def check(path: Path, index: tuple[set[str], set[str]] | None = None) -> list[str]:
    problems: list[str] = []
    for number, target in links(path):
        if target.startswith(SKIP_SCHEMES):
            continue
        file_part, _, fragment = target.partition("#")
        dest = path if not file_part else (path.parent / unquote(file_part)).resolve()
        where = f"{path.relative_to(ROOT)}:{number}"
        if not dest.exists():
            problems.append(f"{where}: dead link -> {target}")
        elif not is_tracked(dest, *(index := index if index is not None else tracked())):
            problems.append(
                f"{where}: target not tracked by git (ignored or never added) -> {target}"
            )
        elif fragment and dest.suffix == ".md" and slug(fragment) not in anchors(dest):
            problems.append(f"{where}: missing anchor -> {target}")
    return problems


def main() -> int:
    index = tracked()
    problems = [p for md in markdown_files() for p in check(md, index)]
    for problem in problems:
        print(problem)
    print(f"{len(problems)} dead link(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
