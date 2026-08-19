"""dag_ingest — [extract_deezer, extract_csv] -> write_lake_parquet (E.5).

ADR-005 removed the third branch, `extract_jamendo`: the Creative-Commons catalogue was
dropped, so Deezer plus the manual CSV are the only sources to extract.

**No business logic lives here.** Every task body is a call into `cyclebeat/`, which is what
makes the same pipeline runnable from `make ingest` without a scheduler. Retries (3, with
exponential backoff) are set on the extraction tasks only, per E.5 — a lake write that fails
is a bug to fix, not a flake to retry.
"""

from __future__ import annotations

import os

import pendulum
from airflow.sdk import Asset, dag, task

from cyclebeat import lake
from cyclebeat.resolve import deduplicate

LAKE_TRACKS = Asset(lake.ASSET_TRACKS)

DEMO_MODE = os.environ.get("CYCLEBEAT_DEMO", "1") != "0"
CSV_PLAYLIST = os.environ.get("CYCLEBEAT_CSV", "")

EXTRACT_ARGS = {
    "retries": 3,
    "retry_exponential_backoff": True,
    "retry_delay": pendulum.duration(seconds=30),
}


@dag(
    dag_id="dag_ingest",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    tags=["cyclebeat", "phase-2", "ingest"],
    # DuckDB is single-writer by design (V3 §, risk table: "fichier, pas de concurrence"),
    # and the lake partitions are full-replaced rather than appended. Two runs of the same
    # DAG overlapping therefore corrupt or abort each other -- unpausing a DAG creates the
    # scheduled run, and one click on "Trigger" then puts a second run alongside it.
    max_active_runs=1,
    doc_md=__doc__,
)
def dag_ingest() -> None:
    @task(task_id="extract_deezer", **EXTRACT_ARGS)
    def extract_deezer() -> dict[str, list[dict]]:
        """Deezer catalogue + per-track bpm. DEMO_MODE reads the committed snapshot (E.8)."""
        if DEMO_MODE:
            from cyclebeat.demo import build_demo_batch

            tracks, resolutions = build_demo_batch()
        else:
            from cyclebeat.cli import SPIKE_CACHE
            from cyclebeat.http import PacedSession
            from cyclebeat.sources import deezer

            tracks, resolutions = deezer.extract_chart(PacedSession(SPIKE_CACHE))
        return {
            "tracks": [t.model_dump(mode="json") for t in tracks],
            "resolutions": [r.model_dump(mode="json") for r in resolutions],
        }

    @task(task_id="extract_csv", **EXTRACT_ARGS)
    def extract_csv() -> dict[str, list[dict]]:
        """The ADR-005 manual floor. No CSV configured is a valid state, not an error."""
        if not CSV_PLAYLIST:
            return {"tracks": [], "resolutions": []}

        from pathlib import Path

        from cyclebeat.sources.csv_source import read_csv

        tracks, resolutions = read_csv(Path(CSV_PLAYLIST))
        return {
            "tracks": [t.model_dump(mode="json") for t in tracks],
            "resolutions": [r.model_dump(mode="json") for r in resolutions],
        }

    # Publishing the asset here rather than on the extract tasks: the lake is only
    # current once the partitions are actually written.
    @task(task_id="write_lake_parquet", outlets=[LAKE_TRACKS])
    def write_lake_parquet(*batches: dict[str, list[dict]]) -> str:
        """Partition by ingestion date: lake/raw/tracks/dt=YYYY-MM-DD/ (E.5)."""
        from cyclebeat.models import RawResolution, RawTrack

        tracks = [RawTrack(**row) for batch in batches for row in batch["tracks"]]
        resolutions = [
            RawResolution(**row) for batch in batches for row in batch["resolutions"]
        ]
        if not tracks:
            return "nothing to write"

        dt = max(track.ingested_at for track in tracks).date()
        unique = list({track.track_id: track for track in tracks}.values())
        lake.write_partition(unique, lake.TRACKS, dt)
        lake.write_partition(deduplicate(resolutions, dt), lake.RESOLUTIONS, dt)
        return f"dt={dt}: {len(unique)} tracks"

    write_lake_parquet(extract_deezer(), extract_csv())


dag_ingest()
