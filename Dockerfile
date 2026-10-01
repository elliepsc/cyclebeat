FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv: dependency and toolchain manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# Python dependencies — resolution frozen by uv.lock.
#
# The API and dbt images exclude dev groups. The Airflow service overrides this with
# UV_SYNC_ARGS="" because `apache-airflow` lives in the dev group: it is a test dependency
# for the three E.5 DAG tests AND the runtime of the orchestrator, and with
# `package = false` there is no way to self-reference an extra. One build arg is cheaper
# than duplicating the pin in two places, where they would drift.
ARG UV_SYNC_ARGS="--no-dev"
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked ${UV_SYNC_ARGS}

# Source code
COPY . .

# Demo warehouse, built at image-build time (ADR-003): the served DuckDB is rebuilt from
# the VERSIONED files only -- data/cycling_patterns.json and the committed spike snapshot --
# so a deploy starts with no ingestion and no network (E.8, DEMO by default).
#
# .dockerignore does not cover every kind of local state (a root-level *.duckdb, the
# data/*.db SQLite store), so wipe them here instead of trusting the build context: what
# ends up in the image is then a function of git, not of the machine that ran the build.
# lake/ and data/*.duckdb are already excluded by .dockerignore; the rm is belt and braces.
RUN rm -rf lake data/*.duckdb data/*.duckdb.wal data/*.db *.duckdb \
    && python -m ingest.ingest_pipeline \
    && python -m cyclebeat.cli ingest \
    && python -m cyclebeat.cli extract-app \
    && python -m cyclebeat.cli load \
    && dbt build --project-dir dbt --profiles-dir dbt

# The image serves the API. The React UI lands in phase 5 with its own service.
EXPOSE 8000

# HEALTHCHECK and CMD must read the same ${PORT:-8000}: Render injects $PORT, and a probe
# hard-coded to 8000 would keep reporting a healthy server as sick.
HEALTHCHECK CMD curl --fail http://localhost:${PORT:-8000}/health || exit 1

# `exec` makes uvicorn PID 1, so it receives the stop signal itself; without it the wrapping
# `sh -c` stays PID 1 and swallows it. Everywhere but Render the API stays on 8000.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
