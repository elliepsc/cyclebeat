# Backend

There is no `backend/` package: the backend lives in two top-level packages.

| Path | What it holds |
|---|---|
| [`api/`](../api/) | The FastAPI service, in layers: [`routers/`](../api/routers/) (HTTP) → [`services/`](../api/services/) (use cases) → [`repositories/`](../api/repositories/) (the API's SQL, for the transactional store and the read-only DuckDB warehouse). Entry point: [`api/main.py`](../api/main.py). |
| [`cyclebeat/`](../cyclebeat/) | The domain and the pipeline, with no FastAPI import: BPM normalization and zones ([`e2.py`](../cyclebeat/e2.py)), the planner and its evaluator ([`planner.py`](../cyclebeat/planner.py), [`evaluator.py`](../cyclebeat/evaluator.py), [`rules.py`](../cyclebeat/rules.py)), the lake and the warehouse loader ([`lake.py`](../cyclebeat/lake.py), [`warehouse.py`](../cyclebeat/warehouse.py)), and the pipeline CLI ([`cli.py`](../cyclebeat/cli.py)). |

The API contract, written before the code: [`openapi.yaml`](../openapi.yaml). How the parts fit
together: the [architecture section of the README](../README.md#architecture).
