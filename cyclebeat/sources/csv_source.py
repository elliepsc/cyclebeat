"""CSV import — the manual floor of ADR-005.

The one source that depends on no third party at all. ADR-005 accepts a real dependency on
Deezer serving public previews; this is the mitigation that keeps the pipeline usable if
that ever stops: an owner-supplied CSV still produces tracks and BPM.

Two shapes are accepted, both by column presence rather than by position:

    artist,title              -> a playlist to resolve against Deezer (no BPM opinion)
    artist,title,bpm          -> a manual BPM, recorded as source `manual`
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from cyclebeat.models import RawResolution, RawTrack

SOURCE_PLATFORM = "csv"


def _slug(artist: str, title: str) -> str:
    """Stable local id for a CSV row that has no platform id yet.

    Prefixed so it can never collide with a Deezer numeric id, and deterministic so
    re-importing the same CSV is idempotent on the `track_id+source+dt` key.
    """
    normalized = f"{artist.strip().lower()}|{title.strip().lower()}"
    return "csv:" + normalized.replace(" ", "_")


def read_csv(
    path: Path, ingested_at: datetime | None = None
) -> tuple[list[RawTrack], list[RawResolution]]:
    """Read a manual playlist. Rows missing artist or title are skipped, not guessed."""
    stamp = ingested_at or datetime.now(UTC)
    tracks: list[RawTrack] = []
    resolutions: list[RawResolution] = []

    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            artist = (row.get("artist") or "").strip()
            title = (row.get("title") or "").strip()
            if not artist or not title:
                continue

            track_id = _slug(artist, title)
            tracks.append(
                RawTrack(
                    track_id=track_id,
                    source_platform=SOURCE_PLATFORM,
                    title=title,
                    artist=artist,
                    ingested_at=stamp,
                )
            )

            raw_bpm = (row.get("bpm") or "").strip()
            if raw_bpm:
                try:
                    bpm = float(raw_bpm)
                except ValueError:
                    # A malformed BPM is dropped rather than coerced: E.2 treats absence as
                    # NULL, and inventing a number here would silently enter the warehouse.
                    continue
                resolutions.append(
                    RawResolution(
                        track_id=track_id,
                        source="manual",
                        bpm_raw=bpm,
                        resolved_at=stamp,
                    )
                )

    return tracks, resolutions
