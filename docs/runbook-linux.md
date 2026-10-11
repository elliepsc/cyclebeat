# Runbook — restart CycleBeat on Linux (WSL)

Short checklist to get back to a working state in the Ubuntu shell. First-time installation
(uv, nvm, make, Docker Desktop WSL integration) is in
[CONTRIBUTING.md](../CONTRIBUTING.md); this page only covers what to run each time.

All commands run from the repo root, `~/projets/cyclebeat`.

## 1. Start of a session

```bash
cd ~/projets/cyclebeat
git fetch origin
git branch --show-current          # know where you are before touching anything
git status -sb
```

New work: cut the branch from `origin/main`, never from local `main`
(workflow in [CONTRIBUTING.md](../CONTRIBUTING.md)).

```bash
git checkout -b <type>/<slug> origin/main
```

## 2. Check the toolchain

```bash
uv --version && make --version | head -1 && node -v && docker --version
```

If `uv` is not found, reopen the terminal (it lives in `~/.local/bin`). If `node` is not
24.19.0, run `cd frontend && nvm use`. If `docker` is not found, start Docker Desktop on
Windows and check **Settings > Resources > WSL integration**.

After a pull that changed `pyproject.toml` or `uv.lock`: `make setup`.

## 3. Definition of done (offline, no network)

```bash
make lint && make test-unit
```

Expected on a clean clone without `DATABASE_URL` / `TEST_DATABASE_URL`:
**301 passed, 15 skipped** (the skips are the Postgres cases). Other gates: `make typecheck`,
`make eval`, `make contract` (after `make dbt`).

## 4. Rebuild the data and run the app

```bash
make ingest && make dbt            # demo data, no key, no network
make api                           # http://localhost:8000 , docs at /docs
```

Frontend, in a second terminal (`make api` must be running):

```bash
make front                         # http://localhost:5173
```

## 5. Docker Compose stack

```bash
make compose-ports                 # which host ports will be used
make compose-up                    # API + Prometheus + Grafana
make compose-pipeline              # same, plus Airflow
make compose-build                 # after editing code baked into the image
make compose-down                  # stop and remove containers
```

Defaults: API 8000, Airflow 8080, Prometheus 9090, Grafana 3000; the Makefile steps up to the
next free port when one is taken and prints the URLs it chose.

## 6. When something is off

| Symptom | Fix |
|---|---|
| `make dbt` fails on a column the code does not explain | Stale local DuckDB: `rm data/cyclebeat_runtime.duckdb && make ingest && make dbt` |
| `make contract` fails on the quality endpoints | `make ingest && make dbt && make contract` |
| `/health` does not answer `{"status":"ok"}` | Another service holds port 8000: stop it, or run the API elsewhere and set `VITE_API_URL` |
| `import` error right after removing a dependency | `make test-unit` (lint does not catch it) |
| `git push` asks for a password | `gh auth status`, then `gh auth login` if it is not logged in |

Never run an experiment against the real `lake/` or `data/`: use a temporary path, for example
`RUNTIME_DB_PATH=/tmp/cb_try.duckdb`.

## 7. End of a session

```bash
git status -sb
git add <files> && git commit -m "<type>: ..."
git push -u origin <branch>
gh pr create --fill
```

Add the `docs/ai-workflow.md` entry before opening the PR. `main` is never pushed to directly.
