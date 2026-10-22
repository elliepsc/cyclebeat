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


def test_no_semgrep_rule_is_excluded_globally() -> None:
    assert "--exclude-rule" not in MAKEFILE, "accept a finding with a targeted nosemgrep instead"


def test_the_only_semgrep_exception_is_targeted_and_justified() -> None:
    """One accepted finding: the API image runs as root. Named rule, reason above it, one file."""
    rule = "nosemgrep: dockerfile.security.missing-user.missing-user"
    api = (ROOT / "Dockerfile").read_text().splitlines()
    marks = [i for i, line in enumerate(api) if "nosemgrep" in line]
    assert len(marks) == 1 and api[marks[0]].strip() == f"# {rule}"
    assert api[marks[0] + 1].startswith("CMD "), "the exception sits right above the CMD it covers"
    assert "root" in " ".join(api[marks[0] - 4 : marks[0]]), "the reason is written above it"
    assert "nosemgrep" not in (ROOT / "frontend" / "Dockerfile").read_text()


# Criterion 13: the five artifacts at the paths the grid expects (security/, ops/), reachable
# from the README. A path the grid names must exist as a real file, not only as a promise.
SECURITY_ARTIFACTS = [
    "security/README.md",
    "security/pr-audits/pr-38.md",
    "security/pr-audits/pr-38-triage.md",
    "security/scans/2026-10-20.md",
    "security/agent-security.md",
    "security/ai-policy.md",
    "ops/README.md",
    "ops/incident-2026-10-15-postgres-down.md",
    "ops/evidence/2026-10-15-postgres-down.log",
]


def test_every_criterion_13_artifact_exists() -> None:
    missing = [p for p in SECURITY_ARTIFACTS if not (ROOT / p).is_file()]
    assert not missing, f"missing criterion-13 artifacts: {missing}"


def test_the_security_index_names_every_artifact() -> None:
    index = (ROOT / "security" / "README.md").read_text()
    for path in SECURITY_ARTIFACTS[1:6] + ["ops/incident-2026-10-15-postgres-down.md"]:
        name = path.removeprefix("security/")
        assert name in index or f"../{path}" in index, f"security/README.md does not name {path}"


def test_the_readme_points_to_security_and_ops() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "## Security & ops" in readme
    assert "(security/README.md)" in readme and "(ops/README.md)" in readme


def test_the_exposure_window_records_the_owner_decision() -> None:
    """The key-rotation decision is the owner's, recorded as hers, with its date."""
    notes = (ROOT / "security" / "agent-security.md").read_text()
    assert "Exposure window, PR #38 to PR #41" in notes
    assert "décision de la propriétaire (22 October 2026)" in notes
    assert "[à compléter]" not in notes
