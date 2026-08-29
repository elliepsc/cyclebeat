"""The wire shapes, mirroring `openapi.yaml` (pydantic v2, E.6).

Deliberately separate from `cyclebeat/models.py`. Those are the **domain**: what the planner
reasons about. These are the **contract**: what goes over HTTP. The mapping between them lives
in `api/services/`, and keeping them apart is what lets `SessionPlan` stay free of a
`coaching` field until phase 6 while the wire already carries it as nullable.

`openapi.yaml` is the source of truth. If this file and that one disagree,
`tests/test_api_contract.py` fails and the YAML is right.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Level = Literal["beginner", "intermediate", "advanced"]
Goal = Literal["endurance", "intervals", "recovery"]
Zone = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]
Verdict = Literal["safe", "review"]
Rating = Literal["up", "down"]
SegmentRole = Literal[
    "warmup", "recovery", "endurance", "cardio", "intensity", "sprint", "cooldown"
]
SourceType = Literal["deezer_url", "csv", "demo"]


class Health(BaseModel):
    status: Literal["ok"] = "ok"


class Problem(BaseModel):
    """RFC 7807. E.3 fixes the four members; `reasons` is the additive one.

    `reasons` carries the planner's machine-readable refusal codes, so a client can react to
    *why* no session was possible instead of parsing `detail` as prose.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    reasons: list[str] = Field(default_factory=list)


class TrackSource(BaseModel):
    type: SourceType
    value: str = ""


class GenerateSessionRequest(BaseModel):
    source: TrackSource
    level: Level
    goal: Goal
    # E.3 fixes the bounds. Declared here so a bad duration is a 422 from the contract rather
    # than an exception from the planner.
    duration_min: int = Field(ge=20, le=120)


class Track(BaseModel):
    track_id: str
    title: str
    artist: str
    duration_s: float
    bpm_effective: float | None = None
    zone: Zone | None = None
    confidence: float | None = None
    preview_url: str | None = None


class Coaching(BaseModel):
    """Phase 6 populates this. Nullable on `Segment` until then."""

    instruction: str
    transition_cue: str
    kb_refs: list[str] = Field(default_factory=list)


class Segment(BaseModel):
    order: int
    track: Track
    zone: Zone
    role: SegmentRole
    duration_s: float
    coaching: Coaching | None = None


class ExcludedTrack(BaseModel):
    track_id: str
    reason: str


class SessionPlan(BaseModel):
    session_id: str
    level: Level
    goal: Goal
    duration_min: int
    verdict: Verdict
    segments: list[Segment]
    excluded: list[ExcludedTrack] = Field(default_factory=list)
    duration_gap_s: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class SessionSummary(BaseModel):
    session_id: str
    level: Level
    goal: Goal
    duration_min: int
    verdict: Verdict
    n_segments: int
    duration_gap_s: float
    created_at: datetime


class SessionPage(BaseModel):
    items: list[SessionSummary]
    total: int
    limit: int
    offset: int


class FeedbackRequest(BaseModel):
    rating: Rating
    note: str | None = Field(default=None, max_length=1000)


class Feedback(BaseModel):
    session_id: str
    rating: Rating
    note: str | None = None
    created_at: datetime


class CoverageRow(BaseModel):
    source: str
    n_tracks: int
    pct_of_catalogue: float
    n_usable: int


class QualitySummary(BaseModel):
    """E.3's "JSON record unique" over `mart_data_quality`.

    The mart's own grain (one row per `confidence_method`) is preserved under `by_method`, so
    aggregating here loses nothing.
    """

    n_tracks: int
    n_with_bpm: int
    pct_with_bpm: float
    n_flagged_review: int
    pct_flagged_review: float
    avg_confidence: float | None = None
    by_method: dict[str, int] = Field(default_factory=dict)
