"""Deezer extraction — the ADR-005 catalogue, preview provider and enrichment source.

Deezer plays two distinct roles, and conflating them is the mistake this module is shaped
to prevent:

  1. **Catalogue + preview** (the backbone). `/chart` or `/search` finds tracks, `/track`
     carries the 30 s `preview` URL that librosa actually analyses.
  2. **`bpm` field** (enrichment only). Present on ~23 % of current releases and ~65 % of
     classics (phase-1 spike). It raises confidence to 0.9 when it agrees with librosa
     within the E.2 tolerance, and never blocks or moves a resolution (ADR-006).

The public API needs no key and no account — that is why ADR-005 could drop Jamendo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cyclebeat.http import PacedSession
from cyclebeat.models import RawResolution, RawTrack

DEEZER_CHART = "https://api.deezer.com/chart/0/tracks"
DEEZER_TRACK = "https://api.deezer.com/track/{track_id}"
DEEZER_SEARCH = "https://api.deezer.com/search"

SOURCE_PLATFORM = "deezer"


def _now() -> datetime:
    return datetime.now(UTC)


def _to_track(detail: dict[str, Any], ingested_at: datetime) -> RawTrack:
    artist = detail.get("artist") or {}
    return RawTrack(
        track_id=str(detail.get("id")),
        source_platform=SOURCE_PLATFORM,
        title=str(detail.get("title") or ""),
        artist=str(artist.get("name") or ""),
        duration_s=float(detail["duration"]) if detail.get("duration") else None,
        preview_url=detail.get("preview") or None,
        ingested_at=ingested_at,
    )


def fetch_chart(session: PacedSession, limit: int = 30) -> list[str]:
    """Track ids from the global chart. The `mainstream` set of the phase-1 spike."""
    payload, _ = session.get_json(DEEZER_CHART, {"limit": limit})
    return [str(item["id"]) for item in payload.get("data", []) if item.get("id") is not None]


def search_track(session: PacedSession, artist: str, title: str) -> str | None:
    """Resolve an (artist, title) pair to a Deezer track id, or None when there is no hit."""
    payload, _ = session.get_json(DEEZER_SEARCH, {"q": f'artist:"{artist}" track:"{title}"'})
    hits = payload.get("data") or []
    if not hits:
        payload, _ = session.get_json(DEEZER_SEARCH, {"q": f"{artist} {title}"})
        hits = payload.get("data") or []
    return str(hits[0]["id"]) if hits else None


def fetch_track(
    session: PacedSession, track_id: str, ingested_at: datetime | None = None
) -> tuple[RawTrack, RawResolution]:
    """Fetch one track's metadata, returning its raw.tracks row and its bpm opinion.

    The resolution row is always produced, even when Deezer has no BPM: `bpm_raw` is then
    None, which E.2 reads as absence of a source. Recording the absence explicitly is what
    lets `mart_data_quality` report coverage per source instead of guessing it.
    """
    stamp = ingested_at or _now()
    detail, latency_ms = session.get_json(DEEZER_TRACK.format(track_id=track_id))

    # Deezer encodes "no BPM" as exactly 0, which is not a tempo. E.2 normalization already
    # rejects non-positive values, but storing 0 in raw.resolutions would misreport coverage.
    raw_bpm = detail.get("bpm")
    bpm = float(raw_bpm) if raw_bpm else None

    resolution = RawResolution(
        track_id=str(track_id),
        source="deezer",
        bpm_raw=bpm,
        resolved_at=stamp,
        latency_ms=int(latency_ms) if latency_ms else None,
    )
    return _to_track(detail, stamp), resolution


def extract_chart(
    session: PacedSession, limit: int = 30
) -> tuple[list[RawTrack], list[RawResolution]]:
    """The `extract_deezer` task body: chart -> per-track detail. No business logic in dags/."""
    stamp = _now()
    tracks: list[RawTrack] = []
    resolutions: list[RawResolution] = []
    for track_id in fetch_chart(session, limit):
        track, resolution = fetch_track(session, track_id, stamp)
        tracks.append(track)
        resolutions.append(resolution)
    return tracks, resolutions
