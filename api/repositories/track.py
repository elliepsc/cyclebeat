"""Reads the track catalogue the planner works from."""

from __future__ import annotations

from pathlib import Path

from api.repositories.connection import readable, table_exists
from cyclebeat.models import PlannerTrack


class TrackRepository:
    """`dim_track` -> `PlannerTrack`."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def planner_catalogue(self, limit: int | None = None) -> list[PlannerTrack]:
        """Every track the planner may consider.

        Filters on `planner_eligible`, the column phase 2 exposed for exactly this: E.2 says a
        track with no BPM is excluded from the planner, and reading a materialized flag means
        the rule is applied once, upstream, rather than re-derived here in SQL.

        Ordered by `track_id` — the planner is order-independent by construction (ADR-007),
        but a deterministic read makes a failure reproducible from the same database.
        """
        with readable(self._db_path) as con:
            if not table_exists(con, "dim_track"):
                return []
            sql = """
                select
                    track_id,
                    title,
                    artist,
                    duration_s,
                    bpm_effective,
                    zone,
                    confidence,
                    preview_url
                from dim_track
                where planner_eligible
                  and duration_s is not null
                  and duration_s > 0
                order by track_id
            """
            if limit is not None:
                sql += f" limit {int(limit)}"
            rows = con.execute(sql).fetchall()

        return [
            PlannerTrack(
                track_id=str(row[0]),
                title=str(row[1] or ""),
                artist=str(row[2] or ""),
                duration_s=float(row[3]),
                bpm_effective=None if row[4] is None else float(row[4]),
                zone=row[5],
                confidence=None if row[6] is None else float(row[6]),
                preview_url=row[7],
            )
            for row in rows
        ]

    def count(self) -> int:
        with readable(self._db_path) as con:
            if not table_exists(con, "dim_track"):
                return 0
            row = con.execute("select count(*) from dim_track").fetchone()
        return int(row[0]) if row else 0
