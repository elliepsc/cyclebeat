.PHONY: setup lock lint typecheck test-unit test-integration dbt ingest api front eval audit

# Everything runs through uv: it provisions the Python 3.11 toolchain itself
# (see .python-version) and resolves from uv.lock, so no global pip is involved.
UV ?= uv
RUN ?= $(UV) run
DBT ?= $(RUN) dbt

setup:
	$(UV) sync

lock:
	$(UV) lock

# Scoped to the code that survives the phase 0 purge (runbook step 3).
# Widen to the whole repo once agents/, app/, evaluation/ and scripts/ are gone.
lint:
	$(RUN) ruff check api db ingest

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

ingest:
	$(RUN) python -m ingest.ingest_pipeline

api:
	$(RUN) uvicorn api.main:app --host 0.0.0.0 --port 8000

front:
	@echo "No frontend is defined yet." && exit 1

eval:
	$(RUN) python evaluation/session_eval.py

audit:
	@echo "No audit target is defined yet." && exit 1
