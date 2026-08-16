"""The E.2 row shapes, as pydantic v2 models (E.6: pydantic v2 everywhere).

These are the contract between the extractors, the lake and the DuckDB loader. E.2 fixes
the columns; nothing here may add or rename one without an impact analysis.

    raw.tracks      : track_id, source_platform, title, artist, duration_s,
                      preview_url, ingested_at
    raw.resolutions : track_id, source, bpm_raw, resolved_at, latency_ms
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
