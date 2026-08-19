"""dag_resolve_bpm — read_unresolved -> resolve_multi_sources -> cross_validate ->
write_resolutions (E.5).

Idempotent on `track_id + source + dt`: re-running the same day replaces that partition
instead of appending, so a retried run never duplicates a resolution. That property is
asserted by `test_resolve_dag_idempotent_on_same_dt`.

`resolve_multi_sources` is the only expensive task — it downloads previews and runs librosa.
`cross_validate` is pure and offline, so the E.2 rule can be replayed after a contract change
without re-fetching a single byte of audio. In DEMO_MODE the expensive task is a no-op: the
committed snapshot already carries librosa's answers (E.8).
"""

from __future__ import annotations

import os

import pendulum
from airflow.sdk import Asset, dag, task

from cyclebeat import lake

LAKE_TRACKS = Asset(lake.ASSET_TRACKS)
LAKE_RESOLUTIONS = Asset(lake.ASSET_RESOLUTIONS)

DEMO_MODE = os.environ.get("CYCLEBEAT_DEMO", "1") != "0"


@dag(
    dag_id="dag_resolve_bpm",
    # Asset-driven, not clock-driven: this runs when dag_ingest has actually landed
    # the day's tracks, never three seconds before it. See dags/assets.py.
    schedule=[LAKE_TRACKS],
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    tags=["cyclebeat", "phase-2", "resolve"],
    # DuckDB is single-writer by design (V3 §, risk table: "fichier, pas de concurrence"),
    # and the lake partitions are full-replaced rather than appended. Two runs of the same
    # DAG overlapping therefore corrupt or abort each other -- unpausing a DAG creates the
    # scheduled run, and one click on "Trigger" then puts a second run alongside it.
    max_active_runs=1,
    doc_md=__doc__,
)
def dag_resolve_bpm() -> None:
    @task(task_id="read_unresolved")
    def read_unresolved() -> list[dict]:
        """Tracks with a preview but no librosa opinion yet."""
        resolved = {
            str(row["track_id"])
            for row in lake.read_dataset(lake.RESOLUTIONS)
            if str(row.get("source")) == "librosa" and row.get("bpm_raw") is not None
        }
        return [
            {k: v for k, v in row.items() if k != "dt"}
            for row in lake.read_dataset(lake.TRACKS)
            if row.get("preview_url") and str(row["track_id"]) not in resolved
        ]

    @task(
        task_id="resolve_multi_sources",
        retries=3,
        retry_exponential_backoff=True,
        retry_delay=pendulum.duration(seconds=30),
    )
    def resolve_multi_sources(pending: list[dict]) -> list[dict]:
        """librosa on the Deezer preview — the ADR-005 backbone. Needs the `audio` extra."""
        if DEMO_MODE or not pending:
            return []

        from cyclebeat.cli import SPIKE_CACHE
        from cyclebeat.http import PacedSession
        from cyclebeat.models import RawTrack
        from cyclebeat.resolve import resolve_track_bpm

        session = PacedSession(SPIKE_CACHE)
        produced = []
        for row in pending:
            resolution = resolve_track_bpm(session, RawTrack(**row))
            if resolution is not None:
                produced.append(resolution.model_dump(mode="json"))
        return produced

    @task(task_id="cross_validate")
    def cross_validate_task(produced: list[dict]) -> dict[str, int]:
        """Apply E.2 + ADR-006. Pure, offline, replayable."""
        from cyclebeat.resolve import confidence_distribution, cross_validate

        existing = lake.read_dataset(lake.RESOLUTIONS)
        track_ids = [str(row["track_id"]) for row in lake.read_dataset(lake.TRACKS)]
        resolved = cross_validate(list(existing) + list(produced), track_ids)
        return confidence_distribution(resolved)

    @task(task_id="write_resolutions", outlets=[LAKE_RESOLUTIONS])
    def write_resolutions(produced: list[dict], distribution: dict[str, int]) -> str:
        """Write the new opinions, keyed on track_id+source+dt (E.5 idempotency)."""
        from cyclebeat.models import RawResolution
        from cyclebeat.resolve import deduplicate

        if produced:
            rows = [RawResolution(**row) for row in produced]
            dt = max(row.resolved_at for row in rows).date()
            lake.write_partition(deduplicate(rows, dt), lake.RESOLUTIONS, dt)
        return ", ".join(f"{method}={count}" for method, count in sorted(distribution.items()))

    pending = read_unresolved()
    produced = resolve_multi_sources(pending)
    write_resolutions(produced, cross_validate_task(produced))


dag_resolve_bpm()
