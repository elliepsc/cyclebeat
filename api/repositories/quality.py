"""Reads the data-quality marts behind `/v1/quality/*`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.repositories.connection import readable, table_exists


class QualityRepository:
    """`mart_bpm_coverage` and `mart_data_quality`.

    Both are built by `make dbt`. Neither read re-derives anything: E.2 forbids variants, so
    the aggregation for `/v1/quality/summary` sums counts the marts already computed rather
    than recomputing confidence from `raw.resolutions`.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path

    def coverage(self) -> list[dict[str, Any]]:
        """Rows of `mart_bpm_coverage`, one per BPM source (E.3)."""
        with readable(self._db_path) as con:
            if not table_exists(con, "mart_bpm_coverage"):
                return []
            rows = con.execute(
                """
                select source, n_tracks, n_usable, pct_of_catalogue
                from mart_bpm_coverage
                order by source
                """
            ).fetchall()
        return [
            {
                "source": str(r[0]),
                "n_tracks": int(r[1]),
                "n_usable": int(r[2]),
                "pct_of_catalogue": float(r[3]) if r[3] is not None else 0.0,
            }
            for r in rows
        ]

    def quality_by_method(self) -> list[dict[str, Any]]:
        """Raw rows of `mart_data_quality` — grain is `confidence_method`.

        The service aggregates these into E.3's single summary record. Returning the mart's
        own grain here keeps the repository a reader and puts the shape decision in the layer
        that owns it.
        """
        with readable(self._db_path) as con:
            if not table_exists(con, "mart_data_quality"):
                return []
            rows = con.execute(
                """
                select
                    confidence_method,
                    n_tracks,
                    pct_of_catalogue,
                    avg_confidence,
                    n_with_bpm,
                    n_flagged_review
                from mart_data_quality
                order by confidence_method
                """
            ).fetchall()
        return [
            {
                "confidence_method": str(r[0]),
                "n_tracks": int(r[1]),
                "pct_of_catalogue": float(r[2]) if r[2] is not None else 0.0,
                "avg_confidence": None if r[3] is None else float(r[3]),
                "n_with_bpm": int(r[4]),
                "n_flagged_review": int(r[5]),
            }
            for r in rows
        ]
