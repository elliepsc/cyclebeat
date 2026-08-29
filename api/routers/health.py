"""Liveness probe.

Unversioned on purpose: it is not a business route, and the Dockerfile HEALTHCHECK plus the
compose services already target `/health`.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
def get_health() -> Health:
    return Health()
