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

# The image serves the API. The React UI lands in phase 5 with its own service.
EXPOSE 8000

HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
