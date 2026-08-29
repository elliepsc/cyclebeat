"""CycleBeat API — app factory (§7, contract-first).

Replaces the v1 module wholesale. What went: the flat unversioned routes (`/session/demo`,
`/session/generated`, `/feedback`, `/feedback/stats`), the JSON-file store they read, and the
deliberate 501 on `POST /session/generate` that CLAUDE.md kept parked until this phase. The
resolver (phase 2) and the engine (phase 3) exist now, so that endpoint is real, versioned as
`POST /v1/sessions/generate`.

Layering: `routers/` -> `services/` -> `repositories/`. FastAPI is imported only inside
`api/`; `cyclebeat/` stays a plain domain package that the planner tests import on its own.

`openapi.yaml` is the contract and is NOT generated from this app. It is written by hand and
CI asserts the two agree (`tests/test_api_contract.py`) — the divergence check is what makes
the contract binding rather than decorative.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.errors import register_error_handlers
from api.routers import health, quality, sessions

# Kept in step with `info.version` in openapi.yaml; the contract test compares them.
API_VERSION = "1.0.0"


def create_app() -> FastAPI:
    app = FastAPI(
        title="CycleBeat API",
        version=API_VERSION,
        description=(
            "BPM-driven indoor-cycling session planner. Sessions are built by a "
            "deterministic engine; no LLM makes a structural decision."
        ),
    )

    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(quality.router)

    _instrument(app)
    return app


def _instrument(app: FastAPI) -> None:
    """Attach Prometheus metrics when the dependency is present.

    Optional rather than required: compose scrapes `/metrics`, but the unit suite and a bare
    `uvicorn api.main:app` must not depend on the instrumentator being installed.
    """
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:  # pragma: no cover - exercised only where the extra is absent
        return
    Instrumentator().instrument(app).expose(app, include_in_schema=False)


app = create_app()
