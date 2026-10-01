"""tools/check_links.py must fail on dead links and pass on live ones."""

from pathlib import Path

from tools import check_links


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_live_link_and_anchor_pass(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _write(tmp_path, "other.md", "# Other\n\n## Some Heading\n")
    body = "[ok](other.md) [a](other.md#some-heading) [s](#top)\n# Top\n"
    page = _write(tmp_path, "page.md", body)
    assert check_links.check(page) == []


def test_dead_file_and_missing_anchor_are_reported(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    _write(tmp_path, "other.md", "# Other\n")
    page = _write(tmp_path, "page.md", "[x](missing.md)\n[y](other.md#nope)\n")
    problems = check_links.check(page)
    assert len(problems) == 2
    assert "dead link" in problems[0] and "missing anchor" in problems[1]


def test_external_urls_and_code_are_ignored(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    page = _write(
        tmp_path, "page.md", "[e](https://example.com/x) `[c](nope.md)`\n```\n[f](nope.md)\n```\n"
    )
    assert check_links.check(page) == []
