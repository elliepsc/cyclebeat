# Architecture — every box and arrow, with its source

The diagram and the summary of how the parts fit together are in the
[README's Architecture section](../README.md#architecture). This page sources each box and each
arrow (A1-A18) of that diagram in the code. Moved from the README with issue #70; six pointers
that had drifted since PR #63 were refreshed (`api/services/session.py`, `cyclebeat/cli.py`,
`cyclebeat/app_store.py`, `cyclebeat/lake.py`). Line numbers checked against `main` at 66fdab9;
they drift as the files change.

| Box or arrow | What | Source |
|---|---|---|
| CI test jobs | `build`, `frontend`, `integration`, `security` | `.github/workflows/ci.yml:27`, `:119`, `:157`, `:182` |
| deploy | runs on `main` only | `.github/workflows/ci.yml:198-200` |
| A1 | `deploy` waits for the four test jobs | `.github/workflows/ci.yml:199` |
| A2, A3 | `tools/deploy.py` calls the two deploy hooks, then smoke-tests health, generate, CORS and the web page; Render's auto-deploy is off | `.github/workflows/ci.yml:221-226`; `tools/deploy.py:115`, `:245-266`; `render.yaml:30`, `:48` |
| cyclebeat-web | Render static site built by Vite | `render.yaml:42-47` |
| cyclebeat-api | Render Docker service; the container runs uvicorn only | `render.yaml:23-26`; `Dockerfile:61` |
| planner + evaluator | called by the generate service | `api/services/session.py:67`, `:77` |
| A4 | the bundle calls the API URL fixed at build time; the API lets that origin in | `render.yaml:36-37`, `:55-56`; `frontend/src/api/client.ts:6` |
| A5, SQLite | no `DATABASE_URL` in production, so the store is SQLite | `render.yaml:31-37`; `api/repositories/database.py:153-167` |
| A6, A10 | the API opens the warehouse read-only; it falls back to read-write only if that open fails (a missing file), which the image's baked-in warehouse does not hit | `api/repositories/warehouse.py:38-42`; `api/repositories/track.py:27` |
| API image build, A7 | one `RUN` builds the warehouse from versioned files; the API reads it at `RUNTIME_DB_PATH` | `Dockerfile:40-45`; `render.yaml:32-33` |
| web (compose) | nginx serves the built bundle | `docker-compose.yml:86-92`; `frontend/Dockerfile:24-28` |
| api (compose), A11 | built from the same `Dockerfile` | `docker-compose.yml:60-61`, `:76` |
| A8 | the compose bundle points at the compose API | `docker-compose.yml:90`; `frontend/src/api/client.ts:6` |
| A9, postgres | `DATABASE_URL` set, so the store is Postgres | `docker-compose.yml:40-47`, `:69`; `api/repositories/database.py:106-107`, `:153-158` |
| DuckDB (compose) | the image's warehouse, not mounted over | `docker-compose.yml:58-59`, `:65` |
| Local pipeline | `make ingest`, `make dbt`; compose profile `pipeline` | `Makefile:81-82`, `:92-96`; `docker-compose.yml:106-138`, `:148-191` |
| sources | demo snapshot or live Deezer, optional CSV; patterns JSON | `cyclebeat/cli.py:48-67`; `ingest/ingest_pipeline.py:43` |
| app store | engine picked by `DATABASE_URL` | `cyclebeat/app_store.py:61`, `:64-68` |
| lake | Parquet partitions under `lake/` | `cyclebeat/lake.py:27`, `:109` |
| DuckDB (local) | `RUNTIME_DB_PATH`, default `data/cyclebeat_runtime.duckdb` | `db/runtime.py:21-23`; `dbt/profiles.yml:8` |
| A12 | `cli ingest` writes the lake | `cyclebeat/cli.py:69`; `Makefile:94` |
| A13 | dlt stages the patterns in its own DuckDB file, `cyclebeat_ingestion.duckdb` in the working directory ([dlt docs](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb)); `save_patterns` then copies them into the runtime DuckDB | `ingest/ingest_pipeline.py:51-56` (dlt, no path given), `:59-61`; `db/runtime.py:63`; `Makefile:93` |
| A14 | `cli extract-app` copies sessions and feedback into the lake | `cyclebeat/cli.py:123`; `cyclebeat/app_store.py:176`; `Makefile:95` |
| A15 | `cli load` loads the lake into DuckDB | `cyclebeat/cli.py:106`; `cyclebeat/warehouse.py:122`; `Makefile:96` |
| A16 | dbt builds the marts in the same DuckDB | `dbt/profiles.yml:8`; `Makefile:82` |
| Airflow | three DAGs chained on lake assets | `dags/dag_ingest.py:36`; `dags/dag_resolve_bpm.py:34`; `dags/dag_build_warehouse.py:32` |
| A17 | `dag_ingest` and `dag_resolve_bpm` write the lake | `dags/dag_ingest.py:84`; `dags/dag_resolve_bpm.py:94` |
| A18 | `dag_build_warehouse`: extract-app, load, then dbt build | `dags/dag_build_warehouse.py:44-77` |
