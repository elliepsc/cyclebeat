.PHONY: setup lock lint typecheck contract test test-unit test-integration dbt ingest ingest-live confidence-report airflow api front front-test front-gen eval audit compose-ports compose-up compose-monitoring compose-pipeline compose-build compose-down mcp-server plugin

# Everything runs through uv: it provisions the Python 3.11 toolchain itself
# (see .python-version) and resolves from uv.lock, so no global pip is involved.
UV ?= uv
RUN ?= $(UV) run
DBT ?= $(RUN) dbt

setup:
	$(UV) sync

lock:
	$(UV) lock

# agents/, app/, evaluation/ and scripts/ are gone (runbook step 3), so this is
# now the whole Python surface of the repo. `tools/` joined it in phase 1: without
# it the spike code would escape the definition of done entirely. `cyclebeat/` and
# `dags/` joined it in phase 2 — same reason.
lint:
	$(RUN) ruff check api cyclebeat dags db ingest evals tests tools catalogue_fixtures.py \
		mcp-server agent-hooks
	$(RUN) python -m tools.check_links

# Gating since phase 4. It was red only on the v1 `api/main.py`, which the contract-first
# rewrite deleted; `api/` is strict-clean now and CI runs this target.
typecheck:
	$(RUN) mypy

# The phase-4 exit criterion (§15): openapi.yaml and the implementation must not diverge.
# Two independent checks live in that file -- the hand-written contract against the schema
# FastAPI generates, and schemathesis driving the contract against the real app.
#
# Run it AFTER `make dbt`, so the quality endpoints answer against built marts.
contract:
	$(RUN) pytest tests/test_api_contract.py

test-unit:
	$(RUN) pytest

# Phase 8 (criterion 9): black-box HTTP tests against the full compose stack, run as its OWN
# compose project so it can neither collide with nor wipe the developer's `cyclebeat` stack
# (the final `down -v` removes this project's volumes only).
#   1. build and start api + web + postgres, wait until all three are healthy (bounded);
#   2. run tests/integration (addopts overridden: the default one ignores that directory);
#   3. on failure, dump `ps` and the logs; ALWAYS tear down; exit with the tests' status.
# Ports: 8000 / 4173 by default, override with CYCLEBEAT_API_PORT / CYCLEBEAT_WEB_PORT. They
# are exported to the tests too, so the URLs they target match what compose published.
# Passed per command, never `export`ed: a global export would also pin the ports of
# `compose-up`, and tools/compose_ports.py never probes a variable that is already set.
IT_PROJECT := cyclebeat-it
IT_API_PORT ?= $(or $(CYCLEBEAT_API_PORT),8000)
IT_WEB_PORT ?= $(or $(CYCLEBEAT_WEB_PORT),4173)
IT_ENV = CYCLEBEAT_API_PORT=$(IT_API_PORT) CYCLEBEAT_WEB_PORT=$(IT_WEB_PORT)
IT_COMPOSE = $(IT_ENV) docker compose -p $(IT_PROJECT)
IT_WAIT_S ?= 300

test-integration:
	@rc=0; \
	$(IT_COMPOSE) up --build --wait --wait-timeout $(IT_WAIT_S) || rc=$$?; \
	if [ $$rc -eq 0 ]; then \
		$(IT_ENV) \
		CYCLEBEAT_IT_API_URL=http://localhost:$(IT_API_PORT) \
		CYCLEBEAT_IT_WEB_URL=http://localhost:$(IT_WEB_PORT) \
		$(RUN) pytest -o addopts="" -q -m integration tests/integration || rc=$$?; \
	fi; \
	if [ $$rc -ne 0 ]; then \
		$(IT_COMPOSE) ps -a; \
		$(IT_COMPOSE) logs --no-color --tail=200; \
	fi; \
	$(IT_COMPOSE) down -v --remove-orphans; \
	exit $$rc

# Issue #45 (official grid, "Testing": both suites with a single command). A sequential
# recipe, not prerequisites: `make -j` would run prerequisites in parallel. Stops at the first
# failing suite and says which one; without Docker the integration suite fails, never skips.
test:
	@$(MAKE) --no-print-directory test-unit || { echo "make test: FAILED in the unit suite (make test-unit); the integration suite did not run" >&2; exit 1; }
	@$(MAKE) --no-print-directory test-integration || { echo "make test: FAILED in the integration suite (make test-integration)" >&2; exit 1; }
	@echo "make test: unit and integration suites passed"

dbt:
	$(DBT) build --project-dir dbt --profiles-dir dbt

# The §15 phase-2 exit criterion: the whole offline pipeline from cold, CLI only, no
# Airflow and no network. Three stages, in order:
#   1. the pattern knowledge base (dlt -> DuckDB), unchanged since phase 0;
#   2. extract into the Parquet lake — DEMO by default, off the committed snapshot (E.8);
#   3. extract the TRANSACTIONAL store (sessions, feedback) into the lake — ADR-009/§2.7.
#      A no-op when nobody has generated a session yet, so a clean clone still works;
#   4. load the lake into DuckDB and materialize the E.2 verdict dbt reads.
# `make ingest && make dbt` is therefore runnable on a clean clone with no credentials.
ingest:
	$(RUN) python -m ingest.ingest_pipeline
	$(RUN) python -m cyclebeat.cli ingest
	$(RUN) python -m cyclebeat.cli extract-app
	$(RUN) python -m cyclebeat.cli load

# Live extraction against the real Deezer API. Opt-in, never part of the DoD or CI (E.8).
# librosa resolution additionally needs `uv sync --extra audio`.
ingest-live:
	$(RUN) python -m cyclebeat.cli ingest --live
	$(RUN) python -m cyclebeat.cli load

# The measured confidence distribution — the other half of the phase-2 exit criterion.
confidence-report:
	$(RUN) python -m cyclebeat.cli confidence-report

# ── Docker Compose ───────────────────────────────────────────────────────────
# Each service keeps its conventional host port (8000 / 4173 / 8080 / 9090 / 3000). When
# another local stack already holds one, tools/compose_ports.py steps up to the
# next free port rather than letting the whole `up` die on `port is already
# allocated` -- and prints the URLs it settled on. Pin one by hand any time with
# e.g. CYCLEBEAT_API_PORT=9000.
# Deliberately NOT `$(RUN)`/`uv run`: tools/compose_ports.py imports nothing outside the
# standard library, so a bare interpreter runs it without needing the project environment
# (it also works before `make setup`).
PY ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
PORTS ?= $(PY) -m tools.compose_ports

# Show which host ports would be used, without starting anything.
compose-ports:
	$(PORTS)

# The full system: postgres -> api -> web, each waited on through its healthcheck.
# `--build` because the web bundle bakes in the API URL: a port change needs a rebuild.
compose-up:
	$(PORTS) docker compose up -d --build

# ... plus Prometheus + Grafana (profile `monitoring`).
compose-monitoring:
	$(PORTS) docker compose --profile monitoring up -d --build

# ... plus ingest + dbt (one-shot) and the Airflow orchestrator (E.5 check: the 3 DAGs green
# in the UI). Profile `pipeline`: these services WRITE the host's data/ and lake/.
compose-pipeline:
	$(PORTS) docker compose --profile pipeline up -d

# Rebuild the images, then bring the stack back up.
#
# Needed after editing code the image BAKES IN -- `COPY . .` in the Dockerfile, so
# cyclebeat/, api/, ingest/, db/, dbt/, tests/ and the dependency pins. NOT needed for
# dags/, lake/ or data/: those are bind-mounted, so a running container already sees the
# edit (Airflow re-parses the DAG folder on its own).
#
# No `down` first. `up -d` recreates exactly the services whose image or config changed
# and leaves the rest running; a `down` would only add downtime. Use compose-down when
# you actually want the network and the one-shot containers gone.
compose-build:
	$(PORTS) docker compose --profile pipeline up -d --build

compose-down:
	docker compose --profile pipeline --profile monitoring down --remove-orphans

api:
	$(RUN) uvicorn api.main:app --host 0.0.0.0 --port 8000

# Frontend (phase 5): React/Vite in frontend/. Node is pinned in frontend/.nvmrc.
front:
	npm --prefix frontend ci
	npm --prefix frontend run dev

front-test:
	npm --prefix frontend ci
	npm --prefix frontend test

# Regenerates frontend/src/api/schema.d.ts from openapi.yaml. CI fails if the committed file differs.
front-gen:
	npm --prefix frontend ci
	npm --prefix frontend run gen:api

# The adversarial playlists and the MUTATION CHECK -- the phase-3 exit criterion (§15).
# Physically separate from `test-unit` because §11 puts them in different buckets, and
# because it makes the exit criterion one command instead of a grep over pytest output.
#
# Unlike `test-unit`, this suite imports only cyclebeat + hypothesis, never Airflow.
# The phase-6 coach/copilot evals join it here.
eval:
	$(RUN) pytest evals

# Criterion 12: the read-only warehouse tools over MCP (stdio). Claude Code starts it through
# .mcp.json; run by hand, it waits for a client on stdin. Reads RUNTIME_DB_PATH, else
# data/cyclebeat_runtime.duckdb, read-only and never created.
mcp-server:
	$(RUN) python mcp-server/cyclebeat_warehouse.py

# Criterion 12: regenerate plugins/cyclebeat-agent-pack/ from .claude/skills, .claude/agents and
# .mcp.json. Committed build output, like frontend/src/api/schema.d.ts: CI fails on drift.
plugin:
	$(RUN) python -m tools.build_plugin

# Criterion 13: deterministic security scans, the same command locally and in CI (job `security`).
# Both scanners run from Docker images pinned by version AND digest: no Python dependency added.
#   - Semgrep (community packs, --metrics=off, never --config auto: it logs in to the registry
#     with the project URL) scans `git archive HEAD`, i.e. the COMMITTED tree: never .env,
#     never the untracked data/ and lake/. A first run prints every severity (report); the gate
#     run fails on severity ERROR only (owner decision, phase 10).
#   - gitleaks scans the git HISTORY of every ref from a read-only mount of .git alone (the
#     working tree, and so .env, is never mounted) and fails on any finding.
# No rule is excluded globally: an accepted finding gets a `nosemgrep: <rule>` comment on its
# own line, with the reason, and is triaged in security/scans/.
SEMGREP_IMAGE := semgrep/semgrep:1.178.0@sha256:32e459968daabe7ab86968184a29109b9564aa00392401156f9788452b42786b
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
SEMGREP_PACKS := --config p/python --config p/typescript --config p/dockerfile --config p/github-actions
SEMGREP = docker run --rm -v "$$src:/src:ro" -w /src $(SEMGREP_IMAGE) semgrep scan --metrics=off $(SEMGREP_PACKS)

audit:
	@set -e; src=$$(mktemp -d); trap 'rm -rf "$$src"' EXIT; \
	git archive HEAD | tar -x -C "$$src"; \
	echo "== semgrep: every severity (report) =="; \
	$(SEMGREP); \
	echo "== semgrep: gate, severity ERROR =="; \
	$(SEMGREP) --severity ERROR --error; \
	echo "== gitleaks: history of every ref =="; \
	docker run --rm -v "$(CURDIR)/.git:/repo/.git:ro" $(GITLEAKS_IMAGE) \
		git /repo --log-opts=--all --redact --no-banner --exit-code 1
