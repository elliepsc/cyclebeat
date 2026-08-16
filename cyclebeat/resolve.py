"""BPM resolution — the ADR-005 backbone applied through the E.2 rule.

Two stages, deliberately separate:

  `resolve_track_bpm`  fetches the preview and runs librosa. Needs network + the `audio`
                       extra. This is the only stage that costs anything.
  `cross_validate`     applies E.2/ADR-006 to whatever opinions exist. Pure, offline,
                       replayable — a change to the confidence rule never re-fetches audio.

That split is why `raw.resolutions` stores each source's raw opinion rather than a verdict:
the verdict is cheap to recompute, the opinions are expensive to obtain.

Idempotency (E.5): resolutions are keyed on `track_id + source + dt`. Re-running the same
day replaces those rows instead of appending, so a retried DAG run never duplicates.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cyclebeat.e2 import resolve as e2_resolve
from cyclebeat.http import PacedSession
from cyclebeat.models import RawResolution, RawTrack, ResolvedTrack

AUDIO_CACHE = Path("data") / "audio_cache"


def resolve_track_bpm(
    session: PacedSession,
    track: RawTrack,
    cache_dir: Path | None = None,
) -> RawResolution | None:
    """Download a track's preview and estimate its BPM with librosa (ADR-005 backbone).

    Returns None when the track has no preview or librosa cannot lock a stable tempo —
    absence of a source, which E.2 reads as "no opinion", never as a BPM of 0.
    """
    if not track.preview_url:
        return None

    from cyclebeat.audio import analyse, backbone_bpm

    destination = (cache_dir or AUDIO_CACHE) / f"deezer_{track.track_id}.mp3"
    path = session.download(track.preview_url, destination)
    bpm = backbone_bpm(analyse(path))
    if bpm is None:
        return None

    return RawResolution(
        track_id=track.track_id,
        source="librosa",
        bpm_raw=bpm,
        resolved_at=datetime.now(UTC),
    )


def group_by_track(
    resolutions: Iterable[RawResolution | dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    """Collapse resolution rows into the `{track_id: {source: bpm}}` shape E.2 consumes.

    Accepts model instances or the plain dicts the lake reads back, so the DAG can feed it
    straight from Parquet without a conversion step.
    """
    grouped: dict[str, dict[str, float | None]] = {}
    for row in resolutions:
        data = row if isinstance(row, dict) else row.model_dump()
        track_id = str(data["track_id"])
        grouped.setdefault(track_id, {})[str(data["source"])] = data.get("bpm_raw")
    return grouped


def cross_validate(
    resolutions: Iterable[RawResolution | dict[str, Any]],
    track_ids: Sequence[str] | None = None,
) -> list[ResolvedTrack]:
    """Apply E.2 + ADR-006 to every track's opinions.

    `track_ids` lets the caller include tracks that produced NO resolution at all: E.2 says
    those land at bpm NULL / `unknown` and are excluded from the planner, and they only
    appear in `mart_data_quality` if something asserts they exist. Passing only the
    resolutions would silently under-report the unresolved share.
    """
    grouped = group_by_track(resolutions)
    for track_id in track_ids or []:
        grouped.setdefault(str(track_id), {})

    resolved: list[ResolvedTrack] = []
    for track_id in sorted(grouped):
        verdict = e2_resolve(grouped[track_id])
        resolved.append(
            ResolvedTrack(
                track_id=track_id,
                bpm_effective=verdict["bpm_effective"],  # type: ignore[arg-type]
                zone=verdict["zone"],  # type: ignore[arg-type]
                confidence=verdict["confidence"],  # type: ignore[arg-type]
                confidence_method=str(verdict["confidence_method"]),
                n_sources_agree=int(verdict["n_sources_agree"]),  # type: ignore[call-overload]
                review=bool(verdict["review"]),
            )
        )
    return resolved


def deduplicate(
    resolutions: Sequence[RawResolution], dt: date | str
) -> list[RawResolution]:
    """Enforce the E.5 idempotency key `track_id + source + dt` within one batch.

    The `dt` is the partition the batch is about to be written to, so two opinions from the
    same source about the same track on the same day collapse to the last one rather than
    duplicating. Cross-partition idempotency comes from `lake.write_partition`, which
    overwrites the partition instead of appending to it.
    """
    del dt  # the partition is the third key component; the caller supplies it as the path
    latest: dict[tuple[str, str], RawResolution] = {}
    for resolution in resolutions:
        latest[(resolution.track_id, resolution.source)] = resolution
    return list(latest.values())


def confidence_distribution(resolved: Sequence[ResolvedTrack]) -> dict[str, int]:
    """Counts per `confidence_method` — the phase-2 exit criterion's measured figure."""
    return dict(Counter(track.confidence_method for track in resolved))
