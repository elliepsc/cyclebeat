"""tools/check_links.py must fail on dead links and pass on live ones."""

import subprocess
from pathlib import Path

from tools import check_links


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(root: Path) -> None:
    """A real git repo: since the ops/ log incident, a live link must point to a TRACKED file."""
    _git(root, "init", "-q")


def _track(root: Path) -> None:
    _git(root, "add", "-A")


def test_live_link_and_anchor_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _repo(tmp_path)
    _write(tmp_path, "other.md", "# Other\n\n## Some Heading\n")
    body = "[ok](other.md) [a](other.md#some-heading) [s](#top)\n# Top\n"
    page = _write(tmp_path, "page.md", body)
    _track(tmp_path)
    assert check_links.check(page) == []


def test_dead_file_and_missing_anchor_are_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _repo(tmp_path)
    _write(tmp_path, "other.md", "# Other\n")
    page = _write(tmp_path, "page.md", "[x](missing.md)\n[y](other.md#nope)\n")
    _track(tmp_path)
    problems = check_links.check(page)
    assert len(problems) == 2
    assert "dead link" in problems[0] and "missing anchor" in problems[1]


def test_external_urls_and_code_are_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    page = _write(
        tmp_path, "page.md", "[e](https://example.com/x) `[c](nope.md)`\n```\n[f](nope.md)\n```\n"
    )
    assert check_links.check(page) == []


def test_a_link_to_an_ignored_file_on_disk_is_reported(tmp_path: Path, monkeypatch) -> None:
    """The exact phase-10 case: ops/evidence/*.log present locally, ignored by `*.log`.

    check_links passed on the developer's machine (the file was on disk) and failed in CI
    (git never had it). A link must point to a file git tracks.
    """
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _repo(tmp_path)
    _write(tmp_path, ".gitignore", "*.log\n")
    _write(tmp_path, "ops/evidence/2026-10-15-postgres-down.log", "### exit=0\n")
    page = _write(
        tmp_path,
        "ops/incident.md",
        "[raw log](evidence/2026-10-15-postgres-down.log)\n",
    )
    _track(tmp_path)
    problems = check_links.check(page)
    assert len(problems) == 1
    assert "not tracked by git" in problems[0]
    assert "evidence/2026-10-15-postgres-down.log" in problems[0]


def test_a_tracked_file_and_a_tracked_folder_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _repo(tmp_path)
    _write(tmp_path, ".gitignore", "*.log\n!ops/evidence/*.log\n")
    _write(tmp_path, "ops/evidence/run.log", "x\n")
    page = _write(tmp_path, "ops/incident.md", "[log](evidence/run.log) [dir](evidence/)\n")
    _track(tmp_path)
    assert check_links.check(page) == []


def test_a_file_never_added_is_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _repo(tmp_path)
    page = _write(tmp_path, "page.md", "[n](new.md)\n")
    _track(tmp_path)
    _write(tmp_path, "new.md", "# New\n")
    problems = check_links.check(page)
    assert len(problems) == 1 and "not tracked by git" in problems[0]
