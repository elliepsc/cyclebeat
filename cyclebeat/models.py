"""The domain shapes, as pydantic v2 models (E.6: pydantic v2 everywhere).

Two families live here.

**The E.2 row shapes** — the contract between the extractors, the lake and the DuckDB
loader. E.2 fixes the columns; nothing here may add or rename one without an impact
analysis.

    raw.tracks      : track_id, source_platform, title, artist, duration_s,
                      preview_url, ingested_at
    raw.resolutions : track_id, source, bpm_raw, resolved_at, latency_ms

**The session shapes** (phase 3) — what the planner consumes and produces, and what the
evaluator returns. `SessionParams` mirrors the E.3 request; `SessionPlan` is the *domain*
object, not the wire shape. Mapping it onto E.3's 200 response (and its per-segment
`coaching` block) is phase 4 / phase 6 work, which is why no `coaching` field exists here:
phase 3 is deterministic, and the LLM never sees this module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# E.2 fixes this enum. ADR-005 dropped the Jamendo catalogue but did NOT change the enum:
# `librosa` is the backbone, `deezer` enrichment, `manual` the CSV floor, `getsongbpm`
# an optional source that has never been measured or adopted.
ResolutionSource = Literal["deezer", "librosa", "getsongbpm", "manual"]


class RawTrack(BaseModel):
    """One row of `raw.tracks`."""

    track_id: str
    source_platform: str
    title: str
    artist: str
    duration_s: float | None = None
    preview_url: str | None = None
    ingested_at: datetime


class RawResolution(BaseModel):
    """One row of `raw.resolutions` — a single source's opinion about one track.

    Deliberately NOT the resolved BPM: this table records what each source said, and the
    E.2 confidence rule is applied downstream. Keeping the raw opinions means a change to
    the rule can be replayed without re-fetching anything.
    """

    track_id: str
    source: ResolutionSource
    bpm_raw: float | None = None
    resolved_at: datetime
    latency_ms: int | None = None


class ResolvedTrack(BaseModel):
    """The E.2 verdict for one track, as it lands in `dim_track`."""

    track_id: str
    bpm_effective: float | None = None
    zone: str | None = None
    confidence: float | None = None
    confidence_method: str
    n_sources_agree: int = 0
    review: bool = False


class WindowedTempo(BaseModel):
    """A librosa estimate on two disjoint windows, plus the E.2 stability verdict."""

    window_a: float | None = None
    window_b: float | None = None
    seconds: float | None = None
    stability: str = Field(description="usable | unstable | too_short")


# ── Session shapes (phase 3) ─────────────────────────────────────────────────────────────

# E.3 fixes these two enums. `intervals` is NOT `hiit`: the v1 note used the latter, E.3 uses
# the former, and the truth-source order settles it (ADR-007, disambiguation 2).
Level = Literal["beginner", "intermediate", "advanced"]
Goal = Literal["endurance", "intervals", "recovery"]

# E.2 fixes the zones. `cyclebeat.e2.zone_for` is the only thing that produces one.
Zone = Literal["Z1", "Z2", "Z3", "Z4", "Z5"]

# What a segment is FOR, derived from its zone and its position. Narrative labelling only:
# no rule keys off a role, so mislabelling one cannot make an unsafe session look safe.
SegmentRole = Literal[
    "warmup", "recovery", "endurance", "cardio", "intensity", "sprint", "cooldown"
]


class SessionParams(BaseModel):
    """The user's request. Mirrors the E.3 `POST /v1/sessions/generate` body.

    `source` is deliberately absent: resolving a source into a catalogue is the phase-4
    service's job, and the planner is handed the tracks it already found.
    """

    level: Level
    goal: Goal
    # E.3: duration_min int (20..120). The bound belongs to the contract, so it is declared
    # rather than checked inside the planner.
    duration_min: int = Field(ge=20, le=120)

    @property
    def target_duration_s(self) -> float:
        """The target in seconds, which is the unit every duration rule is written in."""
        return float(self.duration_min) * 60.0


class PlannerTrack(BaseModel):
    """One candidate track, as `dim_track` exposes it.

    `bpm_effective is None` is exactly `planner_eligible = false` (ADR-006) — the planner
    filters on that contract instead of re-deriving E.2.
    """

    track_id: str
    title: str
    artist: str
    duration_s: float
    bpm_effective: float | None = None
    zone: Zone | None = None
    confidence: float | None = None
    preview_url: str | None = None


class Segment(BaseModel):
    """One placed track. `duration_s` is the FULL track duration (ADR-007, decision 3)."""

    order: int
    track: PlannerTrack
    zone: Zone
    role: SegmentRole
    duration_s: float


class ExcludedTrack(BaseModel):
    """A candidate the planner refused, with the reason it refused it.

    Every input track ends up either in a segment or in here — a track never just vanishes.
    That is asserted as a property-based invariant, not left to review.
    """

    track_id: str
    reason: str


class SessionPlan(BaseModel):
    """What the planner produces: the structure of a session, with no coaching text."""

    params: SessionParams
    segments: list[Segment]
    excluded: list[ExcludedTrack] = Field(default_factory=list)
    # E.3. Signed: positive means the session overruns the target.
    duration_gap_s: float = 0.0
    warnings: list[str] = Field(default_factory=list)

    @property
    def total_duration_s(self) -> float:
        return sum(segment.duration_s for segment in self.segments)


class EvaluationResult(BaseModel):
    """What the evaluator returns for a finished plan.

    `verdict` is E.3's two-value enum. A blocking failure is NOT a third verdict: it lands in
    `blocking_failures`, which phase 4 turns into the E.3 422 (ADR-007, decision 2).
    """

    checks: dict[str, bool]
    score: float
    verdict: Literal["safe", "review"]
    blocking_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
