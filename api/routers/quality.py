"""`/v1/quality/*` — the dashboard reads (E.3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import get_quality_service
from api.schemas import CoverageRow, QualitySummary
from api.services import QualityService

router = APIRouter(prefix="/v1/quality", tags=["quality"])

# `Annotated` rather than a `Depends()` default: same wiring, but it keeps the dependency out
# of the function signature's default values, which is what ruff's B008 is about.
QualityDep = Annotated[QualityService, Depends(get_quality_service)]


@router.get("/coverage", response_model=list[CoverageRow], operation_id="getQualityCoverage")
def get_coverage(service: QualityDep) -> list[CoverageRow]:
    """Rows of `mart_bpm_coverage`, one per BPM source."""
    return service.coverage()


@router.get("/summary", response_model=QualitySummary, operation_id="getQualitySummary")
def get_summary(service: QualityDep) -> QualitySummary:
    """One aggregate record over the catalogue (E.3)."""
    return service.summary()
