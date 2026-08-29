"""Data-quality reads (§7 — logic layer).

The only real logic here is the aggregation E.3 asks for: `/v1/quality/summary` is specified
as a single record while `mart_data_quality` has one row per `confidence_method`. Summing
happens here rather than in SQL so the mart keeps its own honest grain and the endpoint keeps
the shape the contract promises.
"""

from __future__ import annotations

from api.repositories import QualityRepository
from api.schemas import CoverageRow, QualitySummary


class QualityService:
    def __init__(self, quality: QualityRepository) -> None:
        self._quality = quality

    def coverage(self) -> list[CoverageRow]:
        return [CoverageRow.model_validate(row) for row in self._quality.coverage()]

    def summary(self) -> QualitySummary:
        rows = self._quality.quality_by_method()
        if not rows:
            # A clean clone that has not run `make dbt` yet. Zeros beat a 500 with a DuckDB
            # error in the body.
            return QualitySummary(
                n_tracks=0,
                n_with_bpm=0,
                pct_with_bpm=0.0,
                n_flagged_review=0,
                pct_flagged_review=0.0,
                avg_confidence=None,
                by_method={},
            )

        n_tracks = sum(row["n_tracks"] for row in rows)
        n_with_bpm = sum(row["n_with_bpm"] for row in rows)
        n_review = sum(row["n_flagged_review"] for row in rows)

        # Weighted by track count, not a mean of the per-method means -- those buckets are
        # very different sizes (ADR-006 measured single_source at 56 % of the catalogue), so
        # an unweighted average would overstate the rare methods.
        weighted = [
            (row["avg_confidence"], row["n_tracks"])
            for row in rows
            if row["avg_confidence"] is not None and row["n_tracks"]
        ]
        total_weight = sum(weight for _, weight in weighted)
        avg_confidence = (
            sum(value * weight for value, weight in weighted) / total_weight
            if total_weight
            else None
        )

        return QualitySummary(
            n_tracks=n_tracks,
            n_with_bpm=n_with_bpm,
            pct_with_bpm=_pct(n_with_bpm, n_tracks),
            n_flagged_review=n_review,
            pct_flagged_review=_pct(n_review, n_tracks),
            avg_confidence=None if avg_confidence is None else round(avg_confidence, 4),
            by_method={row["confidence_method"]: row["n_tracks"] for row in rows},
        )


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0
