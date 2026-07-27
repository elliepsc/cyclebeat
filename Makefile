.PHONY: setup lint test-unit test-integration dbt ingest api front eval audit

PYTHON ?= python
PIP ?= $(PYTHON) -m pip
DBT ?= dbt

setup:
	$(PIP) install -r requirements.txt

lint:
	$(PYTHON) -m compileall api agents app db ingest evaluation scripts

test-unit:
	$(PYTHON) -m pytest

test-integration:
	@echo "No integration test suite is defined yet." && exit 1

dbt:
	$(DBT) build --project-dir dbt --profiles-dir dbt

ingest:
	$(PYTHON) -m ingest.ingest_pipeline

api:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

front:
	@echo "No frontend is defined yet." && exit 1

eval:
	$(PYTHON) evaluation/session_eval.py

audit:
	@echo "No audit target is defined yet." && exit 1
