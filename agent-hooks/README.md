# agent-hooks/ — the PreToolUse guardrail (criterion 12)

[`pre_tool_use.py`](pre_tool_use.py) is the **hook or guardrail** element of the
[agent extension pack](../docs/agent-extension-pack.md). Claude Code runs it before every
`Bash`, `Read`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `Grep`, `Glob` and `WebFetch` call,
because [`.claude/settings.json`](../.claude/settings.json) declares it (exec form,
`${CLAUDE_PROJECT_DIR}/agent-hooks/pre_tool_use.py`, `"onFailure": "block"`).

It refuses, with exit code 2 and a one-line reason:

| Rule | Examples refused | Examples allowed |
|---|---|---|
| no write to `data/` or `lake/` | `Write data/x`, `rm -rf lake`, `echo x > data/y`, `cd data && rm x`, `make ingest`, `make dbt` | `ls data/`, `git log -- data/`, `stat`/`sha256sum`, `cp data/x /tmp/`, `RUNTIME_DB_PATH=/tmp/x.duckdb make dbt`, `cat frontend/src/data/x.ts` |
| no secrets file | `Read .env`, `cat .env*`, `grep KEY .env.local`, private keys | `cat .env.example` |
| no force push, no push to `main` | `git push --force`, `git push origin main --force`, `-uf`, `+branch`, `HEAD:main` | `git push -u origin feature` |
| no merge into `main` | `git merge x` on main, `git switch main && git merge x` | `git merge origin/main` on a branch |
| no PR creation or merge | `gh pr create`, `gh pr merge 999999`, the merge API | `gh pr view`, `gh run list` |
| no Render | deploy hooks, `api.render.com`, `$RENDER_*`, `python -m tools.deploy` | `pytest tests/unit/test_deploy.py` |
| the guardrails are the owner's | edits to `agent-hooks/` and `.claude/settings*.json` | reading them, `git add` |

It reads command text. It stops mistakes, not an adversary: a `python -c` that builds a path at
runtime gets through. What it can and cannot do, and the two other layers, are in
[docs/permissions.md](../docs/permissions.md).

Tests: [`tests/unit/test_agent_hook.py`](../tests/unit/test_agent_hook.py), with at least as many
allowed calls as refused ones (owner rule: a hook that blocks normal work gets switched off).

Standard library only, Python 3.10 or later, so it runs before any virtualenv exists.
