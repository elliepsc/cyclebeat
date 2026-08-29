"""Wiring: which repository each service gets.

One place, so a test can override a single dependency instead of monkeypatching a module.
FastAPI's `Depends` is used only here and in `routers/` — services take plain constructor
arguments and know nothing about it, which is what keeps them testable with fakes.
"""

from __future__ import annotations

from api.repositories import (
    FeedbackRepository,
    QualityRepository,
    SessionRepository,
    TrackRepository,
)
from api.services import QualityService, SessionService


def get_session_service() -> SessionService:
    return SessionService(
        tracks=TrackRepository(),
        sessions=SessionRepository(),
        feedback=FeedbackRepository(),
    )


def get_quality_service() -> QualityService:
    return QualityService(quality=QualityRepository())
