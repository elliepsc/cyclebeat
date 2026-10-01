# Contributing to CycleBeat

How to set up the toolchain and how work reaches `main`. The project overview is in
[README.md](README.md); the rules every contributor (human or agent) follows are in
[CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md).

## Development environment

> This section exists because the definition of done — `make lint && make test-unit` —
> is not runnable out of the box on a Windows checkout shared with WSL.

The repo sits on a Windows path and is used from two shells: Windows (PowerShell) and
WSL at `/mnt/c/...`. **They cannot share the same virtual environment.** Windows `uv`
creates `.venv/` with a `Scripts/` layout; Linux `uv` expects `bin/`, considers the
environment foreign, and tries to recreate it — which fails on the `drvfs` mount with
`failed to remove directory .venv/Scripts: Input/output error (os error 5)`.

Each OS therefore gets its own environment. **Do not delete `.venv/`** to "fix" the
error: it is the Windows environment and it is working. `.venv/` is gitignored, so none
of this affects the repository.

### WSL — recommended

`make` is already available; only `uv`'s environment path needs redirecting, to a
location on the Linux filesystem (also much faster than `/mnt/c`).

**What the helper does.** `uv` reads the environment variable `UV_PROJECT_ENVIRONMENT`
to decide *where* to put the project's virtual environment. Unset, it defaults to
`.venv/` in the repo — the Windows one. The helper points it at
`~/.venvs/<repo-name>` instead, on the Linux side, so both operating systems keep their
own environment and neither tries to overwrite the other's. It does nothing else: no
install, no repo state change. It is a convenience wrapper around one `export`.

**One-time setup.** Append it to `~/.bashrc`. The snippet below is copy-pasteable as-is
by anyone, on any clone path — it derives both the repo root and the environment name
from git, so there is nothing to edit:

```bash
cat >> ~/.bashrc <<'EOF'

# Give this repo a Linux-side uv environment (see CONTRIBUTING.md, "Development environment").
cyclebeat() {
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "cyclebeat: run this from inside the clone" >&2
    return 1
  }
  cd "$root" || return 1
  export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/$(basename "$root")"
}
EOF
```

**Then reload the file, once:**

```bash
source ~/.bashrc
```

`cat >>` appended text to a file on disk; it did not change the shell you are currently
sitting in, which read `~/.bashrc` when it started. `source` re-reads the file into
that running shell, which is what makes `cyclebeat` exist without opening a new
terminal. You only ever need this on the terminal where you ran the `cat >>` — every
terminal opened afterwards reads `~/.bashrc` on startup and gets the function for free.

If `cyclebeat` returns `command not found`, that reload is what is missing.

**Every new terminal.** The function is defined in every shell, but the `export` it
performs only lives in the shell that ran it — so it has to be *called*, not merely
defined. It is not something that "expires" and has to be recreated; it just has to be
invoked once per terminal. `cd` into the clone, then:

```bash
cyclebeat
```

It moves you to the repo root and exports `UV_PROJECT_ENVIRONMENT`. Only then:

```bash
make lint && make test-unit
```

Skipping `cyclebeat` is the single most common failure: `uv` falls back to the Windows
`.venv/` and raises the `os error 5` above. The first run after setup builds the Linux
environment (`uv` provisions CPython 3.11 itself); later runs reuse it.

Why a function rather than a plain `export` in `~/.bashrc`: `UV_PROJECT_ENVIRONMENT` is
not scoped to a project, so exporting it globally would make *every* uv project on the
machine share this one environment.

**Not on Windows+WSL?** On a plain Linux or macOS clone none of this applies — there is
only one `uv`, `.venv/` is native, and `make lint && make test-unit` works directly
after `make setup`.

### Windows PowerShell

Two prerequisites, both missing on a fresh setup:

```powershell
winget install --id ezwinports.make
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:USERPROFILE\.local\bin", "User")
```

The first installs `make` (`ezwinports` 4.4.1 — prefer it over `GnuWin32.Make`, still on
3.81). The second puts `uv` on `PATH`: the installer drops it in
`%USERPROFILE%\.local\bin`, which is not on `PATH` by default, so every Makefile target
would otherwise fail on `uv: command not found`. **Reopen the terminal**, then run
`make lint && make test-unit` — no per-session step is needed on this side.

---

## Contributing workflow — branches and pull requests

One phase (or chore) = one branch = one pull request. **`main` never receives a direct
commit**, and it only ever moves through a merged PR — a local merge produces no
reviewable diff and no CI gate on the result.

### The loop

Run these one at a time; the placeholders (`<slug>`) are meant to be replaced, not
pasted.

```bash
git checkout main
git fetch origin
git merge --ff-only origin/main
```

```bash
git checkout -b phase-N/<slug>
```

Work, then commit and publish **the branch** — never `git push origin main`:

```bash
git add -A
git commit -m "feat: ..."
git push -u origin phase-N/<slug>
```

`--ff-only` is deliberate: plain `git pull` silently creates a merge commit when local
`main` has drifted, while `--ff-only` refuses and tells you. Always `git fetch` before
cutting a branch, or the staleness is baked into it.

### Opening and merging the pull request

**When.** Right after `git push -u origin <branch>` succeeds. Pushing a branch does
*not* open a pull request, and opening one does *not* merge it — they are three
separate actions, and the last two happen **on GitHub, not in your terminal**.

This is the step most easily mistaken for a bug. `git fetch` only downloads what GitHub
already has, and `git merge --ff-only origin/main` only replays what `fetch` brought
back. Neither can merge anything: the merge is computed server-side, by GitHub, when
somebody clicks the button. Until then `origin/main` does not move, and re-running
those commands will keep printing `Already up to date.` — correctly. If you are waiting
for a file to appear on `main`, the thing to do is not another git command; it is the
click below.

**How, in the browser.** The `git push` output prints the exact link to use:

```
remote: Create a pull request for '<branch>' on GitHub by visiting:
remote:      https://github.com/<owner>/<repo>/pull/new/<branch>
```

1. Open that URL. If the branch already has a PR, GitHub redirects you to it instead.
2. Check the base branch reads `base: main` and the diff is what you expect.
3. Click **Create pull request**. The PR now exists — still unmerged.
4. On the PR page, click the green **Merge pull request**, then **Confirm merge**.
5. GitHub offers **Delete branch**. Do not use it here — see the deletion proof below.

Only once step 4 is done does `origin/main` move, and only then is it worth running
`git fetch` locally.

**How, with the GitHub CLI**, if `gh` is installed and authenticated (`gh auth login`):

```bash
gh pr create --fill
```

```bash
gh pr merge --merge
```

Check state before merging:

```bash
gh pr view --json state,mergeable,mergeableState
```

`state: OPEN` with `mergeable: true` and `mergeableState: clean` means no conflict and
no blocking check — the merge will go through. `mergeableState: dirty` means conflicts
to resolve first, `blocked` means a required check or review is missing.

**Verifying it actually landed.** Never trust the PR badge alone — confirm against the
remote:

```bash
git fetch origin && git cat-file -e origin/main:path/to/expected/file && echo "on main"
```

### After the merge

```bash
git checkout main
git fetch origin
git merge --ff-only origin/main
```

Then, and only then, clean up the branch — **after proving it holds nothing unique**:

```bash
git rev-list --count origin/main..origin/phase-N/<slug>   # MUST print 0
git branch -d phase-N/<slug>
git push origin --delete phase-N/<slug>
```

Never delete on the strength of "the PR says merged": a commit pushed to a branch
*after* its PR was merged exists nowhere else, and the PR still shows green. Any count
other than `0` is the number of commits deletion would destroy — inspect them with
`git log origin/main..origin/<branch>` and land them first. Use `-d`, never `-D`: `-d`
refuses to delete an unmerged branch, which is exactly the check worth keeping.

`archive/*` branches are the exception and must never be swept: they can report `0`
while being the only named pointer to a tree whose files were later removed on `main`.

---

## Troubleshooting

### `make dbt` fails on a staging model the code does not explain

Symptom: e.g. `Binder Error: Referenced column "title" not found` in `stg_sessions`, or
`check_invalid_rating` failing, on a branch where CI is green.

Cause: the runtime DuckDB (`data/cyclebeat_runtime.duckdb`) is gitignored local state and can
be left over from an older schema. CI always starts from a clean clone, so it never sees this.

Fix: retry on a fresh database before touching any model:

```bash
rm data/cyclebeat_runtime.duckdb
make ingest && make dbt
```

Or leave your database alone and point the run elsewhere:
`RUNTIME_DB_PATH=/tmp/cb_clean.duckdb make ingest && RUNTIME_DB_PATH=/tmp/cb_clean.duckdb make dbt`.

### `make contract` fails on the quality endpoints

Symptom: `tests/test_api_contract.py` fails (or schemathesis reports errors) on the
data-quality endpoints, on a checkout where the code is fine.

Cause: those endpoints read the dbt marts, and `make contract` does not build them. It must
run **after** `make dbt`, on a database that has been through `make ingest`.

Fix:

```bash
make ingest && make dbt && make contract
```

### Experiments never write to the real `lake/` or `data/`

When you try something out (a rebuild, a count, a spike), work in an export or a temporary
directory: `RUNTIME_DB_PATH=/tmp/cb_try.duckdb`, a copy of the folder, never an in-place run on
`lake/` or `data/`. Those are the state your next real run starts from.
