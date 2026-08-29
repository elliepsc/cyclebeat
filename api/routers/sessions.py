"""`/v1/sessions/*` — generate, replay, list, rate.

HTTP only. Every failure path is raised by the service as an `ApiError` and rendered as
RFC 7807 by the handlers in `api/errors.py`, so nothing here builds a response body by hand.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from api.dependencies import get_session_service
from api.schemas import (
    Feedback,
    FeedbackRequest,
    GenerateSessionRequest,
    SessionPage,
    SessionPlan,
)
from api.services import SessionService

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

SessionDep = Annotated[SessionService, Depends(get_session_service)]
SessionId = Annotated[str, Path(description="The session identifier.")]


@router.post(
    "/generate",
    response_model=SessionPlan,
    operation_id="generateSession",
    summary="Build a session from a track source",
)
def generate_session(request: GenerateSessionRequest, service: SessionDep) -> SessionPlan:
    """Resolve the source, plan, evaluate and persist.

    A 422 here is a refusal, not a crash: the planner will not return a session that skips its
    warmup or cooldown, and the structured reasons say which rule made it impossible.
    """
    return service.generate(request)


@router.get("", response_model=SessionPage, operation_id="listSessions")
def list_sessions(
    service: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionPage:
    """Past sessions, newest first."""
    return service.list(limit=limit, offset=offset)


@router.get("/{session_id}", response_model=SessionPlan, operation_id="getSession")
def get_session(session_id: SessionId, service: SessionDep) -> SessionPlan:
    """Replay a stored session exactly as it was served."""
    return service.get(session_id)


@router.post(
    "/{session_id}/feedback",
    response_model=Feedback,
    status_code=201,
    operation_id="submitFeedback",
)
def submit_feedback(
    session_id: SessionId, request: FeedbackRequest, service: SessionDep
) -> Feedback:
    """Rate a session. An unknown id is a 404, not an orphan row (ADR-008)."""
    return service.add_feedback(session_id, request)
