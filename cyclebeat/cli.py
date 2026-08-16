"""The Airflow-free CLI. `make ingest` runs this; the DAGs call the same functions.

§15's phase-2 exit criterion is `make ingest && make dbt` **from cold, without Airflow** —
so every stage has to be reachable without a scheduler. The DAGs in `dags/` are thin
wrappers over these same calls, which is what keeps business logic out of `dags/` (E.5).

Default mode is DEMO (E.8): no key, no network, no audio. `--live` is opt-in and is the
only path that costs anything.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cyclebeat import lake
from cyclebeat.demo import build_demo_batch
from cyclebeat.models import RawResolution, RawTrack
from cyclebeat.resolve import confidence_distribution, cross_validate, deduplicate
from cyclebeat.warehouse import load_lake

SPIKE_CACHE = Path("data") / "spike" / ".cache"


def _write_batch(
    tracks: list[RawTrack], resolutions: list[RawResolution], dt: date, root: Path | None
) -> tuple[int, int]:
    """Write one day's partitions. Returns the counts actually written, after dedup.

    Tracks are deduplicated on track_id alone (the `dim_track` grain) and resolutions on
    `track_id + source`; the partition path supplies the `dt` third of the E.5 key. The
    phase-1 snapshot really does contain a duplicate — Billie Jean was measured in both the
    `mainstream` and `mixed` sets — so this is exercised, not theoretical.
    """
    unique_tracks = list({track.track_id: track for track in tracks}.values())
    unique_resolutions = deduplicate(resolutions, dt)
    lake.write_partition(unique_tracks, lake.TRACKS, dt, root)
    lake.write_partition(unique_resolutions, lake.RESOLUTIONS, dt, root)
    return len(unique_tracks), len(unique_resolutions)


def cmd_ingest(args: argparse.Namespace) -> int:
    """Extract into the lake. Demo by default, `--live` hits Deezer."""
    root = Path(args.lake) if args.lake else None

    if args.live:
        from cyclebeat.http import PacedSession
        from cyclebeat.sources import deezer

        session = PacedSession(SPIKE_CACHE)
        tracks, resolutions = deezer.extract_chart(session, args.limit)
        dt = datetime.now(UTC).date()
        print(f"live: {session.calls} HTTP calls, {session.cache_hits} cache hits")
    else:
        from cyclebeat.demo import SNAPSHOT_DT

        tracks, resolutions = build_demo_batch()
        dt = SNAPSHOT_DT

    if args.csv:
        from cyclebeat.sources.csv_source import read_csv

        csv_tracks, csv_resolutions = read_csv(Path(args.csv))
        tracks += csv_tracks
        resolutions += csv_resolutions

    n_tracks, n_resolutions = _write_batch(tracks, resolutions, dt, root)
    print(f"lake dt={dt}: {n_tracks} tracks, {n_resolutions} resolutions")
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    """Run librosa over previews that have no librosa opinion yet. Needs --extra audio."""
    root = Path(args.lake) if args.lake else None
    rows = lake.read_dataset(lake.TRACKS, root)
    existing = {
        (str(r["track_id"]), str(r["source"]))
        for r in lake.read_dataset(lake.RESOLUTIONS, root)
    }

    from cyclebeat.http import PacedSession
    from cyclebeat.resolve import resolve_track_bpm

    session = PacedSession(SPIKE_CACHE)
    produced: list[RawResolution] = []
    for row in rows:
        if (str(row["track_id"]), "librosa") in existing or not row.get("preview_url"):
            continue
        track = RawTrack(**{k: v for k, v in row.items() if k != "dt"})
        resolution = resolve_track_bpm(session, track)
        if resolution is not None:
            produced.append(resolution)

    if produced:
        dt = datetime.now(UTC).date()
        lake.write_partition(deduplicate(produced, dt), lake.RESOLUTIONS, dt, root)
    print(f"resolved {len(produced)} tracks with librosa")
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    """Lake -> DuckDB, the table layer dbt reads."""
    root = Path(args.lake) if args.lake else None
    counts = load_lake(Path(args.db) if args.db else None, root)
    for table, count in counts.items():
        print(f"{table}: {count} rows")
    return 0


def cmd_confidence_report(args: argparse.Namespace) -> int:
    """The measured confidence distribution — phase 2's exit criterion."""
    root = Path(args.lake) if args.lake else None
    tracks = lake.read_dataset(lake.TRACKS, root)
    resolutions = lake.read_dataset(lake.RESOLUTIONS, root)
    resolved = cross_validate(resolutions, [str(t["track_id"]) for t in tracks])

    total = len(resolved)
    if not total:
        print("no tracks in the lake - run `make ingest` first", file=sys.stderr)
        return 1

    print(f"confidence distribution over {total} tracks (E.2 + ADR-006)\n")
    for method, count in sorted(
        confidence_distribution(resolved).items(), key=lambda kv: -kv[1]
    ):
        print(f"  {method:<20} {count:>4}  {count / total:>6.1%}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cyclebeat", description=__doc__)
    parser.add_argument("--lake", help="lake root (default: ./lake)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="extract into the lake")
    ingest.add_argument("--live", action="store_true", help="hit Deezer instead of the snapshot")
    ingest.add_argument("--limit", type=int, default=30)
    ingest.add_argument("--csv", help="also import a manual CSV playlist")
    ingest.set_defaults(func=cmd_ingest)

    resolve_cmd = subparsers.add_parser("resolve", help="librosa over unresolved previews")
    resolve_cmd.set_defaults(func=cmd_resolve)

    load = subparsers.add_parser("load", help="lake -> DuckDB")
    load.add_argument("--db", help="DuckDB path (default: RUNTIME_DB_PATH)")
    load.set_defaults(func=cmd_load)

    report = subparsers.add_parser("confidence-report", help="measured E.2 distribution")
    report.set_defaults(func=cmd_confidence_report)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
