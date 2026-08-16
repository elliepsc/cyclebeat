"""Demo lake seeding — the committed snapshot E.8 requires.

`data/spike/raw_output.json` is 50 real Deezer tracks measured on 2026-07-29, each already
carrying its two librosa window BPMs. That makes it a complete, offline substitute for the
expensive half of the pipeline: seeding the lake from it needs **no network, no audio
download and no librosa install**, which is exactly what E.8 asks for so review and CI
never re-fetch and never consume quota.

The JSON is committed; the Parquet lake it produces is gitignored and rebuilt on demand, so
no binary artifact enters git and `make ingest` really does build the lake from source.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from cyclebeat.e2 import normalize_bpm, window_stability
from cyclebeat.models import RawResolution, RawTrack

SNAPSHOT = Path("data") / "spike" / "raw_output.json"
SNAPSHOT_DT = date(2026, 7, 29)  # the date of the phase-1 measurement run


def _stamp(payload: dict[str, Any]) -> datetime:
    raw = str(payload.get("generated_at") or "")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime(2026, 7, 29, tzinfo=UTC)


def _librosa_bpm(row: dict[str, Any]) -> float | None:
    """Reproduce the phase-1 backbone value without touching audio.

    Same rule as `cyclebeat.audio.backbone_bpm`: only a `usable` window pair counts, and
    the windows are normalized before averaging so a half-time pair stays correct.
    """
    a, b = row.get("librosa_window_a"), row.get("librosa_window_b")
    if window_stability(a, b) != "usable":
        return None
    na, nb = normalize_bpm(a), normalize_bpm(b)
    if na is None or nb is None:
        return None
    return (na + nb) / 2.0


def build_demo_batch(
    snapshot: Path | None = None,
) -> tuple[list[RawTrack], list[RawResolution]]:
    """Turn the committed spike output into raw.tracks / raw.resolutions rows."""
    path = snapshot or SNAPSHOT
    payload = json.loads(path.read_text(encoding="utf-8"))
    ingested_at = _stamp(payload)

    tracks: list[RawTrack] = []
    resolutions: list[RawResolution] = []

    for row in payload.get("measurements", []):
        deezer_id = row.get("deezer_id")
        if not deezer_id:
            # No Deezer id means the search never matched, so there is no track to record.
            # Dropping it here keeps raw.tracks honest; the miss is already reported in the
            # phase-1 spike report rather than being re-derived as a fake row.
            continue
        track_id = str(deezer_id)

        tracks.append(
            RawTrack(
                track_id=track_id,
                source_platform="deezer",
                title=str(row.get("title") or ""),
                artist=str(row.get("artist") or ""),
                duration_s=row.get("audio_seconds"),
                preview_url=None,  # the snapshot records the analysis, not the URL
                ingested_at=ingested_at,
            )
        )

        # Deezer's opinion. `0` means "no BPM" and is stored as NULL, never as a tempo.
        deezer_bpm = row.get("deezer_bpm_raw")
        resolutions.append(
            RawResolution(
                track_id=track_id,
                source="deezer",
                bpm_raw=float(deezer_bpm) if deezer_bpm else None,
                resolved_at=ingested_at,
            )
        )

        librosa_bpm = _librosa_bpm(row)
        if librosa_bpm is not None:
            resolutions.append(
                RawResolution(
                    track_id=track_id,
                    source="librosa",
                    bpm_raw=librosa_bpm,
                    resolved_at=ingested_at,
                )
            )

    return tracks, resolutions
