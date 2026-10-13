"""Criterion 13: what the supply chain is pinned to, and how `make audit` may scan.

A tag (`@v4`) can be repointed by the action's owner; a commit SHA cannot. The scanner images
follow the same rule: a version for the reader, a digest for the machine.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
MAKEFILE = (ROOT / "Makefile").read_text()

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$", flags=re.MULTILINE)
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^\s*#\s*v\d+\.\d+\.\d+\s*$")


def _uses() -> list[tuple[str, str, str]]:
    found = []
    for workflow in WORKFLOWS:
        for ref, rest in USES.findall(workflow.read_text()):
            found.append((workflow.name, ref, rest))
    return found


def test_there_are_actions_to_check() -> None:
    assert WORKFLOWS, "no workflow found"
    assert _uses(), "no `uses:` found: the pattern no longer matches the workflows"


def test_every_action_is_pinned_by_commit_sha_with_its_version() -> None:
    unpinned = [f"{name}: {ref}" for name, ref, _ in _uses() if not PINNED.match(ref)]
    assert not unpinned, f"pin by commit SHA, not by tag: {unpinned}"
    uncommented = [
        f"{name}: {ref}" for name, ref, rest in _uses() if not VERSION_COMMENT.match(rest)
    ]
    assert not uncommented, f"add the `# vX.Y.Z` the SHA stands for: {uncommented}"


def test_a_tag_is_refused_by_the_pattern() -> None:
    assert not PINNED.match("actions/checkout@v4")
    assert not PINNED.match("actions/checkout@main")
    assert PINNED.match("actions/checkout@11d5960a326750d5838078e36cf38b85af677262")


def test_scanner_images_are_pinned_by_version_and_digest() -> None:
    for var in ("SEMGREP_IMAGE", "GITLEAKS_IMAGE"):
        match = re.search(rf"^{var} := (\S+)$", MAKEFILE, flags=re.MULTILINE)
        assert match, f"{var} missing from the Makefile"
        assert re.fullmatch(r"[\w./-]+:v?\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", match.group(1)), (
            f"{var} must carry an exact version AND a digest: {match.group(1)}"
        )


def test_the_audit_never_reaches_the_working_tree_or_the_registry_login() -> None:
    audit = MAKEFILE[MAKEFILE.index("\naudit:") :]
    packs = re.search(r"^SEMGREP_PACKS := (.+)$", MAKEFILE, flags=re.MULTILINE)
    assert packs, "SEMGREP_PACKS missing from the Makefile"
    assert "auto" not in packs.group(1), "--config auto logs in to the registry"
    assert "semgrep scan --metrics=off" in MAKEFILE
    assert "git archive HEAD" in audit, "Semgrep scans the committed tree only"
    assert '"$(CURDIR)/.git:/repo/.git:ro"' in audit, "gitleaks mounts .git alone, read-only"
    assert '"$(CURDIR):' not in audit, "the working tree (and .env) is never mounted"
