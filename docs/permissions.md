# Permissions — what a coding agent may and may not do on CycleBeat

The permission notes of the [agent extension pack](agent-extension-pack.md) (criterion 12).

## Why auto mode, and why it is acceptable here

The owner runs Claude Code in **auto mode**: a classifier model reviews actions instead of a
human approving each prompt. That is a deliberate choice for speed on a solo project. It is only
acceptable because the rules that matter most are **enforced by code checked into this repo**,
not only by instructions the agent is asked to follow. The motivating case is public: Alexey
Grigorev lost a production database, its VPC and its snapshots when an agent he had let run
Terraform executed `terraform destroy` against a swapped state file, and his own lesson was that
he "over-relied on the AI agent to run Terraform commands"
([his post-mortem](https://aishippingblog.com/p/how-i-dropped-our-production-database)).

| Layer | Where | Enforced by |
|---|---|---|
| 1. Deny rules | [`.claude/settings.json`](../.claude/settings.json) `permissions.deny` | Claude Code itself |
| 2. PreToolUse hook | [`agent-hooks/pre_tool_use.py`](../agent-hooks/pre_tool_use.py), declared in the same file | Claude Code runs it before each tool call; exit 2 blocks |
| 3. Auto-mode classifier | Claude Code | a model: not code from this repo, not relied on |

What the official documentation says about these layers in auto mode:

- Deny rules: *"Deny rules block in every mode, including `bypassPermissions`."*
  ([permission modes](https://code.claude.com/docs/en/permission-modes)).
- Hooks: *"PreToolUse hooks run before the permission prompt, for every tool except
  EndConversation"* and *"A hook that exits with code 2 stops the tool call before permission
  rules are evaluated"* ([permissions](https://code.claude.com/docs/en/permissions#extend-permissions-with-hooks)).
  The page names no exception for auto mode, but it does not state "auto mode" explicitly
  either, so it was tested (below).

**Observed on 2026-10-11, Claude Code 2.1.296, auto mode** (criterion-12 exit criterion 3):

| Attempt | Blocked by | Message |
|---|---|---|
| `gh pr merge 999999` (Bash) | hook | `Blocked by agent-hooks/pre_tool_use.py: gh pr merge is the owner's action` |
| Edit `agent-hooks/README.md` (Edit tool) | deny rule | `File is in a directory that is denied by your permission settings.` |
| Write `data/hook_probe.txt` (Write tool) | deny rule | `File is in a directory that is denied by your permission settings.` |
| `echo probe > data/hook_probe.txt` (Bash) | hook | `writes to data/ and lake/ are refused (hook_probe.txt)` |
| Read `.env` (Read tool) | deny rule | `File is in a directory that is denied by your permission settings.` |
| `cat .env` (Bash) | hook | `secrets files are never read or written by the agent (.env)` |
| `git status`, `make test-unit` | — | ran normally (467 passed, 15 skipped) |

`data/hook_probe.txt` does not exist afterwards. For the file tools the deny rule answered; for
Bash the hook answered first.

## What the agent may do

- Read the whole repo, except secrets files; read `data/` and `lake/` (list, stat, hash, copy
  out to a scratch directory).
- Edit code, tests and docs; run `make` targets that do not write `data/` or `lake/`
  (`lint`, `typecheck`, `test-unit`, `contract`, `eval`, `test-integration`, `mcp-server`,
  `plugin`), and `make dbt` with `RUNTIME_DB_PATH` pointing outside `data/`.
- Create branches, commit, and push a work branch.
- Query the warehouse through the read-only MCP server (one SELECT on four marts, 200 rows, 5 s).

## What the agent may not do

| Action | Layer 1 (deny) | Layer 2 (hook) |
|---|---|---|
| Write to `data/` or `lake/` | `Edit(/data/**)`, `Edit(/lake/**)` | file tools and shell, including `make ingest`, `make dbt` on the real warehouse, `dbt build`, `cyclebeat.cli ingest/load`, the compose `pipeline` profile |
| Read or write a secrets file | `Read`/`Edit` of `.env`, `.env.*`, `.ENV`, `.ENV.*` | the same plus private keys, `.netrc`, `.pgpass`, globs such as `cat .env*` |
| Force push | `git push *--force*`, `git push -f*`, `git push * -f*` | every form: `--force`, `-f` combined (`-uf`), `--force-with-lease`, `--force-if-includes`, `--mirror`, `+refspec`, option after the branch |
| Push to `main` | — | `git push origin main`, `HEAD:main`, `--all`, a bare `git push` from `main` |
| Merge into `main` | — | `git merge` on `main`, or after `git checkout/switch main` in the same command |
| Create or merge a PR | `gh pr create*`, `gh pr merge*` | the same plus the GitHub merge API |
| Call Render | `curl *render.com*`, `WebFetch(domain:api.render.com)` | deploy hooks, `api.render.com`, any `$RENDER_*` variable, `python -m tools.deploy` |
| Loosen its own guardrails | `Edit(/agent-hooks/**)`, `Edit(/.claude/settings.json)`, `Edit(/.claude/settings.local.json)` | writes to `agent-hooks/` and to any `.claude/settings*.json` |

Changing the guardrails is therefore the owner's action, in an editor or a terminal outside
the agent. Side effect: `.env.example` cannot be read with the Read tool (the `.env.*` deny rule
matches it); `cat .env.example` works.

## Limits — what this does not stop

- **The hook reads command text.** A `python -c` that builds a path at runtime, or a script
  that writes `data/` without naming it on the command line, gets through. The deny rules have
  the same limit for Bash: they cover `cat`, `sed`, redirections and the like, *"They don't
  apply to a command that reads files without naming them"* ([permissions](https://code.claude.com/docs/en/permissions)).
  This is a guardrail against mistakes, not against an adversary.
- **A mod can override a hook.** A Claude Code mod handling `tool.check` can approve a call a
  hook blocked, unless the hook is in managed settings (same page). None is installed for this
  project.
- **A `cd` is followed, an alias is not.** The hook tracks `cd <dir>` within one command line,
  not shell aliases or functions.
- **Docker.** `docker compose up` (default profile) is allowed: it mounts no `data/` (verified
  in `docker-compose.yml`). The `pipeline` profile, which writes `data/` and `lake/`, is refused.

## Minimum Claude Code version

**v2.1.295.** The hook is declared with `"onFailure": "block"`, which the
[hooks reference](https://code.claude.com/docs/en/hooks) introduces in v2.1.295: if the script
cannot start, crashes with an exit code other than 0 or 2, prints invalid output, or exceeds its
10 s timeout, the tool call is **blocked**.

With an older version the field does not exist and the documented default applies: *"when a hook
fails or times out, Claude Code still carries out the action"*. The script itself still fails
closed on any Python exception (it catches it and exits 2), so what an older version lets through
is narrower: a missing `python3`, a timeout, or a kill. The deny rules (layer 1) do not depend on
the version. How an older version treats the unknown `onFailure` field is not verified.

`python3` must be on `PATH` (3.10 or later; standard library only).

## Where the MCP server stands

Project-scoped servers from [`.mcp.json`](../.mcp.json) need a one-time approval in an
interactive session (https://code.claude.com/docs/en/mcp). The server is read-only by
construction: see [mcp-server/README.md](../mcp-server/README.md).
