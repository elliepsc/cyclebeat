# Contributing to CycleBeat

How to set up the toolchain and how work reaches `main`. The project overview is in
[README.md](README.md); the rules every contributor (human or agent) follows are in
[CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md).

## Development environment

CycleBeat is developed on **WSL2 (Ubuntu)** only. Clone it on the Linux filesystem
(`~/projets/cyclebeat`), never under `/mnt/c`: file access is much faster there, and `make`,
`uv`, Node and Docker all see one consistent Linux toolchain. The definition of done is
`make lint && make test-unit` (plus the other targets listed in [CLAUDE.md](CLAUDE.md)).

### Prerequisites

Run these in the Ubuntu shell.

**make.** Usually present; otherwise `sudo apt install build-essential`. Check with
`make --version`.

**uv** (Python toolchain). Install with Astral's script
([installation docs](https://docs.astral.sh/uv/getting-started/installation/)):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

It installs into `~/.local/bin`; reopen the shell so it is on `PATH`. `uv` provisions
CPython 3.11 itself (`.python-version`) and resolves from `uv.lock`, so no system Python
or global `pip` is involved.

**Node via nvm.** Install nvm with the script from the
[nvm README](https://github.com/nvm-sh/nvm#installing-and-updating), reopen the shell,
then from the repo:

```bash
cd frontend
nvm install   # reads frontend/.nvmrc (currently 24.19.0)
nvm use
```

`frontend/package.json` also pins `engines.node` to the same version. `make front`,
`make front-test` and `make front-gen` call `npm` and expect that Node on `PATH`.

**Docker Desktop with WSL integration.** Install Docker Desktop on Windows, then enable
**Settings > Resources > WSL integration** for your Ubuntu distribution
([Docker docs](https://docs.docker.com/desktop/features/wsl/)). Check from Ubuntu with
`docker --version` and `docker compose version`. It is needed for the `compose-*` targets;
`make lint` and `make test-unit` do not use it.

### First run

```bash
make setup                  # uv sync: creates .venv/ in the repo
make lint && make test-unit
```

`.venv/` is gitignored and lives in the repo as usual. On a clean clone without
`DATABASE_URL` or `TEST_DATABASE_URL`, `make test-unit` reports **301 passed, 15 skipped**
(measured 2026-10-09). The 15 skips are the Postgres cases of
`tests/unit/test_api_repositories.py`, which need a real server and read
`TEST_DATABASE_URL`; CI runs them against `postgres:16-alpine`. The 6 Airflow DAG tests
(`tests/test_dags.py`) run here.

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

## Deployment

Render deploys nothing by itself (`autoDeployTrigger: off` in `render.yaml`). The `deploy` job of
`.github/workflows/ci.yml` runs on `main` only, after the `build` and `frontend` jobs are green,
and does this through `tools/deploy.py`:

1. triggers the deploy hook of the API and of the site for the exact commit (`ref=<sha>`);
2. polls the Render API every 15 s, up to 20 min, until each deploy is `live` on that commit;
3. smoke-tests production: `/health`, a real `POST /v1/sessions/generate` (demo source, one test
   session per deploy), the CORS preflight from the site, and the site itself.

A failed deploy job leaves the new version live: there is no automatic rollback. Re-run it from the
Actions tab (**Run workflow** on `main`) once the cause is fixed. To run only the smoke test
against production, from any checkout, with no secret:

```bash
API_URL=https://cyclebeat-api.onrender.com WEB_URL=https://cyclebeat-web.onrender.com   python -m tools.deploy --smoke-only
```

**GitHub environment `production`** (limited to `main`, no required reviewer):

| Kind | Name | Content |
|---|---|---|
| Secret | `RENDER_API_KEY` | Render API key |
| Secret | `RENDER_DEPLOY_HOOK_API`, `RENDER_DEPLOY_HOOK_WEB` | deploy hook URLs (they contain a key: regenerate a hook if one leaks) |
| Variable | `RENDER_API_SERVICE_ID`, `RENDER_WEB_SERVICE_ID` | Render service ids (`srv-...`) |
| Variable | `API_URL`, `WEB_URL` | public URLs of the API and the site |

`render.yaml` owns the services' settings. A service's **Manual Deploy** does not re-read it; the
Blueprint's **Manual sync** does, and is what applies a changed value or creates a service.

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

### `/health` answers something other than `{"status":"ok"}`

Another service is using port 8000 (for example the `weather-mlops` container), not CycleBeat.
Stop it, or run the API on another port and set `VITE_API_URL` to match when you start the
frontend.

### Experiments never write to the real `lake/` or `data/`

When you try something out (a rebuild, a count, a spike), work in an export or a temporary
directory: `RUNTIME_DB_PATH=/tmp/cb_try.duckdb`, a copy of the folder, never an in-place run on
`lake/` or `data/`. Those are the state your next real run starts from.
