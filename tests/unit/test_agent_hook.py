"""The PreToolUse guardrail (`agent-hooks/pre_tool_use.py`, criterion 12).

Two lists of real tool calls: what must pass and what must be refused. The owner asked for at
least as many "allowed" cases as "refused" ones, because a hook that blocks normal work gets
switched off; `test_the_allowed_list_is_not_shorter` holds that. The branch is injected, so no
case depends on what this checkout has checked out. The last tests run the script as Claude
Code does: JSON on stdin, exit code 2 and a reason on stderr.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "agent-hooks" / "pre_tool_use.py"


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
    # A2 (#71): what stays allowed around the issue-state refusals
    (
        "pin: gh api PATCH on an issue title",
        bash("gh api -X PATCH repos/o/r/issues/71 -f title=x"),
        "f",
    ),
    ("pin: gh api comment on an issue", bash("gh api repos/o/r/issues/71/comments -f body=x"), "f"),
    (
        "pin: a GraphQL query on an issue",
        bash("gh api graphql -f query='query{repository(owner:\"o\",name:\"r\")"
             "{issue(number:1){title}}}'"),
        "feature",
    ),
    (
        "pin: updateIssue on the title",
        bash("gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",title:\"t\"})"
             "{clientMutationId}}'"),
        "feature",
    ),
    ("pin: gh issue edit a label", bash("gh issue edit 71 --add-label bug"), "feature"),
    ("pin: grep -f a pattern file", bash("grep -f patterns.txt README.md"), "feature"),
    (
        "pin: cli ingest --limit into /tmp",
        bash("uv run python -m cyclebeat.cli --lake /tmp/x ingest --limit 5"),
        "f",
    ),
    ("pin: cli confidence-report", bash("uv run python -m cyclebeat.cli confidence-report"), "f"),
    ("pin: bash heredoc that reads", bash("bash <<'EOF'\nls lake\nmake lint\nEOF"), "f"),
    ("pin: xargs heredoc that reads", bash("xargs wc -l <<'EOF'\nREADME.md\nEOF"), "f"),
    ("pin: heredoc to cat stays data", bash("cat > /tmp/n.md <<'EOF'\nrm -rf lake\nEOF"), "f"),
    ("pin: $() in single quotes is text", bash("echo '$(rm -rf lake)'"), "feature"),
    ("pin: a quoted rev-parse", bash('echo "$(git rev-parse HEAD)"'), "feature"),
    (
        "pin: python reads lake",
        bash("python3 -c \"print(open('lake/raw/x.parquet', 'rb').read(4))\""),
        "f",
    ),
    (
        "pin: duckdb read_only on data",
        bash("python3 -c \"import duckdb; duckdb.connect('data/x.duckdb', read_only=True)\""),
        "f",
    ),
    ("pin: python writes /tmp", bash("python3 -c \"open('/tmp/x.txt', 'w').write('lake')\""), "f"),
    (
        "pin: python heredoc that prints",
        bash("uv run python - <<'EOF'\nprint('lake .env')\nEOF"),
        "f",
    ),
    (
        "pin: subprocess git status",
        bash("python3 -c \"import subprocess; subprocess.run(['git', 'status'])\""),
        "f",
    ),
    ("pin: do grep in a loop", bash("for f in a b; do grep -c x README.md; done"), "feature"),
    ("pin: if test then echo", bash("if test -f README.md; then echo yes; fi"), "feature"),
    ("B3 ingest --help", bash("uv run python -m cyclebeat.cli ingest --help"), "feature"),
    ("B3 load -h", bash("uv run python -m cyclebeat.cli load -h"), "feature"),
    ("pin: a loop of wc over docs", bash("for f in docs/a.md docs/b.md; do wc -l $f; done"), "f"),
    ("pin: a scratch dir by variable", bash("S=/tmp/out; mkdir -p $S && cp README.md $S/"), "f"),
    ("pin: python -c that prints", bash('python3 -c "print(1)"'), "feature"),
    ("pin: a quoted date", bash('echo "$(date -u +%F)"'), "feature"),
    ("pin: bash heredoc running tests", bash("bash <<'EOF'\nmake test-unit\nEOF"), "f"),
    ("pin: a one-line commit message", bash("git commit -m 'docs: the lake/raw layout'"), "f"),
    ("B6 hash-object of the hook", bash("git hash-object agent-hooks/pre_tool_use.py"), "f"),
    ("B6 hash-object of .claude/settings.json", bash("git hash-object .claude/settings.json"), "f"),
    ("pin: read issue comments", bash("gh api repos/o/r/issues/71/comments --jq '.[].body'"), "f"),
    ("pin: dbt on a scratch db", bash("RUNTIME_DB_PATH=/tmp/x.duckdb make dbt"), "feature"),
    ("pin: diff against HEAD", bash("diff <(git show HEAD:README.md) README.md"), "feature"),
    ("pin: unit tests", bash("uv run pytest tests/unit -q"), "feature"),
    ("pin: gh issue view", bash("gh issue view 71 --json title,body,comments"), "feature"),
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
    # B6 (#71): hash-object writes only with -w
    ("B6 hash-object -w", bash("git hash-object -w agent-hooks/pre_tool_use.py"), "feature"),
    ("B6 hash-object -tw cluster", bash("git hash-object -tw blob agent-hooks/README.md"), "f"),
    ("B5 loop into xargs rm", bash("for d in lake/raw; do echo $d; done | xargs rm -rf"), "f"),
    ("B5 awk in the body", bash("for f in lake/x; do awk '{print}' $f; done"), "feature"),
    ("B5 rm in the body", bash("for d in lake/raw; do rm -rf $d; done"), "feature"),
    ("B5 git diff --output", bash("for f in lake/x; do git diff --output=$f; done"), "feature"),
    ("B5 a redirect to a file", bash("for f in lake/x; do cat $f; done > out.txt"), "feature"),
    ("B5 a prefix assignment", bash("for f in lake/x; do X=1 git diff $f; done"), "feature"),
    ("B5 file -C", bash("for f in lake/x; do file -C -m $f; done"), "feature"),
    ("B5 secrets item", bash("for f in .env; do cat $f; done"), "feature"),
    (
        "B4 commit start inside a quote",
        bash("echo 'git commit -m \"'; rm -rf lake; echo '\"'"),
        "f",
    ),
    ("B4 message running a command", bash('git commit -m "$(rm -rf lake)"'), "feature"),
    ("B4 a command after the message", bash('git commit -m "x"; rm -rf lake'), "feature"),
    ("B4 not a git command head", bash("cat git commit -m '.env'"), "feature"),
    ("B4 -m as the value of --author", bash("git commit --author -m '.env'"), "feature"),
    ("B4 -m after --", bash("git commit -- -m '.env'"), "feature"),
    (
        "B4 an ANSI-C quote before",
        bash("echo $'\\''; git commit -m \"'; rm -rf lake; echo \"'"),
        "f",
    ),
    ("B4 a comment before", bash('echo x # git commit -m "\nrm -rf lake\necho "'), "feature"),
    ("B4 a word glued after the span", bash("git commit -m '\nrm -rf lake\n'x"), "feature"),
    # B3 (#71): only the exact help word, before any --
    ("B3 ingest -- --help", bash("uv run python -m cyclebeat.cli ingest -- --help"), "f"),
    ("B3 ingest --help-me", bash("uv run python -m cyclebeat.cli ingest --help-me"), "f"),
    ("B3 ingest --hel", bash("uv run python -m cyclebeat.cli ingest --hel"), "feature"),
    ("B3 help then rm", bash("uv run python -m cyclebeat.cli ingest --help; rm -rf lake"), "f"),
    # Pins: what the relaxations tried and removed after the fourth audit (B1, B2, B4, B5) had
    # to keep refused. Refused by 69b032e too; they stay so.
    ("B2 closing quote then cat .env", bash("echo '\nx\n'; cat .env"), "feature"),
    ("B1 counter: assigned after &&", bash("cd lake; S=.; false && S=/tmp; rm -rf $S/x"), "f"),
    ("B1 counter: assigned in a pipe", bash("cd lake; S=/tmp | true; rm -rf $S/x"), "f"),
    ("B1 counter: assigned in an if", bash("cd lake; if false; then S=/tmp; fi; rm -rf $S/x"), "f"),
    ("B1 counter: exported again", bash("cd lake; S=/tmp; export S=.; rm -rf $S/x"), "f"),
    ("B1 counter: read again", bash("cd lake; S=/tmp; read S <<< .; rm -rf $S/x"), "f"),
    ("B1 counter: in a brace group", bash("cd lake; { S=/tmp; }; rm -rf $S/x"), "f"),
    ("B1 counter: after source", bash("cd lake; S=/tmp; source x; rm -rf $S/x"), "f"),
    ("B1 counter: quoted tilde", bash("cd lake; S='~'; rm -rf $S/x"), "f"),
    ("B1 counter: a value with a space", bash("cd lake; S='/tmp .'; rm -rf $S"), "f"),
    # A8 (#71): a shell keyword before the command, red on 69b032e
    ("A8 do rm", bash("for x in 1; do rm -rf lake; done"), "feature"),
    ("A8 then rm", bash("if true; then rm -rf lake; fi"), "feature"),
    ("A8 else rm", bash("if false; then :; else rm -rf data; fi"), "feature"),
    ("A8 while make ingest", bash("while true; do make ingest; break; done"), "feature"),
    ("A8 brace group", bash("{ rm -rf lake; }"), "feature"),
    ("A8 negation", bash("! rm -rf lake"), "feature"),
    # A7 (#71): python code read with ast, red on 69b032e
    ("A7 rmtree lake", bash("python3 -c \"import shutil; shutil.rmtree('lake')\""), "feature"),
    ("A7 read .env", bash("python3 -c \"print(open('.env').read())\""), "feature"),
    ("A7 -X dev -c", bash("python3 -X dev -c \"import shutil; shutil.rmtree('lake')\""), "f"),
    ("A7 open for writing in data", bash("python3 -c \"open('data/x.csv', 'w')\""), "f"),
    (
        "A7 duckdb.connect on data",
        bash("python3 -c \"import duckdb; duckdb.connect('data/x.duckdb')\""),
        "f",
    ),
    (
        "A7 Path.write_text in lake",
        bash("python3 -c \"from pathlib import Path; Path('lake/x').write_text('')\""),
        "f",
    ),
    (
        "A7 subprocess make ingest",
        bash("python3 -c \"import subprocess; subprocess.run(['make', 'ingest'])\""),
        "f",
    ),
    ("A7 os.system rm", bash("python3 -c \"import os; os.system('rm -rf lake')\""), "f"),
    (
        "A7 multi-line code",
        bash("uv run python -c \"\nimport shutil\nshutil.rmtree('lake')\n\""),
        "f",
    ),
    (
        "A7 python heredoc",
        bash("python3 - <<'EOF'\nimport shutil\nshutil.rmtree('lake')\nEOF"),
        "f",
    ),
    (
        "A7 python -W heredoc",
        bash("python3 -W ignore - <<'X'\nimport shutil; shutil.rmtree('lake')\nX"),
        "f",
    ),
    (
        "A7 a variable that names .env",
        bash("python3 -c \"p = '.env'; print(open(p).read())\""),
        "f",
    ),
    # A6 (#71): a substitution inside double quotes, red on 69b032e
    ("A6 $() in double quotes", bash('echo "$(rm -rf lake)"'), "feature"),
    ("A6 backticks in double quotes", bash('echo "`cat .env`"'), "feature"),
    ("A6 commit message running a command", bash('git commit -m "$(cat .env)"'), "feature"),
    # A5 (#71): a heredoc fed to a shell or xargs, red on 69b032e
    ("A5 bash heredoc", bash("bash <<'EOF'\nrm -rf lake\nEOF"), "feature"),
    ("A5 bash -o pipefail heredoc", bash("bash -o pipefail <<'X'\nrm -rf lake\nX"), "feature"),
    ("A5 sh heredoc reading .env", bash("sh <<'EOF'\ncat .env\nEOF"), "feature"),
    ("A5 cat heredoc into sh", bash("cat <<'EOF' | sh\nrm -rf lake\nEOF"), "feature"),
    ("A5 heredoc on a compound", bash("{ sh; } <<'EOF'\nrm -rf lake\nEOF"), "feature"),
    ("A5 heredoc to eval", bash("eval \"$(cat)\" <<'EOF'\nrm -rf lake\nEOF"), "feature"),
    ("A5 xargs heredoc", bash("xargs rm -rf <<'EOF'\nlake\nEOF"), "feature"),
    ("A5 cat heredoc into xargs", bash("cat <<'EOF' | xargs cat\n.env\nEOF"), "feature"),
    # A4 (#71): the real cyclebeat.cli subcommand, red on 69b032e
    ("A4 --lake lake ingest", bash("uv run python -m cyclebeat.cli --lake lake ingest"), "f"),
    ("A4 --la lake ingest", bash("uv run python -m cyclebeat.cli --la lake ingest"), "f"),
    (
        "A4 --lake agent-hooks ingest",
        bash("uv run python -m cyclebeat.cli --lake agent-hooks ingest"),
        "f",
    ),
    ("A4 ingest --live", bash("uv run python -m cyclebeat.cli --lake /tmp/x ingest --live"), "f"),
    ("A4 ingest --liv", bash("uv run python -m cyclebeat.cli --lake /tmp/x ingest --liv"), "f"),
    ("A4 resolve", bash("uv run python -m cyclebeat.cli --lake /tmp/x resolve"), "f"),
    ("A4 extract-app", bash("uv run python -m cyclebeat.cli --lake /tmp/x extract-app"), "f"),
    # A3 (#71): a secrets name glued to a short flag, red on 69b032e
    ("A3 grep -f.env", bash("grep -f.env x"), "feature"),
    ("A3 grep -if.env", bash("grep -if.env x"), "feature"),
    ("A3 git grep -f.env", bash("git grep -f.env"), "feature"),
    ("A3 git commit -F.env", bash("git commit -F.env"), "feature"),
    ("A3 git commit -aF.env", bash("git commit -aF.env"), "feature"),
    ("A3 git commit -t.env", bash("git commit -t.env"), "feature"),
    ("A3 git tag -F.env", bash("git tag -a v1 -F.env"), "feature"),
    ("A3 git notes -F.env", bash("git notes add -F.env"), "feature"),
    # A2 (#71): an issue's state through gh, red on 69b032e
    ("A2 gh issue reopen", bash("gh issue reopen 3"), "feature"),
    ("A2 gh issue delete", bash("gh issue delete 3 --yes"), "feature"),
    ("A2 gh issue transfer", bash("gh issue transfer 3 o/other"), "feature"),
    ("A2 PATCH state", bash("gh api -X PATCH repos/o/r/issues/3 -f state=closed"), "feature"),
    ("A2 PATCH state_reason", bash("gh api -X PATCH repos/o/r/issues/3 -F state_reason=x"), "f"),
    ("A2 attached -fstate=", bash("gh api -X PATCH repos/o/r/issues/71 -fstate=closed"), "f"),
    ("A2 --input body", bash("gh api -X PATCH repos/o/r/issues/71 --input body.json"), "f"),
    ("A2 query string", bash("gh api -X PATCH 'repos/o/r/issues/71?x=1' -f state=closed"), "f"),
    (
        "A2 GraphQL closeIssue",
        bash("gh api graphql -f query='mutation{closeIssue(input:{issueId:\"I\"})"
             "{clientMutationId}}'"),
        "feature",
    ),
    (
        "A2 GraphQL updateIssue with a state",
        bash("gh api graphql -f query='mutation{updateIssue(input:{id:\"I\",state:CLOSED})"
             "{clientMutationId}}'"),
        "feature",
    ),
    ("A2 GraphQL query from a file", bash("gh api graphql -F query=@m.graphql"), "feature"),
    ("A2 GraphQL body from --input", bash("gh api graphql --input q.json"), "feature"),
    (
        "A2 attached -f opens a PR",
        bash("gh api repos/o/r/pulls -fhead=x -fbase=main -ftitle=t"),
        "f",
    ),
]
# The security-auditor's normal-work probes that 69b032e allows (#71): they stay allowed.
PROBES = [
    'git hash-object --stdin < README.md',
    'case "$x" in a|b) echo yes;; *) echo no;; esac',
    'for f in tests/*.py; do wc -l "$f"; done',
    'for f in a b c; do echo $f; done',
    'for d in lake data; do du -sh $d; done',
    "bash -o pipefail -c 'make test-unit | tail -5'",
    "bash -euo pipefail -c 'uv run pytest -q'",
    'set -o pipefail; make lint 2>&1 | tail -3',
    "bash -lc 'ls'",
    "bash -O extglob -c 'ls'",
    'bash scripts/x.sh',
    'bash -x scripts/x.sh',
    "find /tmp -type f -name '*.tmp' -exec rm {} \\;",
    'ssh host ls',
    'ssh -p 22 -i ~/.ssh/k host uptime',
    'ssh host',
    'watch -n 1 ls',
    "git add README.md && git commit -m 'docs: x'",
    'git add -A && git commit -m x',
    "git commit -am 'x'",
    'echo hello | xargs echo',
    "printf '%s\\n' a b | xargs -n1 echo",
    'echo ls | sh',
    'echo .env.example | xargs cat',
    'grep -rn foo src/',
    'grep -e foo -e bar README.md',
    'gh api -X PATCH repos/o/r/issues/71 -f title=x',
    'gh api repos/o/r/issues/71/comments -f body=x',
    (
        'gh api graphql -f query=\'query{repository(owner:"o",name:"r"){issue(nu'
        "mber:1){title}}}'"
    ),
    'uv run python -m cyclebeat.cli --help',
    'uv run python -m cyclebeat.cli --lake /tmp/x ingest',
    "python3 -W ignore -c 'print(1)'",
    "python3 -X importtime -c 'import json'",
    "printf 'a\\r\\nb' > /tmp/x",
    (
        'git commit -m "$(cat <<\'EOF\'\nfix(hook): refuse rm -rf lake and cat .en'
        'v (#71)\n\nCo-Authored-By: x\nEOF\n)"'
    ),
    "git commit -F - <<'EOF'\ndocs: rm -rf lake is refused; cat .env too\nEOF",
    (
        'gh issue comment 71 --body "$(cat <<\'EOF\'\nPosted by the coding agent ('
        'Claude Code).\nThe hook refuses cat .env and rm -rf lake.\nEOF\n)"'
    ),
    (
        "gh issue comment 71 --body-file - <<'EOF'\nPosted by the coding agent. "
        'cat .env is refused.\nEOF'
    ),
    (
        "gh issue comment 71 --body 'Posted by the coding agent.\nPlan:\n- run ma"
        "ke lint\n- run make test-unit'"
    ),
    "cat > /tmp/notes.md <<'EOF'\nNever run rm -rf lake\nEOF",
    "uv run python - <<'EOF'\nprint(1)\nEOF",
    'find . -name \'*.py\' | while read -r f; do wc -l "$f"; done',
    (
        'git ls-files \'*.py\' | while read -r f; do uv run ruff format "$f"; don'
        'e'
    ),
    (
        'git log --format=%h -3 | while read -r c; do git show --stat "$c"; don'
        'e'
    ),
    "echo 'line' >> /tmp/out.txt",
    'echo lake/raw > /tmp/list.txt',
    'printf \'%s\\n\' "$x" | tee /tmp/y',
    'echo $(git rev-parse HEAD)',
    "sed -i '1i\\\n# header' /tmp/f.md",
    "awk '\n/^#/ { n++ }\nEND { print n }\n' docs/ROADMAP.md",
    "uv run python -c 'import sys\nprint(sys.version)'",
    'make lint && make test-unit',
    'git diff f618410..HEAD -- agent-hooks/pre_tool_use.py',
]
ALLOWED += [(f"probe: {c[:60]}", bash(c), "feature") for c in PROBES]


def test_the_allowed_list_is_not_shorter() -> None:
    assert len(ALLOWED) >= len(DENIED)


def decide(event: dict[str, Any], branch: str) -> str | None:
    """The hook's verdict with the branch injected and nothing staged (A1 reads the index)."""
    kwargs: dict[str, Any] = {"branch_of": lambda _cwd: branch}
    if "staged_of" in inspect.signature(hook.decide).parameters:
        kwargs["staged_of"] = lambda _cwd, _args, _added: ""
    return hook.decide(event, **kwargs)


@pytest.mark.parametrize(("case", "event", "branch"), ALLOWED, ids=[c[0] for c in ALLOWED])
def test_allowed(case: str, event: dict[str, Any], branch: str) -> None:
    assert decide(event, branch) is None


@pytest.mark.parametrize(("case", "event", "branch"), DENIED, ids=[c[0] for c in DENIED])
def test_denied(case: str, event: dict[str, Any], branch: str) -> None:
    assert decide(event, branch)


# ── A1 (#71): a commit that adds a secret ─────────────────────────────────────────────
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


# ── A1: the auditor's findings on the secret check (M2, M3, L6, N2, N3) ──────────────
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


# The six false positives of issue #71, as they were hit (tests/fixtures). FP3 is let through
# by B3; the relaxations for the five others were removed after the fourth security-auditor pass
# and these stay refused (docs/permissions.md, Limits).
FIXED_BY = {"fp3-cli-help": "B3"}
FALSE_POSITIVES = json.loads(
    (ROOT / "tests" / "fixtures" / "hook_false_positives.json").read_text()
)["cases"]


@pytest.mark.parametrize(
    "command",
    [c["command"] for c in FALSE_POSITIVES if c["id"] in FIXED_BY],
    ids=[f"{FIXED_BY[c['id']]} {c['id']}" for c in FALSE_POSITIVES if c["id"] in FIXED_BY],
)
def test_a_false_positive_of_issue_71_is_allowed(command: str) -> None:
    assert decide(bash(command), "feature") is None


@pytest.mark.parametrize(
    "command",
    [c["command"] for c in FALSE_POSITIVES if c["id"] not in FIXED_BY],
    ids=[c["id"] for c in FALSE_POSITIVES if c["id"] not in FIXED_BY],
)
def test_a_false_positive_left_as_a_limit_is_refused(command: str) -> None:
    assert decide(bash(command), "feature")
