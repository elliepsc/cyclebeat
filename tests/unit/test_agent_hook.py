"""The PreToolUse guardrail (`agent-hooks/pre_tool_use.py`, criterion 12).

Two lists of real tool calls: what must pass and what must be refused. The owner asked for at
least as many "allowed" cases as "refused" ones, because a hook that blocks normal work gets
switched off; `test_the_allowed_list_is_not_shorter` holds that. The branch is injected, so no
case depends on what this checkout has checked out, and so is the read of the change to commit
(issue #71, candidate 7), except in the tests that build a git repository for it. The last tests
run the script as Claude Code does: JSON on stdin, exit code 2 and a reason on stderr.

Issue #71: the six recorded false positives are replayed verbatim from
`tests/fixtures/hook_false_positives.json`; every case added for #71 was first run against the
hook at 69b032e: an added allowed case was refused there and an added refused case went through.
A case named "pin: ..." holds a verdict the old hook already gave (a guard the new parsing must
not lose); it was shown red on a mutation of the new hook instead (docs/ai-workflow.md, #71).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-hooks" / "pre_tool_use.py"
FALSE_POSITIVES = json.loads(
    (ROOT / "tests" / "fixtures" / "hook_false_positives.json").read_text()
)["cases"]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pre_tool_use", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load()


def bash(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}


def tool(name: str, **tool_input: str) -> dict[str, Any]:
    return {"tool_name": name, "tool_input": tool_input, "cwd": str(ROOT)}


ALLOWED: list[tuple[str, dict[str, Any], str]] = [
    # the owner's explicit cases
    ("git status", bash("git status"), "feature"),
    ("make test-unit", bash("make test-unit"), "feature"),
    ("git log -- data/", bash("git log --oneline -- data/"), "feature"),
    ("ls data/", bash("ls -la data/"), "feature"),
    ("a path that only contains the word data", bash("cat frontend/src/data/zones.ts"), "feature"),
    ("the word data as an argument", bash("pytest -k data tests/unit"), "feature"),
    # reading the protected zones (criterion 6 needs it)
    ("stat the warehouse", bash("stat -c '%n %s %y' data/cyclebeat_runtime.duckdb"), "feature"),
    ("hash the footprint", bash("find data lake -type f -print0 | xargs -0 sha256sum"), "f"),
    ("du on lake", bash("du -sb data lake"), "feature"),
    ("grep in data", bash("grep -c track data/spike/raw_output.json"), "feature"),
    ("copy the warehouse out", bash("cp data/cyclebeat_runtime.duckdb /tmp/w.duckdb"), "f"),
    ("stage the hook", bash("git add agent-hooks/README.md"), "feature"),
    ("stage the settings", bash("git add .claude/settings.json"), "feature"),
    ("commit the settings", bash("git commit -m msg .claude/settings.json"), "feature"),
    ("diff the settings", bash("git diff .claude/settings.json"), "feature"),
    ("show the settings at HEAD", bash("git show HEAD:.claude/settings.json"), "feature"),
    ("log the hook folder", bash("git log --oneline -- agent-hooks/"), "feature"),
    # globs that cannot reach a secret (bash `*` skips dotfiles)
    ("a bare * glob", bash("ls dbt/models/*"), "feature"),
    ("a *.md glob", bash("cat docs/*.md"), "feature"),
    ("a ? glob", bash("ls tests/unit/test_?.py"), "feature"),
    ("a glob under data/", bash("ls -la data/*"), "feature"),
    # pipeline commands pointed away from data/
    ("dbt on a scratch warehouse", bash("RUNTIME_DB_PATH=/tmp/x.duckdb make dbt"), "feature"),
    ("compose without the pipeline", bash("docker compose up -d --build"), "feature"),
    ("compose down with the profile", bash("docker compose --profile pipeline down"), "f"),
    # git and gh, normal work
    ("push the work branch", bash("git push -u origin phase-7/extension-pack"), "phase-7"),
    ("push a refspec to a branch", bash("git push origin HEAD:feature"), "feature"),
    ("merge main into a branch", bash("git merge origin/main"), "feature"),
    ("pull on main", bash("git pull --ff-only"), "main"),
    ("commit message mentions data/", bash('git commit -m "docs: data/ is guarded"'), "f"),
    (
        "heredoc body mentions data/",
        bash("git commit -F - <<'EOF'\nfix: never write data/ or lake/\nEOF"),
        "feature",
    ),
    ("gh pr view", bash("gh pr view 37"), "feature"),
    ("gh run list", bash("gh run list --branch phase-7/extension-pack"), "feature"),
    # deploy code is testable, just not runnable
    ("the deploy tests", bash("uv run pytest tests/unit/test_deploy.py"), "feature"),
    ("reading deploy.py", bash("cat tools/deploy.py"), "feature"),
    # secrets templates and the guardrail's own tests
    ("the env template", bash("cat .env.example"), "feature"),
    ("read the env template", tool("Read", file_path=str(ROOT / ".env.example")), "f"),
    ("lint the hook", bash("uv run ruff check agent-hooks"), "feature"),
    ("run the hook by hand", bash("python3 agent-hooks/pre_tool_use.py < /tmp/e.json"), "f"),
    # file tools
    ("edit API code", tool("Edit", file_path=str(ROOT / "api" / "main.py")), "feature"),
    ("write a doc", tool("Write", file_path=str(ROOT / "docs" / "permissions.md")), "f"),
    ("write a data-named file", tool("Write", file_path=str(ROOT / "docs" / "data.md")), "f"),
    ("read the warehouse", tool("Read", file_path=str(ROOT / "data" / "demo_session.json")), "f"),
    ("read the hook", tool("Read", file_path=str(SCRIPT)), "feature"),
    ("fetch the docs", tool("WebFetch", url="https://code.claude.com/docs/en/hooks"), "f"),
    ("an MCP tool", {"tool_name": "mcp__cyclebeat-warehouse__query_marts"}, "feature"),
    # ── PR #38 audit (H2, M2, M3): what the new rules must keep allowing ──────────────────
    ("rm -rf a scratch folder", bash("rm -rf /tmp/scratch-x"), "feature"),
    ("rm -rf a build folder", bash("rm -rf frontend/dist"), "feature"),
    ("rm -r a named folder", bash("rm -r build"), "feature"),
    ("a non-recursive rm on a glob", bash("rm -f api/*.pyc"), "feature"),
    ("rm one file", bash("rm tests/unit/__pycache__/x.pyc"), "feature"),
    ("find -exec under tests/", bash("find tests -name __pycache__ -exec rm -rf {} +"), "f"),
    ("find without a write", bash("find . -name '*.md'"), "feature"),
    ("find -delete in /tmp", bash("find /tmp/scratch-x -delete"), "feature"),
    ("find -delete under api/", bash("find api -name '*.pyc' -delete"), "feature"),
    ("bash -c a test run", bash("bash -c 'make test-unit'"), "feature"),
    ("sh -c an echo", bash("sh -c 'echo hello'"), "feature"),
    ("bash -lc pytest", bash("bash -lc 'uv run pytest -q'"), "feature"),
    ("eval an echo", bash("eval echo ok"), "feature"),
    ("bash -c read-only git", bash("bash -c 'git status && git log --oneline -3'"), "f"),
    ("braces over docs", bash("cat docs/{ROADMAP,demo}.md"), "feature"),
    ("braces in mkdir", bash("mkdir -p /tmp/scratch-x/{a,b}"), "feature"),
    ("braces in an echo", bash("echo {1,2,3}"), "feature"),
    ("grep -rn on subfolders", bash("grep -rn API_KEY api tests"), "feature"),
    ("grep -rn on the root, .env excluded", bash("grep -rn KEY . --exclude='.env*'"), "f"),
    ("grep without -r", bash("grep -n KEY README.md"), "feature"),
    ("grep -R on docs/", bash("grep -R TODO docs/"), "feature"),
    ("grep -r outside the repo", bash("grep -rn KEY /tmp/scratch-x"), "feature"),
    ("rg, restricted by default", bash("rg KEY"), "feature"),
    ("rg -uu with .env excluded", bash("rg -uu KEY -g '!.env*'"), "feature"),
    ("rg --hidden on a subfolder", bash("rg --hidden KEY api"), "feature"),
    ("tar a subfolder", bash("tar czf /tmp/docs.tgz docs"), "feature"),
    ("tar the root, .env excluded", bash("tar czf /tmp/x.tgz --exclude='.env*' ."), "f"),
    ("zip a subfolder", bash("zip -r /tmp/docs.zip docs"), "feature"),
    ("gh api list PRs", bash("gh api repos/o/r/pulls"), "feature"),
    ("gh api read a PR", bash("gh api repos/o/r/pulls/41"), "feature"),
    ("gh api graphql query", bash("gh api graphql -f query='query{viewer{login}}'"), "f"),
    ("gh api read a file", bash("gh api -X GET repos/o/r/contents/README.md"), "feature"),
    (
        "gh api write a file on a branch",
        bash("gh api -X PUT repos/o/r/contents/x.md -f message=m -f content=x -f branch=f"),
        "feature",
    ),
    # ── issue #44: the tracker stays usable; only closing is the merged PR's job ─────────
    ("gh issue view", bash("gh issue view 44"), "feature"),
    ("gh issue comment", bash("gh issue comment 44 --body-file /tmp/plan.md"), "feature"),
    ("gh issue create", bash("gh issue create --title t --body-file /tmp/b.md"), "feature"),
    ("gh issue edit, add a label", bash("gh issue edit 44 --add-label docs"), "feature"),
    ("gh issue edit, remove a label", bash("gh issue edit 44 --remove-label docs"), "feature"),
    ("gh issue edit, a title", bash("gh issue edit 44 --title 'Product spec'"), "feature"),
    ("gh issue list --state closed", bash("gh issue list --state closed"), "feature"),
    # ── issue #71: the six recorded false positives, verbatim ─────────────────────────────
    *[(fp["id"], bash(fp["command"]), "feature") for fp in FALSE_POSITIVES],
    # ── issue #71: what bash hands over as data is not read as paths or commands ─────────
    ("a one-line message that starts with lake/", bash("git commit -m 'lake/raw is fixed'"), "f"),
    (
        "a multi-line -am message",
        bash('git commit -am "docs: data/ and lake/\n\nmake ingest is unchanged"'),
        "feature",
    ),
    (
        "pin: a heredoc message inside $( )",
        bash("git commit -m \"$(cat <<'EOF'\nfix: make ingest (lake/) stays\nEOF\n)\""),
        "feature",
    ),
    ("pin: a heredoc fed to cat", bash("cat <<'EOF'\nmake ingest\nrm -rf lake\nEOF"), "feature"),
    ("pin: an unquoted heredoc fed to cat", bash("cat <<EOF\nrm -rf lake\nEOF"), "feature"),
    ("a quoted grep pattern naming .env", bash("grep -n '.env' README.md"), "feature"),
    ("a grep -e pattern naming .env", bash("grep -n -e .env.local docs/permissions.md"), "f"),
    ("git log --grep naming .env", bash("git log --oneline --grep=.env"), "feature"),
    ("git grep for .env", bash("git grep -n .env -- docs"), "feature"),
    ("printf naming .env", bash("printf '%s\\n' .env"), "feature"),
    ("pin: a read in a double-quoted $( )", bash('echo "$(git rev-parse --short HEAD)"'), "f"),
    ("pin: a comment with an apostrophe", bash("ls docs  # don't list data/"), "feature"),
    ("a subshell cd does not leak", bash("(cd data && ls) && rm demo_session.json"), "f"),
    ("pin: a variable outside data/", bash("S=/tmp/scratch-x && echo x > $S/probe"), "feature"),
    (
        "a for loop that reads",
        bash('for f in data/a.json lake/b; do wc -c "$f"; done'),
        "feature",
    ),
    # python -c (owner decision P1): reads and writes elsewhere pass
    ("pin: python -c reads lake/", bash("python3 -c \"print(open('lake/x.json').read())\""), "f"),
    (
        "pin: python -c reads data/ with pathlib",
        bash("python3 -c \"from pathlib import Path; print(Path('data/x.json').read_text())\""),
        "feature",
    ),
    (
        "pin: python -c duckdb read_only on data/",
        bash(
            "uv run python -c \"import duckdb; "
            "duckdb.connect('data/cyclebeat_runtime.duckdb', read_only=True)\""
        ),
        "feature",
    ),
    ("pin: python -c writes /tmp", bash("python3 -c \"open('/tmp/x.txt','w').write('1')\""), "f"),
    (
        "pin: python heredoc edits a doc",
        bash("python3 - <<'EOF'\np='docs/x.md'\nopen(p,'w').write('lake/ data/')\nEOF"),
        "feature",
    ),
    (
        "pin: python -c runs a read",
        bash("python3 -c \"import subprocess; subprocess.run(['ls','data'])\""),
        "feature",
    ),
    # cyclebeat.cli: help, and a lake outside the repo
    ("cyclebeat.cli ingest --help", bash("uv run python -m cyclebeat.cli ingest --help"), "f"),
    ("cyclebeat.cli load --help", bash("uv run python -m cyclebeat.cli load --help"), "f"),
    (
        "pin: cyclebeat.cli ingest, scratch lake",
        bash("uv run python -m cyclebeat.cli --lake /tmp/scratch-x/lake ingest"),
        "feature",
    ),
    (
        "cyclebeat.cli ingest, --lake=",
        bash("uv run python -m cyclebeat.cli --lake=/tmp/scratch-x/lake ingest"),
        "feature",
    ),
    (
        "pin: cyclebeat.cli load, scratch db",
        bash("uv run python -m cyclebeat.cli --lake /tmp/l load --db /tmp/scratch-x/w.duckdb"),
        "feature",
    ),
    # the tracker stays usable
    ("pin: gh issue edit a body", bash("gh issue edit 71 --body-file /tmp/b.md"), "feature"),
    ("pin: gh api read an issue", bash("gh api repos/o/r/issues/71"), "feature"),
    ("pin: gh api comment on an issue", bash("gh api repos/o/r/issues/71/comments -f body=x"), "f"),
    (
        "pin: gh api edit an issue title",
        bash("gh api -X PATCH repos/o/r/issues/71 -f title=t"),
        "feature",
    ),
    # ── issue #71, security-auditor pass 1: what the fixes must keep allowed ──
    ("hash-object reads a file", bash("git hash-object agent-hooks/pre_tool_use.py"), "f"),
    ("hash-object reads data/", bash("git hash-object data/x.parquet"), "feature"),
    ("hash-object with -t", bash("git -C . hash-object -t blob lake/a.parquet"), "feature"),
    ("pin: a ${} default is text", bash("echo ${HOME:-/tmp}"), "feature"),
    ("pin: a $() in a ${} default", bash('echo "${x:-$(git rev-parse HEAD)}"'), "feature"),
    ("pin: a ${:=} assignment", bash(": ${x:=default}"), "feature"),
    ("pin: grep -e .env as a pattern", bash("grep -e .env README.md"), "feature"),
    ("pin: rg -e .env as a pattern", bash("rg -e .env docs/"), "feature"),
    ("pin: git grep -e .env as a pattern", bash("git grep -e .env -- '*.md'"), "feature"),
    ("pin: grep -ie .env as a pattern", bash("grep -ie .env docs/"), "feature"),
    ("pin: echo into xargs echo", bash("echo hello | xargs echo"), "feature"),
    ("pin: printf into xargs -I", bash("printf '%s\\n' a b | xargs -I{} echo {}"), "feature"),
    ("pin: echo a command into sh", bash("echo ls | sh"), "feature"),
    ("pin: bash -o pipefail -c", bash("bash -o pipefail -c 'make lint'"), "feature"),
    ("pin: bash -euo pipefail -c reads", bash("bash -euo pipefail -c 'ls lake'"), "feature"),
    ("pin: find -exec wc", bash("find cyclebeat -name '*.py' -exec wc -l {} +"), "feature"),
    ("pin: ssh reads", bash("ssh localhost 'ls ~/projets/cyclebeat/lake'"), "feature"),
    ("sudo -u then a read", bash("sudo -u postgres cat data/x.csv"), "feature"),
    ("pin: watch git status", bash("watch -n 5 'git status'"), "feature"),
    ("pin: a loop that lists", bash("for d in lake/raw lake/staged; do ls $d; done"), "f"),
    (
        "pin: the loop variable after the loop",
        bash("for f in /tmp/a /tmp/b; do :; done; rm -f $f"),
        "f",
    ),
    ("pin: cd through a loop to read", bash("for d in lake/raw; do cd $d && ls; done"), "f"),
    ("pin: gh api reads an issue state", bash("gh api repos/o/r/issues/71 --jq .state"), "f"),
    (
        "pin: a GraphQL query on an issue",
        bash(
            "gh api graphql -f query='query{repository(owner:\"o\",name:\"r\")"
            "{issue(number:71){state}}}'"
        ),
        "feature",
    ),
    ("pin: gh api -ftitle= attached", bash("gh api -X PATCH repos/o/r/issues/71 -ftitle=t"), "f"),
    ("pin: gh api with a query string", bash("gh api 'repos/o/r/issues?state=closed'"), "f"),
    ("pin: gh api pulls with -q", bash("gh api repos/o/r/pulls -q '.[].title'"), "feature"),
    ("pin: heredoc to bash -o reads", bash("bash -o pipefail <<'X'\nls lake\nX"), "feature"),
    ("pin: heredoc to python -W", bash("python3 -W ignore - <<'X'\nprint(1)\nX"), "feature"),
    ("pin: python -X dev -c", bash('python3 -X dev -c "print(1)"'), "feature"),
    ("pin: a case that echoes", bash("case x in *) echo lake;; esac"), "feature"),
    ("pin: a case in a subshell reads", bash("(cd lake; case x in *) ls;; esac)"), "feature"),
    ("pin: a carriage return in a word", bash("echo a\rb"), "feature"),
    ("pin: cli --la to /tmp", bash("uv run python -m cyclebeat.cli --la /tmp/x ingest"), "f"),
    (
        "pin: cli --lim is --limit",
        bash("uv run python -m cyclebeat.cli --lake /tmp/x ingest --lim 5"),
        "feature",
    ),
    (
        "cli load --d to /tmp",
        bash("uv run python -m cyclebeat.cli load --d /tmp/x.duckdb"),
        "f",
    ),
    # ── issue #71, round 3: what is proven data, and normal work, stays allowed ──
    (
        "pin: a heredoc to gh is data",
        bash("gh issue comment 71 --body-file - <<'EOF'\nPosted by the coding agent (Claude Code)."
             "\nThe hook never reads .env; make ingest writes lake/.\nEOF"),
        "feature",
    ),
    (
        "pin: a heredoc to git commit -F is data",
        bash("git commit -F - <<'EOF'\nfix: x\n\nmentions .env and make ingest\nEOF"),
        "feature",
    ),
    (
        "pin: a heredoc to cat is data",
        bash("cat > /tmp/notes.md <<'EOF'\nnever run make ingest, never cat .env\nEOF"),
        "feature",
    ),
    ("pin: a heredoc to tee is data", bash("tee /tmp/a.md <<'EOF'\nrm -rf lake\nEOF"), "f"),
    ("pin: a heredoc to jq is data", bash("jq -R . <<'EOF'\ncat .env\nEOF"), "f"),
    ("pin: a heredoc to sort is data", bash("sort <<'EOF'\nmake ingest\nrm -rf lake\nEOF"), "f"),
    (
        "pin: a multi-line commit message is data",
        bash('git commit -q -m "fix: y (#71)\n\nBody mentions .env and rm -rf lake."'),
        "feature",
    ),
    ("pin: echo alone is data", bash("echo .env is never read"), "feature"),
    ("pin: printf alone is data", bash("printf '%s\\n' .env"), "feature"),
    (
        "pin: prose that does not parse is skipped",
        bash("gh issue comment 71 --body \"Posted by the coding agent (Claude Code).\n"
             "Plan: don't touch .env.\""),
        "feature",
    ),
    (
        "pin: a multi-line body that parses and is harmless",
        bash('gh issue comment 71 --body "Posted by the coding agent (Claude Code).\nAll green."'),
        "feature",
    ),
    (
        "pin: a multi-line script to stdbuf that reads",
        bash("stdbuf -oL bash -c '\nmake lint\nmake typecheck\n'"),
        "feature",
    ),
    ("pin: a multi-line script to tmux that reads", bash("tmux new -d '\nls lake\nls\n'"), "f"),
    ("pin: read then echo", bash('while read l; do echo "$l"; done < README.md'), "feature"),
    (
        "pin: a pipe into a read loop that reads",
        bash('git log --format=%s -5 | while read s; do echo "$s"; done'),
        "feature",
    ),
    ("pin: read a word then echo it", bash("read -r x <<< hello; echo $x"), "feature"),
    (
        "pin: read file names then count",
        bash('while read f; do wc -l "$f"; done < <(git ls-files docs)'),
        "feature",
    ),
    ("pin: ${f%/} outside the zones", bash("for f in /tmp/a/; do rm -rf ${f%/}; done"), "f"),
    ("pin: ${f:-x} outside the zones", bash("for f in /tmp/x; do rm -f ${f:-/tmp/y}; done"), "f"),
    (
        "pin: cd ${d%/} outside the zones",
        bash("for d in /tmp/x/; do cd ${d%/} && rm -f a; done"),
        "f",
    ),
    ("pin: case fall-through that echoes", bash("case x in a) echo a;& b) echo b;; esac"), "f"),
    ("pin: a captured rev-parse", bash('echo "$(git rev-parse HEAD)"'), "feature"),
    ("pin: a captured file list", bash("cat $(git ls-files tests | head -1)"), "feature"),
    ("pin: grep -f a pattern file", bash("grep -f patterns.txt README.md"), "feature"),
    ("pin: grep -if a pattern file", bash("grep -if words.txt docs/metrics.md"), "feature"),
    (
        "pin: a GraphQL updateIssue on the title",
        bash("gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",title:\"t\"})"
             "{clientMutationId}}'"),
        "feature",
    ),
    ("pin: zip -x keeps .env out", bash("zip -r /tmp/a.zip docs -x '.env*'"), "feature"),
    ("pin: a captured rev-parse redirected", bash('echo "$(git rev-parse HEAD)" > /tmp/h'), "f"),
    ("pin: printf into xargs -n1 echo", bash("printf '%s\\n' a b | xargs -n1 echo"), "feature"),
    ("pin: bash -O extglob -c", bash("bash -O extglob -c 'ls'"), "feature"),
    ("pin: ssh -p -i then a command", bash("ssh -p 22 -i ~/.ssh/k host uptime"), "feature"),
    ("pin: watch -n 1 ls", bash("watch -n 1 ls"), "feature"),
    ("pin: echo .env.example into xargs", bash("echo .env.example | xargs cat"), "feature"),
    ("pin: python -X importtime -c", bash("python3 -X importtime -c 'import json'"), "feature"),
    ("pin: printf with a carriage return", bash("printf 'a\rb\n' > /tmp/x"), "feature"),
]

DENIED: list[tuple[str, dict[str, Any], str]] = [
    # writes to data/ and lake/
    ("Write into data/", tool("Write", file_path=str(ROOT / "data" / "x.json")), "f"),
    ("Edit in lake/", tool("Edit", file_path=str(ROOT / "lake" / "raw" / "x")), "f"),
    ("touch in data/", bash("touch data/probe"), "feature"),
    ("rm -rf lake", bash("rm -rf lake"), "feature"),
    ("copy into data/", bash("cp README.md data/"), "feature"),
    ("move out of data/", bash("mv data/demo_session.json /tmp/"), "feature"),
    ("redirect into data/", bash("echo x > data/probe.txt"), "feature"),
    ("sed -i in data/", bash("sed -i 's/a/b/' data/demo_session.json"), "feature"),
    ("cd then rm", bash("cd data && rm demo_session.json"), "feature"),
    ("find -delete", bash("find lake -name '*.parquet' -delete"), "feature"),
    ("git checkout over data/", bash("git checkout -- data/demo_session.json"), "f"),
    ("make ingest", bash("make ingest"), "feature"),
    ("make dbt on the real warehouse", bash("make dbt"), "feature"),
    ("dbt build", bash("uv run dbt build --project-dir dbt --profiles-dir dbt"), "f"),
    ("the compose pipeline", bash("docker compose --profile pipeline up -d"), "feature"),
    # secrets
    ("Read .env", tool("Read", file_path=str(ROOT / ".env")), "feature"),
    ("cat .env", bash("cat .env"), "feature"),
    ("grep .env.local", bash("grep KEY .env.local"), "feature"),
    ("glob over .env", bash("cat .env*"), "feature"),
    ("a private key", tool("Read", file_path="/home/u/.ssh/id_ed25519"), "feature"),
    # force push, push to main, merge into main
    ("git push --force", bash("git push --force"), "feature"),
    ("option after the branch", bash("git push origin main --force"), "feature"),
    ("-f combined", bash("git push -uf origin feature"), "feature"),
    ("force with lease", bash("git push --force-with-lease origin feature"), "feature"),
    ("plus refspec", bash("git push origin +feature"), "feature"),
    ("push to main", bash("git push origin main"), "feature"),
    ("push HEAD:main", bash("git push origin HEAD:main"), "feature"),
    ("merge on main", bash("git merge feature"), "main"),
    ("switch then merge", bash("git switch main && git merge feature"), "feature"),
    # PRs
    ("gh pr merge", bash("gh pr merge 999999"), "feature"),
    ("gh pr create", bash("gh pr create --fill"), "feature"),
    ("merge API", bash("gh api -X PUT repos/o/r/pulls/1/merge"), "feature"),
    # Render
    ("deploy hook", bash("curl -X POST 'https://api.render.com/deploy/srv-x?key=y'"), "f"),
    ("hook from env", bash('curl -fsS "$RENDER_DEPLOY_HOOK_API"'), "feature"),
    ("tools.deploy", bash("uv run python -m tools.deploy --smoke-only"), "feature"),
    # the guardrails themselves
    ("Edit the hook", tool("Edit", file_path=str(SCRIPT)), "feature"),
    ("sed -i the settings", bash("sed -i 's/a/b/' .claude/settings.json"), "feature"),
    ("redirect into the settings", bash("echo {} > .claude/settings.json"), "feature"),
    ("checkout over the settings", bash("git checkout -- .claude/settings.json"), "feature"),
    ("restore the hook", bash("git restore agent-hooks/pre_tool_use.py"), "feature"),
    # globs that can reach a secret
    ("a dot glob", bash("cat .e*"), "feature"),
    ("an ssh key glob", bash("cat ~/.ssh/id_*"), "feature"),
    ("a pem glob", bash("ls certs/*.pem"), "feature"),
    ("a key glob", bash("cat *.key"), "feature"),
    # ── PR #38 audit, H2: deletions that never name data/ or lake/ ───────────────────────
    ("git clean -fdx", bash("git clean -fdx"), "feature"),
    ("git clean -fdX", bash("git clean -fdX"), "feature"),
    ("git clean, dry run too", bash("git clean -n"), "feature"),
    ("git -C clean", bash("git -C . clean -ffd"), "feature"),
    ("rm -rf *", bash("rm -rf *"), "feature"),
    ("rm -rf da*", bash("rm -rf da*"), "feature"),
    ("rm -rf ./lak?", bash("rm -rf ./lak?"), "feature"),
    ("rm -rf {data,lake}", bash("rm -rf {data,lake}"), "feature"),
    ("rm -r -- *.duckdb", bash("rm -r -- *.duckdb"), "feature"),
    ("find . -delete", bash("find . -name '*.duckdb' -delete"), "feature"),
    ("find . -exec rm", bash("find . -type f -exec rm {} +"), "feature"),
    # nested shells and eval go through the same rules
    ("bash -c make ingest", bash("bash -c 'make ingest'"), "feature"),
    ("sh -c force push", bash('sh -c "git push --force"'), "feature"),
    ("bash -lc rm -rf lake", bash("bash -lc 'rm -rf lake'"), "feature"),
    ("eval make ingest", bash("eval make ingest"), "feature"),
    ("bash -c inside bash -c", bash("bash -c \"bash -c 'cat .env'\""), "feature"),
    # ── M2: brace patterns and recursive searches that reach .env ────────────────────────
    ("braces naming .env", bash("cat {.env,README.md}"), "feature"),
    ("braces spelling .env", bash("head -n 99 {.,}env"), "feature"),
    ("braces inside the name", bash("cat .e{n,}v"), "feature"),
    ("grep -rn on the root", bash("grep -rn API_KEY ."), "feature"),
    ("grep -R with no path", bash("grep -R KEY"), "feature"),
    ("grep -rn on home", bash("grep -rn KEY ~"), "feature"),
    ("grep -rn on a parent", bash("grep -rn KEY .."), "feature"),
    ("rg -uu", bash("rg -uu KEY"), "feature"),
    ("rg --hidden --no-ignore", bash("rg --hidden --no-ignore KEY ."), "feature"),
    ("tar the root", bash("tar czf /tmp/x.tgz ."), "feature"),
    ("zip the root", bash("zip -r /tmp/x.zip ."), "feature"),
    # ── M3: GitHub API routes to a merge or to main ─────────────────────────────────────
    (
        "graphql mergePullRequest",
        bash(
            'gh api graphql -f query=\'mutation{mergePullRequest(input:{pullRequestId:"x"})'
            "{clientMutationId}}'"
        ),
        "feature",
    ),
    (
        "POST /pulls",
        bash("gh api -X POST repos/o/r/pulls -f title=t -f head=f -f base=main"),
        "feature",
    ),
    ("implicit POST /pulls", bash("gh api repos/o/r/pulls -f title=t -f head=f"), "feature"),
    (
        "PUT /contents on main",
        bash("gh api -X PUT repos/o/r/contents/x.md -f message=m -f content=x -f branch=main"),
        "feature",
    ),
    (
        "PUT /contents, default branch",
        bash("gh api --method=PUT repos/o/r/contents/x.md -f message=m -f content=x"),
        "feature",
    ),
    # ── issue #44: the merged PR closes an issue, never the agent ───────────────────────
    ("gh issue close", bash("gh issue close 44"), "feature"),
    ("gh issue close with a comment", bash("gh issue close 44 --comment done"), "feature"),
    ("gh -R issue close", bash("gh -R elliepsc/cyclebeat issue close 44"), "feature"),
    ("gh issue edit --state", bash("gh issue edit 44 --state closed"), "feature"),
    ("gh issue edit --state=", bash("gh issue edit 44 --state=closed"), "feature"),
    # ── issue #71: every string bash runs is checked ────────────────────────────────────
    ("a heredoc fed to bash", bash("bash <<'EOF'\nrm -rf lake\nEOF"), "feature"),
    ("a heredoc fed to bash -s", bash("bash -s <<'EOF'\nmake ingest\nEOF"), "feature"),
    ("a here-string fed to sh", bash("sh <<< 'make ingest'"), "feature"),
    ("a heredoc fed to xargs rm", bash("xargs rm -rf <<'EOF'\nlake\nEOF"), "feature"),
    ("a substitution in an unquoted heredoc", bash("cat <<EOF\n$(make ingest)\nEOF"), "f"),
    ("a backtick in a double-quoted message", bash('git commit -m "fix `make ingest`"'), "f"),
    ("a $( ) in double quotes", bash('echo "$(make ingest)"'), "feature"),
    ("pin: a $( ) in an argument", bash("ls $(rm -rf lake)"), "feature"),
    ("a variable into data/", bash("S=data && echo x > $S/probe"), "feature"),
    ("an exported variable into lake/", bash("export D=lake && touch $D/x"), "feature"),
    ("pin: a for loop that removes in data/", bash('for f in data/*.json; do rm "$f"; done'), "f"),
    ("pin: a subshell does not hide the cd", bash("cd data && (ls) && rm x.json"), "feature"),
    (
        "pin: a commit message is skipped, not its pathspec",
        bash("git commit -m msg data/x.json"),
        "feature",
    ),
    ("pin: commit -F .env", bash("git commit -F .env"), "feature"),
    ("an unbalanced quote", bash("echo 'oops"), "feature"),
    ("pin: an unclosed $(", bash("echo $(make ingest"), "feature"),
    # python -c and python heredocs (owner decision P1)
    ("python -c writes data/", bash("python3 -c \"open('data/x.json','w').write('1')\""), "f"),
    ("python -c rmtree lake", bash("python3 -c \"import shutil; shutil.rmtree('lake')\""), "f"),
    (
        "python -c write_text into data/",
        bash("python3 -c \"from pathlib import Path; Path('data/x.json').write_text('1')\""),
        "feature",
    ),
    (
        "python -c a name bound to lake/",
        bash("python3 -c \"p = 'lake/raw/x.parquet'\nimport os\nos.remove(p)\""),
        "feature",
    ),
    (
        "python -c duckdb read-write on data/",
        bash("python3 -c \"import duckdb; duckdb.connect('data/cyclebeat_runtime.duckdb')\""),
        "feature",
    ),
    ("python -c reads .env", bash("python3 -c \"print(open('.env').read())\""), "feature"),
    (
        "python -c runs make ingest",
        bash("python3 -c \"import subprocess; subprocess.run(['make', 'ingest'])\""),
        "feature",
    ),
    ("python -c os.system rm", bash("python3 -c \"import os; os.system('rm -rf lake')\""), "f"),
    (
        "python heredoc rmtree lake",
        bash("python3 - <<'EOF'\nimport shutil\nshutil.rmtree('lake')\nEOF"),
        "feature",
    ),
    ("python -c that does not parse", bash("python3 -c 'def ('"), "feature"),
    ("pin: python -c redirected into data/", bash("python3 -c 'print(1)' > data/x.txt"), "f"),
    ("pin: python -c given a data/ path", bash("python3 -c 'import sys' data/x.json"), "f"),
    # cyclebeat.cli
    (
        "cyclebeat.cli --lake lake ingest",
        bash("uv run python -m cyclebeat.cli --lake lake ingest"),
        "feature",
    ),
    ("pin: cyclebeat.cli ingest", bash("uv run python -m cyclebeat.cli ingest"), "feature"),
    (
        "cyclebeat.cli ingest --live, scratch lake",
        bash("uv run python -m cyclebeat.cli --lake /tmp/scratch-x/lake ingest --live"),
        "feature",
    ),
    (
        "cyclebeat.cli resolve, scratch lake",
        bash("uv run python -m cyclebeat.cli --lake /tmp/scratch-x/lake resolve"),
        "feature",
    ),
    ("pin: cyclebeat.cli load", bash("uv run python -m cyclebeat.cli load"), "feature"),
    # M1b: an issue's state is the merged PR's job
    ("gh issue reopen", bash("gh issue reopen 44"), "feature"),
    ("gh issue delete", bash("gh issue delete 44 --yes"), "feature"),
    ("gh issue transfer", bash("gh issue transfer 44 elliepsc/other"), "feature"),
    ("gh api PATCH state", bash("gh api -X PATCH repos/o/r/issues/44 -f state=closed"), "f"),
    ("gh api implicit POST state", bash("gh api repos/o/r/issues/44 -F state=open"), "f"),
    (
        "gh api --method= state_reason",
        bash("gh api --method=PATCH /repos/o/r/issues/44 -f state_reason=completed"),
        "feature",
    ),
    # ── issue #71, security-auditor pass 1: each finding, red on 0ef6e38 ──
    ("H1 a $() in a ${} default", bash("echo ${x:-$(rm -rf lake)}"), "feature"),
    ("H1 a secret read in a ${} default", bash("echo ${x:-$(cat .env)}"), "feature"),
    ("H1 a backtick in a ${:=}", bash(": ${x:=`git push --force`}"), "feature"),
    ("H2 grep -e. on .env", bash("grep -e. .env"), "feature"),
    ("H2 rg -e. on .env", bash("rg -e. .env"), "feature"),
    ("H2 git grep -e. on .env", bash("git grep --no-index -e. -- .env"), "feature"),
    ("H3 echo .env into xargs cat", bash("echo .env | xargs cat"), "feature"),
    ("H3 printf .env into xargs cp", bash("printf '%s\\n' .env | xargs -I{} cp {} /tmp/leak"), "f"),
    ("H3 echo a command into sh", bash("echo cat .env | sh"), "feature"),
    ("H4 bash -euo pipefail -c multiline", bash("bash -euo pipefail -c '\nrm -rf lake\n'"), "f"),
    (
        "H4 find -exec sh -c multiline",
        bash("find /tmp -maxdepth 0 -exec sh -c '\ncat .env\n' \\;"),
        "f",
    ),
    ("H4 ssh multiline", bash("ssh localhost '\ncat ~/projets/cyclebeat/.env\n'"), "feature"),
    ("H4 bash -o pipefail -c one line", bash("bash -o pipefail -c 'rm -rf lake'"), "feature"),
    ("H4 sudo -u then sh -c", bash("sudo -u postgres sh -c 'rm -rf lake'"), "feature"),
    (
        "M1 a loop past 64 values",
        bash(
            "for d in x0 x1 x2 x3 x4 x5 x6 x7 x8 x9 x10 x11 x12 x13 x14 x15 x16 x17 x18 x19 x20 x21"
            " x22 x23 x24 x25 x26 x27 x28 x29 x30 x31 x32 x33 x34 x35 x36 x37 x38 x39 x40 x41 x42 x"
            "43 x44 x45 x46 x47 x48 x49 x50 x51 x52 x53 x54 x55 x56 x57 x58 x59 x60 x61 x62 x63 lak"
            "e/raw; do rm -rf $d; done"
        ),
        "f",
    ),
    ("M1 the loop variable after the loop", bash("for d in lake/raw; do :; done; rm -rf $d"), "f"),
    (
        "M1 cd through the loop variable",
        bash("for d in lake/raw; do cd $d && rm -f a.parquet; done"),
        "f",
    ),
    (
        "M1 too many loop values",
        bash("for a in " + "x " * 70 + "; do for b in " + "y " * 70 + "; do echo $a$b; done; done"),
        "f",
    ),
    ("M4 gh api --input", bash("gh api -X PATCH repos/o/r/issues/71 --input body.json"), "f"),
    (
        "M4 gh api -fstate= attached",
        bash("gh api -X PATCH repos/o/r/issues/71 -fstate=closed"),
        "f",
    ),
    (
        "M4 gh api endpoint with a query",
        bash("gh api -X PATCH 'repos/o/r/issues/71?x=1' -f state=closed"),
        "f",
    ),
    (
        "M4 gh api -fhead= opens a PR",
        bash("gh api repos/o/r/pulls -fhead=x -fbase=main -ftitle=t"),
        "f",
    ),
    (
        "M4 GraphQL closeIssue",
        bash(
            "gh api graphql -f query='mutation{closeIssue(input:{issueId:\"I\"}){clientMutationId}}"
            "'"
        ),
        "f",
    ),
    (
        "M4 GraphQL reopenIssue",
        bash(
            "gh api graphql -f query='mutation{reopenIssue(input:{issueId:\"I\"}){clientMutationId}"
            "}'"
        ),
        "f",
    ),
    (
        "M4 GraphQL deleteIssue",
        bash(
            "gh api graphql -f query='mutation{deleteIssue(input:{issueId:\"I\"}){clientMutationId}"
            "}'"
        ),
        "f",
    ),
    (
        "M4 GraphQL transferIssue",
        bash(
            "gh api graphql -f query='mutation{transferIssue(input:{issueId:\"I\",repositoryId:\"R"
            "\"}){clientMutationId}}'"
        ),
        "f",
    ),
    ("M5 heredoc to bash -o pipefail", bash("bash -o pipefail <<'X'\nrm -rf lake\nX"), "feature"),
    ("M5 heredoc to bash -euo pipefail", bash("bash -euo pipefail <<'X'\nrm -rf lake\nX"), "f"),
    (
        "M5 heredoc to python -W ignore -",
        bash("python3 -W ignore - <<'X'\nimport shutil; shutil.rmtree('lake')\nX"),
        "f",
    ),
    (
        "M5 python -X dev -c",
        bash("python3 -X dev -c \"import shutil; shutil.rmtree('lake')\""),
        "f",
    ),
    ("L1 case ) in a subshell", bash("(cd lake; case x in *) rm -f a.parquet;; esac)"), "feature"),
    (
        "L1 case ) in a substitution",
        bash("echo $(cd lake; case x in *) rm -f a.parquet;; esac)"),
        "f",
    ),
    ("L2 a carriage return before #", bash("echo x\r#$(rm -rf lake)"), "feature"),
    ("L3 cli --la is --lake", bash("uv run python -m cyclebeat.cli --la lake ingest"), "feature"),
    (
        "L3 cli --liv is --live",
        bash("uv run python -m cyclebeat.cli --lake /tmp/x ingest --liv"),
        "f",
    ),
    (
        "L3 cli --lake on agent-hooks",
        bash("uv run python -m cyclebeat.cli --lake agent-hooks ingest"),
        "f",
    ),
    (
        "pin: L3 cli load --d is --db",
        bash("cd data && uv run python -m cyclebeat.cli load --d x.duckdb"),
        "f",
    ),
    (
        "pin: hash-object -w on agent-hooks",
        bash("git hash-object -w agent-hooks/pre_tool_use.py"),
        "f",
    ),
    # ── issue #71, round 3: the second pass (R1-R4), red on f618410, refused by 69b032e ──
    ("R1 echo .env through tee then xargs", bash("echo .env | tee /dev/null | xargs cat"), "f"),
    ("R1 echo .env through cat then xargs", bash("echo .env | cat | xargs cat"), "feature"),
    ("R1 printf through sed then xargs", bash("printf '%s' .env | sed s/x/x/ | xargs cat"), "f"),
    ("R1 echo .env into /usr/bin/xargs", bash("echo .env | /usr/bin/xargs cat"), "feature"),
    ("R1 echo .env into a read loop", bash('echo .env | while read f; do cat "$f"; done'), "f"),
    ("R1 echo .env into a file", bash("echo .env > /tmp/l; xargs cat < /tmp/l"), "feature"),
    ("R1 echo .env into wc", bash("echo .env | wc -c"), "feature"),
    ("R1 printf .env into grep", bash("printf '%s\\n' .env | grep -c env"), "feature"),
    ("R2 stdbuf", bash("stdbuf -oL bash -c '\nrm -rf lake\n'"), "feature"),
    ("R2 flock -c", bash("flock /tmp/l -c '\nrm -rf lake\n'"), "feature"),
    ("R2 script -qc", bash("script -qc '\nrm -rf lake\n' /dev/null"), "feature"),
    ("R2 su -c", bash("su -c '\nrm -rf lake\n'"), "feature"),
    ("R2 setsid", bash("setsid bash -c '\nrm -rf lake\n'"), "feature"),
    ("R2 tmux new", bash("tmux new -d '\nrm -rf lake\n'"), "feature"),
    ("R2 parallel", bash("parallel ::: '\nrm -rf lake\n'"), "feature"),
    ("R2 git rebase -x", bash("git rebase -x '\nrm -rf lake\n' HEAD~1"), "feature"),
    ("R2 git bisect run", bash("git bisect run sh -c '\nrm -rf lake\n'"), "feature"),
    ("R3 ${d%/}", bash("for d in lake/raw; do rm -rf ${d%/}; done"), "feature"),
    ("R3 ${d:-x}", bash("for d in lake/raw; do rm -rf ${d:-x}; done"), "feature"),
    (
        "R3 read from a process substitution",
        bash("while read d; do rm -rf $d; done < <(echo lake/raw)"),
        "f",
    ),
    ("R4 ;& in a subshell", bash("(cd lake; case x in a) :;& b) rm -f a.parquet;; esac)"), "f"),
    (
        "R4 ;& in a substitution",
        bash("echo $(cd lake; case x in a) :;& *) rm -f a.parquet;; esac)"),
        "f",
    ),
    ("R rg --files .env", bash("rg --files .env"), "feature"),
    # ── issue #71, round 3: the other findings and the caution rule, red on f618410 ──
    (
        "N5 updateIssue with a state",
        bash(
            "gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",state:CLOSED}){clientMut"
            "ationId}}'"
        ),
        "f",
    ),
    ("N5 a GraphQL query from a file", bash("gh api graphql -F query=@m.graphql"), "feature"),
    ("N5 a GraphQL body from --input", bash("gh api graphql --input q.json"), "feature"),
    ("N6 grep -f.env", bash("grep -f.env x"), "feature"),
    ("N6 grep -if.env", bash("grep -if.env x"), "feature"),
    ("N6 git grep -f.env", bash("git grep -f.env"), "feature"),
    ("read then rm", bash('IFS= read -r d <<< lake/raw; rm -rf "$d"'), "feature"),
    ("read then cd and rm", bash("while read d; do cd $d && rm -f a; done < <(echo lake)"), "f"),
    ("a heredoc to make", bash("make -f /dev/stdin <<'X'\nall:\n\trm -rf lake\nX"), "feature"),
    ("echo .env captured by a substitution", bash("cat $(echo .env)"), "feature"),
]


def test_the_allowed_list_is_not_shorter() -> None:
    assert len(ALLOWED) >= len(DENIED)


def decide(event: dict[str, Any], branch: str) -> str | None:
    """The hook's verdict with the branch injected and nothing staged."""
    return hook.decide(
        event, branch_of=lambda _cwd: branch, staged_of=lambda _cwd, _args, _added: ""
    )


@pytest.mark.parametrize(("case", "event", "branch"), ALLOWED, ids=[c[0] for c in ALLOWED])
def test_allowed(case: str, event: dict[str, Any], branch: str) -> None:
    assert decide(event, branch) is None


@pytest.mark.parametrize(("case", "event", "branch"), DENIED, ids=[c[0] for c in DENIED])
def test_denied(case: str, event: dict[str, Any], branch: str) -> None:
    assert decide(event, branch)


def test_the_six_false_positives_are_all_replayed() -> None:
    assert [fp["issue_71_item"] for fp in FALSE_POSITIVES] == [1, 2, 3, 4, 5, 6]


# ── issue #71, candidate 7: a commit that adds a secret (owner decision A) ──────────────
# Built by concatenation so that no literal key sits in this file (gitleaks scans it in CI).
FAKE = "0123456789abcdefABCDEF0123456789abcd"
STAGED = [
    ("private key", "RSA key header", "-----BEGIN " + "RSA PRIVATE KEY-----"),
    ("private key", "OpenSSH key header", "-----BEGIN " + "OPENSSH PRIVATE KEY-----"),
    ("private key", "PKCS#8 key header", "-----BEGIN " + "PRIVATE KEY-----"),
    ("private key", "PGP key header", "-----BEGIN " + "PGP PRIVATE KEY BLOCK-----"),
    ("GitHub token", "ghp_", "gh" + "p_" + FAKE),
    ("GitHub token", "gho_", "gh" + "o_" + FAKE),
    ("GitHub token", "ghu_", "gh" + "u_" + FAKE),
    ("GitHub token", "ghs_", "gh" + "s_" + FAKE),
    ("GitHub token", "ghr_", "gh" + "r_" + FAKE),
    ("GitHub fine-grained token", "github_pat_", "github" + "_pat_" + FAKE),
    ("AWS access key ID", "AKIA", "AK" + "IA" + "Q7" * 8),
    ("AWS access key ID", "ASIA", "AS" + "IA" + "Z3" * 8),
]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        check=True, capture_output=True,
    )


def _repo(tmp_path: Path, content: str, name: str = "config.py") -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / name).write_text(f"value = '{content}'\n")
    _git(tmp_path, "add", "-f", name)
    return tmp_path


def _commit(repo: Path, command: str = "git commit -m add") -> str | None:
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}
    return hook.decide(event, branch_of=lambda _cwd: "feature")


@pytest.mark.parametrize(("rule", "kind", "secret"), STAGED, ids=[s[1] for s in STAGED])
def test_a_commit_that_adds_a_secret_is_refused(
    tmp_path: Path, rule: str, kind: str, secret: str
) -> None:
    reason = _commit(_repo(tmp_path, secret))
    assert reason and rule in reason and "config.py" in reason
    assert secret not in reason  # the value is never echoed


def test_a_clean_commit_is_allowed(tmp_path: Path) -> None:
    assert _commit(_repo(tmp_path, "nothing to see")) is None


def test_a_secret_that_only_resembles_a_prefix_is_allowed(tmp_path: Path) -> None:
    assert _commit(_repo(tmp_path, "ghp_short and AKIA-not-a-key")) is None


def test_commit_a_reads_the_tracked_changes(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "nothing")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "config.py").write_text("value = '" + "gh" + "p_" + FAKE + "'\n")
    assert _commit(repo, "git commit -m x") is None  # not staged, not committed
    assert _commit(repo, "git commit -am x")
    assert _commit(repo, "git commit -m x config.py")


def test_the_change_to_commit_never_includes_env(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "nothing")
    (repo / ".env").write_text("GROQ_API_KEY=" + "gh" + "p_" + FAKE + "\n")
    _git(repo, "add", "-f", ".env")
    assert FAKE not in hook._commit_diff(repo, [])


@pytest.mark.parametrize(
    "path",
    [".claude/settings.json", ".claude/settings.local.json"],
)
def test_the_settings_files_cannot_be_written(path: str) -> None:
    assert hook.decide(tool("Write", file_path=str(ROOT / path)), branch_of=lambda _c: "f")


def _run(stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], input=stdin, capture_output=True, text=True,
        timeout=30, check=False,
    )


def test_the_script_blocks_with_exit_2_and_a_reason() -> None:
    out = _run(json.dumps(bash("gh pr merge 999999")))
    assert out.returncode == 2
    assert "gh pr merge is the owner's action" in out.stderr


def test_the_script_lets_a_normal_call_through() -> None:
    out = _run(json.dumps(bash("git status")))
    assert (out.returncode, out.stderr) == (0, "")


def test_the_script_fails_closed_on_garbage() -> None:
    out = _run("this is not json")
    assert out.returncode == 2
    assert "failing closed" in out.stderr


# ── issue #71, security-auditor pass 1 on the secret check (M2, M3, L6) ─────────────────
TOKEN = "gh" + "p_" + FAKE


def test_a_git_error_refuses_the_commit(tmp_path: Path) -> None:
    reason = _commit(tmp_path)  # not a repository: git diff exits 129
    assert reason and "could not be read" in reason


def test_an_unresolved_cd_still_reads_the_repo(tmp_path: Path) -> None:
    repo = _repo(tmp_path, TOKEN)
    assert _commit(repo, 'cd "$(git rev-parse --show-toplevel)" && git commit -m x')


def test_an_unborn_branch_with_a_pathspec_is_read(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "nothing")  # staged clean, no commit yet: HEAD does not exist
    (repo / "config.py").write_text(f"v = '{TOKEN}'\n")
    assert _commit(repo, "git commit -m x config.py")


def test_git_add_then_commit_in_one_command_is_read(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "nothing")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "new.py").write_text(f"v = '{TOKEN}'\n")
    assert _commit(repo, "git add new.py && git commit -m x")
    assert _commit(repo, "git add -A && git commit -m x")
    assert _commit(repo, "git add . && git commit -m x")


def test_the_refusal_never_prints_a_line_of_content(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "config.py").write_text("++ " + TOKEN + "\n" + TOKEN + "\n")
    _git(tmp_path, "add", "config.py")
    reason = _commit(tmp_path)
    assert reason and "GitHub token" in reason and "config.py" in reason
    assert FAKE not in reason


@pytest.mark.parametrize("name", ["certs/server.pem", "deploy.key", ".ssh/id_ed25519", "id_custom"])
def test_a_secrets_file_staged_is_refused_by_name(tmp_path: Path, name: str) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text("not a key header\n")
    _git(tmp_path, "add", "-f", name)
    reason = _commit(tmp_path)
    assert reason and "secrets file is staged" in reason


def test_a_public_key_staged_is_allowed(tmp_path: Path) -> None:
    # A pin: green on 0ef6e38, red on the mutation that refuses every id_* (ai-workflow #71).
    _git(tmp_path, "init", "-q")
    (tmp_path / "id_ed25519.pub").write_text("ssh-ed25519 AAAA test\n")
    _git(tmp_path, "add", "id_ed25519.pub")
    assert _commit(tmp_path) is None


def test_a_staged_env_is_refused_without_being_read(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "nothing")
    (repo / ".env").write_text("GROQ_API_KEY=" + TOKEN + "\n")
    _git(repo, "add", "-f", ".env")
    reason = _commit(repo)
    assert reason and "secrets file is staged (.env)" in reason
    assert FAKE not in hook._commit_diff(repo, [], [])


# ── issue #71, round 3: the commit check runs no code of the repository (N3) ─────────────
def _marker_program(tmp_path: Path) -> tuple[Path, Path]:
    marker = tmp_path / "ran"
    program = tmp_path / "program.sh"
    program.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    program.chmod(0o755)
    return program, marker


def test_the_commit_check_runs_no_fsmonitor_of_the_repo(tmp_path: Path) -> None:
    program, marker = _marker_program(tmp_path)
    (tmp_path / "repo").mkdir()
    repo = _repo(tmp_path / "repo", "nothing")
    _git(repo, "config", "core.fsmonitor", str(program))
    marker.unlink(missing_ok=True)
    _commit(repo)
    assert not marker.exists()


def test_a_filter_driver_of_the_repo_refuses_the_commit_unrun(tmp_path: Path) -> None:
    program, marker = _marker_program(tmp_path)
    (tmp_path / "repo").mkdir()
    repo = _repo(tmp_path / "repo", "nothing")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "config", "filter.x.clean", str(program))
    (repo / ".gitattributes").write_text("* filter=x\n")
    (repo / "config.py").write_text("value = 'changed'\n")
    marker.unlink(missing_ok=True)
    reason = _commit(repo, "git commit -am x")
    assert reason and "could not be read" in reason
    assert not marker.exists()


# ── issue #71, round 3: no secret in a refusal, no forged header (N2) ────────────────────
def _staged_bytes(tmp_path: Path, name: str, content: bytes) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / name).write_bytes(content)
    _git(tmp_path, "add", "-f", name)
    return tmp_path


def test_a_forged_header_never_puts_the_token_in_the_refusal(tmp_path: Path) -> None:
    forged = f"x\x0cdiff --git a/q b/z{TOKEN}\n\x0c@@\n{TOKEN}\n".encode()
    reason = _commit(_staged_bytes(tmp_path, "c.txt", forged))
    assert reason and FAKE not in reason


@pytest.mark.parametrize(
    "content",
    [f"a\r{TOKEN}\r", f"x\x0cdiff --git a/q b/q\n{TOKEN}\n"],
    ids=["CR-only line endings", "a form feed before a header"],
)
def test_content_split_on_other_line_breaks_is_read(tmp_path: Path, content: str) -> None:
    assert _commit(_staged_bytes(tmp_path, "c.txt", content.encode()))


def test_a_file_name_holding_a_token_is_not_printed(tmp_path: Path) -> None:
    reason = _commit(_staged_bytes(tmp_path, "id_" + TOKEN, b"x\n"))
    assert reason and FAKE not in reason
