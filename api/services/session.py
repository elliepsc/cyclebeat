"""Session generation, replay and feedback (§7 — logic layer).

Holds no SQL and opens no connection: repositories are injected, which is what lets
`tests/unit/test_api_services.py` exercise every branch below against fakes with no database.

It also holds no *rules*. The planner and the evaluator decide; this module resolves a source
into a catalogue, calls them, maps the domain object onto the wire shape, and persists. If a
session rule ever appears here, it belongs in `cyclebeat/rules.py` instead.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.errors import NotFoundError, UnprocessableError
from api.repositories import FeedbackRepository, SessionRepository, TrackRepository
from api.schemas import (
    ExcludedTrack,
    Feedback,
    FeedbackRequest,
    GenerateSessionRequest,
    Segment,
    SessionPage,
    SessionPlan,
    SessionSummary,
    Track,
)
from cyclebeat.evaluator import evaluate
from cyclebeat.models import PlannerTrack, SessionParams
from cyclebeat.planner import NoValidSessionError, plan_session


def _demo_mode() -> bool:
    """E.8: demo by default, with no key and no network."""
    return os.environ.get("CYCLEBEAT_DEMO", "1") != "0"


class SessionService:
    def __init__(
        self,
        tracks: TrackRepository,
        sessions: SessionRepository,
        feedback: FeedbackRepository,
    ) -> None:
        self._tracks = tracks
        self._sessions = sessions
        self._feedback = feedback

    # ── Generate ─────────────────────────────────────────────────────────────────────────

    def generate(self, request: GenerateSessionRequest) -> SessionPlan:
        catalogue = self._resolve_source(request)
        if not catalogue:
            raise UnprocessableError(
                "The source resolved to no usable track.",
                reasons=["empty_catalogue"],
            )

        params = SessionParams(
            level=request.level, goal=request.goal, duration_min=request.duration_min
        )

        try:
            plan = plan_session(catalogue, params)
        except NoValidSessionError as exc:
            # E.3 routes "no valid session possible" to a 422 with structured reasons. The
            # planner refuses rather than returning a session that skips its cooldown, and
            # that refusal is information, so its codes travel through unchanged.
            raise UnprocessableError(
                "No session satisfying the safety rules can be built from this source.",
                reasons=exc.reasons,
            ) from exc

        result = evaluate(plan, params)

        wire = SessionPlan(
            session_id=uuid.uuid4().hex,
            level=request.level,
            goal=request.goal,
            duration_min=request.duration_min,
            verdict=result.verdict,
            segments=[
                Segment(
                    order=segment.order,
                    track=Track.model_validate(segment.track.model_dump()),
                    zone=segment.zone,
                    role=segment.role,
                    duration_s=segment.duration_s,
                    # Phase 6 fills this. Nullable in the contract precisely so that lands
                    # without a breaking change.
                    coaching=None,
                )
                for segment in plan.segments
            ],
            excluded=[
                ExcludedTrack(track_id=item.track_id, reason=item.reason)
                for item in plan.excluded
            ],
            duration_gap_s=plan.duration_gap_s,
            # The evaluator's warnings are added to the planner's: the planner reports what it
            # could not do, the evaluator what it judges wrong, and a caller wants both.
            warnings=[*plan.warnings, *result.warnings],
            created_at=datetime.now(UTC),
        )

        self._sessions.save(wire.model_dump(mode="json"))
        return wire

    def _resolve_source(self, request: GenerateSessionRequest) -> list[PlannerTrack]:
        kind = request.source.type

        if kind == "demo":
            return self._tracks.planner_catalogue()

        if kind == "csv":
            from cyclebeat.sources.csv_source import read_csv

            path = request.source.value
            if not path:
                raise UnprocessableError(
                    "A csv source needs a path in `source.value`.", reasons=["missing_csv_path"]
                )
            try:
                tracks, resolutions = read_csv(Path(path))
            except FileNotFoundError as exc:
                raise UnprocessableError(
                    f"CSV not found: {path}", reasons=["csv_not_found"]
                ) from exc
            return _from_csv(tracks, resolutions)

        # deezer_url. Live network, so it is refused in DEMO_MODE -- which is the default and
        # what CI runs (E.8: no API quota consumed in review).
        if _demo_mode():
            raise UnprocessableError(
                "Deezer playlists need live network; the service is in demo mode.",
                reasons=["source_unavailable_in_demo_mode"],
            )
        raise UnprocessableError(
            "Live Deezer playlist import is not wired yet.",
            reasons=["deezer_url_not_implemented"],
        )

    # ── Replay and history ───────────────────────────────────────────────────────────────

    def get(self, session_id: str) -> SessionPlan:
        stored = self._sessions.get(session_id)
        if stored is None:
            raise NotFoundError(f"No session with id {session_id}.")
        return SessionPlan.model_validate(stored)

    def list(self, limit: int, offset: int) -> SessionPage:
        items, total = self._sessions.list(limit=limit, offset=offset)
        return SessionPage(
            items=[SessionSummary.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    # ── Feedback ─────────────────────────────────────────────────────────────────────────

    def add_feedback(self, session_id: str, request: FeedbackRequest) -> Feedback:
        """Rate a session.

        Existence is checked first so an unknown id is a 404 rather than an orphan row —
        which is the whole point of ADR-008 rekeying feedback on `session_id`.
        """
        if not self._sessions.exists(session_id):
            raise NotFoundError(f"No session with id {session_id}.")
        record = self._feedback.add(
            session_id=session_id,
            rating=request.rating,
            note=request.note,
            session_title=_title_for(session_id),
        )
        return Feedback.model_validate(record)


def _title_for(session_id: str) -> str:
    """The denormalized label the existing dbt feedback chain groups on (ADR-008).

    Sessions carry no user-facing title in the E.3 contract, so this is derived rather than
    invented: it keeps `mart_feedback_summary` populated without adding a field the contract
    never promised.
    """
    return f"session-{session_id[:8]}"


def _from_csv(tracks: list[Any], resolutions: list[Any]) -> list[PlannerTrack]:
    """Turn a CSV import into planner candidates.

    The manual BPM in the CSV is a single E.2 source, so it is passed through `e2.resolve`
    rather than trusted directly — the same rule the warehouse applies, applied once here too
    instead of a second variant.
    """
    from cyclebeat import e2

    by_track: dict[str, float | None] = {}
    for resolution in resolutions:
        by_track[resolution.track_id] = resolution.bpm_raw

    candidates: list[PlannerTrack] = []
    for track in tracks:
        verdict = e2.resolve({"manual": by_track.get(track.track_id)})
        bpm = verdict["bpm_effective"]
        candidates.append(
            PlannerTrack(
                track_id=track.track_id,
                title=track.title,
                artist=track.artist,
                duration_s=float(track.duration_s or 0.0),
                bpm_effective=None if bpm is None else float(bpm),  # type: ignore[arg-type]
                zone=verdict["zone"],  # type: ignore[arg-type]
                confidence=verdict["confidence"],  # type: ignore[arg-type]
                preview_url=track.preview_url,
            )
        )
    return candidates
