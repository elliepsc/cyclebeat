"""Generate `plugins/cyclebeat-agent-pack/` from the sources Claude Code already loads.

The plugin is a BUILD OUTPUT, like `frontend/src/api/schema.d.ts`: it is committed so a reviewer
can open it and `claude --plugin-dir` can load it, but nobody edits it. The single sources are:

* `.claude/skills/*/SKILL.md`  -> `skills/`
* `.claude/agents/*.md`        -> `agents/`
* `.mcp.json`                  -> `.mcp.json` (same server entry; Claude Code substitutes
  `${CLAUDE_PROJECT_DIR}` in a plugin's MCP configuration too,
  https://code.claude.com/docs/en/plugins/components#path-variables-and-persistent-data)

The guardrails (deny rules, hook) are NOT packaged: they stay in `.claude/settings.json`, where
they bind every session in this repo whether or not the plugin is installed.

    uv run python -m tools.build_plugin            # (re)generate
    uv run python -m tools.build_plugin --check    # exit 1 if the committed plugin drifted

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "cyclebeat-agent-pack"
OUT = ROOT / "plugins" / NAME

MANIFEST = {
    "name": NAME,
    "description": (
        "CycleBeat's agent extension pack: the new-mart workflow, the four review subagents "
        "and the read-only warehouse MCP server. Works inside a CycleBeat checkout."
    ),
}

README = """\
# plugins/cyclebeat-agent-pack/ — GENERATED, do not edit

Built by `make plugin` from the sources Claude Code loads in this repo
(`.claude/skills/`, `.claude/agents/`, `.mcp.json`); CI fails if this folder differs from what
`make plugin` produces. Edit the sources, then run `make plugin`.

| In the plugin | Source | Name once installed |
|---|---|---|
{rows}

The MCP server runs the code of the CycleBeat checkout (`${{CLAUDE_PROJECT_DIR}}`), so the plugin
works inside a clone of this repo only. The guardrails (deny rules and the PreToolUse hook) are not
in the plugin: they stay in `.claude/settings.json`. Names are prefixed with the plugin name only
for whoever installs the plugin; see `docs/agent-extension-pack.md`.

Load it without installing: `claude --plugin-dir plugins/cyclebeat-agent-pack`.
"""


def expected() -> dict[str, str]:
    """Every file of the plugin, relative path -> content."""
    files: dict[str, str] = {
        ".claude-plugin/plugin.json": json.dumps(MANIFEST, indent=2) + "\n",
    }
    rows: list[str] = []
    for skill in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        name = skill.parent.name
        files[f"skills/{name}/SKILL.md"] = skill.read_text()
        rows.append(f"| skill `{name}` | `.claude/skills/{name}/SKILL.md` | `/{NAME}:{name}` |")
    for agent in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        files[f"agents/{agent.name}"] = agent.read_text()
        rows.append(
            f"| subagent `{agent.stem}` | `.claude/agents/{agent.name}` | `{NAME}:{agent.stem}` |"
        )
    servers = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]
    files[".mcp.json"] = json.dumps({"mcpServers": servers}, indent=2) + "\n"
    for server in sorted(servers):
        rows.append(
            f"| MCP server `{server}` | `.mcp.json` | `mcp__plugin_{NAME}_{server}__<tool>` |"
        )
    files["README.md"] = README.format(rows="\n".join(rows))
    return files


def on_disk() -> dict[str, str]:
    if not OUT.is_dir():
        return {}
    return {
        str(path.relative_to(OUT)): path.read_text()
        for path in sorted(OUT.rglob("*"))
        if path.is_file()
    }


def drift() -> list[str]:
    want, have = expected(), on_disk()
    problems = [f"missing: {p}" for p in sorted(want.keys() - have.keys())]
    problems += [f"not generated: {p}" for p in sorted(have.keys() - want.keys())]
    problems += [f"differs: {p}" for p in sorted(want.keys() & have.keys()) if want[p] != have[p]]
    return problems


def build() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, content in expected().items():
        path = OUT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def _shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the plugin drifted")
    args = parser.parse_args(argv)
    if args.check:
        problems = drift()
        for line in problems:
            print(line)
        if problems:
            print(f"{_shown(OUT)} is stale: run `make plugin`", file=sys.stderr)
            return 1
        print(f"{_shown(OUT)} matches its sources")
        return 0
    build()
    print(f"wrote {_shown(OUT)} ({len(expected())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
