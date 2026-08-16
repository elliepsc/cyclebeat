"""Phase-2 DE core: lake partitioning, resolution, demo snapshot, warehouse load.

No network, no audio, no librosa — everything runs off `data/spike/raw_output.json`, which
is committed (E.8). These are the tests that guard the E.2 contract end to end, from a
source's raw opinion to the row `dim_track` exposes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from cyclebeat import lake
from cyclebeat.demo import SNAPSHOT_DT, build_demo_batch
from cyclebeat.models import RawResolution, RawTrack
from cyclebeat.resolve import (
    confidence_distribution,
    cross_validate,
    deduplicate,
    group_by_track,
)

NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


def _track(track_id: str, **kwargs) -> RawTrack:
    defaults = dict(
        source_platform="deezer", title="T", artist="A", ingested_at=NOW
    )
    return RawTrack(track_id=track_id, **{**defaults, **kwargs})


def _resolution(track_id: str, source: str, bpm: float | None) -> RawResolution:
    return RawResolution(track_id=track_id, source=source, bpm_raw=bpm, resolved_at=NOW)


# --- lake -----------------------------------------------------------------------------


def test_partition_path_is_hive_partitioned() -> None:
    """The `dt=` prefix is what makes DuckDB read `dt` back as a column, not just a folder."""
    path = lake.partition_dir(lake.TRACKS, date(2026, 7, 29))
    assert path.as_posix().endswith("raw/tracks/dt=2026-07-29")


def test_lake_round_trip_recovers_the_dt_column(tmp_path) -> None:
    lake.write_partition([_track("1")], lake.TRACKS, date(2026, 7, 29), tmp_path)
    rows = lake.read_dataset(lake.TRACKS, tmp_path)
    assert len(rows) == 1
    assert rows[0]["dt"] == date(2026, 7, 29)


def test_nullable_bpm_column_survives_a_leading_null(tmp_path) -> None:
    """Regression: typing the column from the first row's VALUE types it VARCHAR whenever
    that row is None — and bpm_raw is None for every track Deezer has no BPM for, which is
    most of them. The DDL is read from the pydantic model instead."""
    rows = [_resolution("1", "deezer", None), _resolution("2", "librosa", 128.0)]
    lake.write_partition(rows, lake.RESOLUTIONS, date(2026, 7, 29), tmp_path)
    back = {r["track_id"]: r["bpm_raw"] for r in lake.read_dataset(lake.RESOLUTIONS, tmp_path)}
    assert back["1"] is None
    assert back["2"] == pytest.approx(128.0)


def test_rewriting_a_partition_replaces_rather_than_appends(tmp_path) -> None:
    for _ in range(3):
        lake.write_partition([_track("1")], lake.TRACKS, date(2026, 7, 29), tmp_path)
    assert len(lake.read_dataset(lake.TRACKS, tmp_path)) == 1


def test_empty_batch_writes_nothing(tmp_path) -> None:
    assert lake.write_partition([], lake.TRACKS, date(2026, 7, 29), tmp_path) is None


# --- resolution -----------------------------------------------------------------------


def test_deduplicate_keeps_one_row_per_track_and_source() -> None:
    rows = [
        _resolution("1", "deezer", 100.0),
        _resolution("1", "deezer", 120.0),
        _resolution("1", "librosa", 128.0),
    ]
    kept = deduplicate(rows, date(2026, 7, 29))
    assert len(kept) == 2
    assert {(r.track_id, r.source) for r in kept} == {("1", "deezer"), ("1", "librosa")}


def test_group_by_track_accepts_lake_dicts_and_models() -> None:
    """The DAG feeds this straight from Parquet, so both shapes must work."""
    from_models = group_by_track([_resolution("1", "deezer", 128.0)])
    from_dicts = group_by_track([{"track_id": "1", "source": "deezer", "bpm_raw": 128.0}])
    assert from_models == from_dicts == {"1": {"deezer": 128.0}}


def test_tracks_without_any_resolution_are_reported_as_unknown() -> None:
    """E.2: no source -> bpm NULL, excluded from the planner. Passing only the resolutions
    would silently under-report the unresolved share, so track_ids are passed explicitly."""
    resolved = cross_validate([_resolution("1", "librosa", 128.0)], ["1", "2"])
    by_id = {r.track_id: r for r in resolved}
    assert by_id["2"].confidence_method == "unknown"
    assert by_id["2"].bpm_effective is None
    assert by_id["2"].confidence is None


def test_deezer_zero_is_absence_not_a_tempo() -> None:
    """Deezer encodes 'no BPM' as exactly 0. It must not become a second agreeing source."""
    resolved = cross_validate(
        [_resolution("1", "deezer", 0.0), _resolution("1", "librosa", 128.0)]
    )
    assert resolved[0].confidence_method == "single_source"
    assert resolved[0].bpm_effective == pytest.approx(128.0)


# --- demo snapshot (E.8) --------------------------------------------------------------


def test_demo_batch_is_deduplicated_to_the_dim_track_grain() -> None:
    """The snapshot holds 50 measurements but 48 unique tracks: one row never matched a
    Deezer id (Get Lucky) and one track was measured in both sets (Billie Jean). dim_track's
    grain is track_id, so the warehouse must carry 48 — not the 50 the spike report counts."""
    tracks, _ = build_demo_batch()
    unique = {track.track_id for track in tracks}
    assert len(unique) == 48
    assert len(tracks) == 49  # the duplicate is collapsed downstream, not hidden here


def test_demo_batch_reproduces_the_phase_1_distribution() -> None:
    """The measured phase-2 baseline. A move here means the resolver drifted from E.2."""
    tracks, resolutions = build_demo_batch()
    resolved = cross_validate(resolutions, [t.track_id for t in tracks])
    distribution = confidence_distribution(resolved)

    assert sum(distribution.values()) == 48
    assert distribution == {
        "single_source": 27,
        "cross_validated": 12,
        "librosa_arbitrated": 4,
        "unknown": 5,
    }


def test_demo_snapshot_needs_no_network_or_librosa() -> None:
    """E.8: the committed snapshot is what makes CI free. Guard that it stays self-contained."""
    tracks, resolutions = build_demo_batch()
    assert tracks and resolutions
    assert all(r.source in {"deezer", "librosa"} for r in resolutions)


# --- warehouse ------------------------------------------------------------------------


def test_load_lake_materializes_one_verdict_per_track(tmp_path) -> None:
    import duckdb

    lake_root = tmp_path / "lake"
    db_path = tmp_path / "w.duckdb"
    tracks, resolutions = build_demo_batch()
    unique = list({t.track_id: t for t in tracks}.values())
    lake.write_partition(unique, lake.TRACKS, SNAPSHOT_DT, lake_root)
    lake.write_partition(
        deduplicate(resolutions, SNAPSHOT_DT), lake.RESOLUTIONS, SNAPSHOT_DT, lake_root
    )

    from cyclebeat.warehouse import load_lake

    counts = load_lake(db_path, lake_root)
    assert counts["raw_tracks"] == counts["raw_resolved"] == 48

    con = duckdb.connect(str(db_path))
    try:
        distinct = con.execute("select count(distinct track_id) from raw_resolved").fetchone()
    finally:
        con.close()
    assert distinct and distinct[0] == 48


def test_load_lake_is_idempotent(tmp_path) -> None:
    """Full replace from the lake, so re-running never doubles the warehouse."""
    from cyclebeat.warehouse import load_lake

    lake_root = tmp_path / "lake"
    db_path = tmp_path / "w.duckdb"
    tracks, resolutions = build_demo_batch()
    unique = list({t.track_id: t for t in tracks}.values())
    lake.write_partition(unique, lake.TRACKS, SNAPSHOT_DT, lake_root)
    lake.write_partition(
        deduplicate(resolutions, SNAPSHOT_DT), lake.RESOLUTIONS, SNAPSHOT_DT, lake_root
    )

    first = load_lake(db_path, lake_root)
    second = load_lake(db_path, lake_root)
    assert first == second
