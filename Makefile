.PHONY: setup lock lint typecheck test-unit test-integration dbt ingest ingest-live confidence-report airflow api front eval audit

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
	$(RUN) ruff check api cyclebeat dags db ingest tests tools

# Not gating yet: strict mypy is red on the v1 api/main.py, which phases 4-5
# rewrite contract-first. Configured now so the tooling is in place.
typecheck:
	$(RUN) mypy

test-unit:
	$(RUN) pytest

test-integration:
	@echo "No integration test suite is defined yet." && exit 1

dbt:
	$(DBT) build --project-dir dbt --profiles-dir dbt

# The §15 phase-2 exit criterion: the whole offline pipeline from cold, CLI only, no
# Airflow and no network. Three stages, in order:
#   1. the pattern knowledge base (dlt -> DuckDB), unchanged since phase 0;
#   2. extract into the Parquet lake — DEMO by default, off the committed snapshot (E.8);
#   3. load the lake into DuckDB and materialize the E.2 verdict dbt reads.
# `make ingest && make dbt` is therefore runnable on a clean clone with no credentials.
ingest:
	$(RUN) python -m ingest.ingest_pipeline
	$(RUN) python -m cyclebeat.cli ingest
	$(RUN) python -m cyclebeat.cli load

# Live extraction against the real Deezer API. Opt-in, never part of the DoD or CI (E.8).
# librosa resolution additionally needs `uv sync --extra audio`.
ingest-live:
	$(RUN) python -m cyclebeat.cli ingest --live
	$(RUN) python -m cyclebeat.cli load

# The measured confidence distribution — the other half of the phase-2 exit criterion.
confidence-report:
	$(RUN) python -m cyclebeat.cli confidence-report

api:
	$(RUN) uvicorn api.main:app --host 0.0.0.0 --port 8000

front:
	@echo "No frontend is defined yet." && exit 1

# The v1 evaluation/ suite was purged (ADR-001); the V3 coach/copilot evals
# arrive in phase 6. Fails explicitly rather than being absent (runbook step 4).
eval:
	@echo "No evaluation suite is defined yet (phase 6)." && exit 1

audit:
	@echo "No audit target is defined yet." && exit 1
