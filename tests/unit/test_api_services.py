"""Service-layer tests against FAKE repositories (§7).

The point of the layering is that this file needs no database, no HTTP and no dbt run. If a
test here ever has to build a DuckDB, the service has grown a dependency it should not have.

Repository behaviour against a real database is covered separately, in
`test_api_repositories.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from api.errors import NotFoundError, UnprocessableError
from api.schemas import FeedbackRequest, GenerateSessionRequest
from api.services import QualityService, SessionService
from catalogue_fixtures import build_catalogue
from cyclebeat.models import PlannerTrack

# Deep enough in every zone for the planner to build a real 45-minute session.
CATALOGUE = build_catalogue(
    [
        (95, 240), (98, 200), (92, 190), (88, 230), (96, 210), (94, 220),
        (105, 210), (110, 220), (112, 200), (108, 215), (102, 205), (106, 195),
        (120, 215), (125, 230), (128, 205), (122, 210), (118, 220), (124, 200),
        (135, 200), (140, 195), (138, 210), (133, 205), (142, 200),
        (150, 190), (155, 205), (160, 200), (148, 195),
    ]
)


# ── Fakes ────────────────────────────────────────────────────────────────────────────────


class FakeTrackRepository:
    def __init__(self, tracks: list[PlannerTrack] | None = None) -> None:
        self._tracks = CATALOGUE if tracks is None else tracks

    def planner_catalogue(self, limit: int | None = None) -> list[PlannerTrack]:
        return list(self._tracks)

    def count(self) -> int:
        return len(self._tracks)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.saved: dict[str, dict[str, Any]] = {}

    def save(self, plan: dict[str, Any]) -> None:
        self.saved[plan["session_id"]] = plan

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self.saved.get(session_id)

    def exists(self, session_id: str) -> bool:
        return session_id in self.saved

    def list(self, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        rows = [
            {
                "session_id": p["session_id"],
                "level": p["level"],
                "goal": p["goal"],
                "duration_min": p["duration_min"],
                "verdict": p["verdict"],
                "n_segments": len(p["segments"]),
                "duration_gap_s": p["duration_gap_s"],
                "created_at": p["created_at"],
            }
            for p in self.saved.values()
        ]
        return rows[offset : offset + limit], len(rows)


class FakeFeedbackRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self, session_id: str, rating: str, note: str | None, session_title: str = ""
    ) -> dict[str, Any]:
        record = {
            "session_id": session_id,
            "rating": rating,
            "note": note,
            "created_at": datetime.now(UTC),
            "session_title": session_title,
        }
        self.rows.append(record)
        return record

    def for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["session_id"] == session_id]


class FakeQualityRepository:
    def __init__(
        self,
        coverage: list[dict[str, Any]] | None = None,
        by_method: list[dict[str, Any]] | None = None,
    ) -> None:
        self._coverage = coverage if coverage is not None else []
        self._by_method = by_method if by_method is not None else []

    def coverage(self) -> list[dict[str, Any]]:
        return self._coverage

    def quality_by_method(self) -> list[dict[str, Any]]:
        return self._by_method


@pytest.fixture()
def service() -> SessionService:
    return SessionService(
        tracks=FakeTrackRepository(),  # type: ignore[arg-type]
        sessions=FakeSessionRepository(),  # type: ignore[arg-type]
        feedback=FakeFeedbackRepository(),  # type: ignore[arg-type]
    )


def request(**overrides: Any) -> GenerateSessionRequest:
    body: dict[str, Any] = {
        "source": {"type": "demo", "value": ""},
        "level": "advanced",
        "goal": "intervals",
        "duration_min": 45,
    }
    body.update(overrides)
    return GenerateSessionRequest.model_validate(body)


# ── Generate ─────────────────────────────────────────────────────────────────────────────


def test_generate_returns_a_planned_session(service: SessionService) -> None:
    plan = service.generate(request())

    assert plan.verdict == "safe"
    assert plan.segments
    assert plan.session_id


def test_generate_persists_the_session(service: SessionService) -> None:
    plan = service.generate(request())
    assert service.get(plan.session_id).session_id == plan.session_id


def test_each_generate_gets_a_fresh_id(service: SessionService) -> None:
    assert service.generate(request()).session_id != service.generate(request()).session_id


def test_the_wire_session_carries_the_engine_verdict(service: SessionService) -> None:
    """The service maps; it does not judge. The verdict comes from the evaluator."""
    from cyclebeat.evaluator import evaluate
    from cyclebeat.models import SessionParams
    from cyclebeat.planner import plan_session

    plan = service.generate(request())
    params = SessionParams(level="advanced", goal="intervals", duration_min=45)
    expected = evaluate(plan_session(CATALOGUE, params), params)

    assert plan.verdict == expected.verdict


def test_segments_keep_the_planner_zones_and_roles(service: SessionService) -> None:
    from cyclebeat.models import SessionParams
    from cyclebeat.planner import plan_session

    plan = service.generate(request())
    params = SessionParams(level="advanced", goal="intervals", duration_min=45)
    domain = plan_session(CATALOGUE, params)

    assert [s.zone for s in plan.segments] == [s.zone for s in domain.segments]
    assert [s.role for s in plan.segments] == [s.role for s in domain.segments]


def test_coaching_is_absent_until_phase_6(service: SessionService) -> None:
    """Contracted as nullable so phase 6 fills it without a breaking change."""
    assert all(segment.coaching is None for segment in service.generate(request()).segments)


def test_warnings_merge_the_planner_and_the_evaluator(service: SessionService) -> None:
    """A thin catalogue cannot fill the target; the caller should hear about it."""
    thin = SessionService(
        tracks=FakeTrackRepository(build_catalogue([(95, 240), (105, 210), (95, 200)])),  # type: ignore[arg-type]
        sessions=FakeSessionRepository(),  # type: ignore[arg-type]
        feedback=FakeFeedbackRepository(),  # type: ignore[arg-type]
    )
    plan = thin.generate(request(duration_min=60))

    assert any(w.startswith("duration_accuracy") for w in plan.warnings)


def test_an_unplannable_catalogue_is_a_422_carrying_the_planner_reasons() -> None:
    """E.3 routes "no valid session possible" here, with structured reasons."""
    no_z1 = SessionService(
        tracks=FakeTrackRepository(build_catalogue([(120, 210), (125, 220), (128, 200)])),  # type: ignore[arg-type]
        sessions=FakeSessionRepository(),  # type: ignore[arg-type]
        feedback=FakeFeedbackRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(UnprocessableError) as raised:
        no_z1.generate(request())

    assert raised.value.status == 422
    assert "no_cooldown_candidate" in raised.value.reasons


def test_an_empty_catalogue_is_a_422() -> None:
    empty = SessionService(
        tracks=FakeTrackRepository([]),  # type: ignore[arg-type]
        sessions=FakeSessionRepository(),  # type: ignore[arg-type]
        feedback=FakeFeedbackRepository(),  # type: ignore[arg-type]
    )
    with pytest.raises(UnprocessableError) as raised:
        empty.generate(request())
    assert "empty_catalogue" in raised.value.reasons


def test_a_deezer_url_is_refused_in_demo_mode(
    service: SessionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E.8: no API quota is consumed in demo or in CI."""
    monkeypatch.setenv("CYCLEBEAT_DEMO", "1")
    with pytest.raises(UnprocessableError) as raised:
        service.generate(request(source={"type": "deezer_url", "value": "http://x"}))
    assert "source_unavailable_in_demo_mode" in raised.value.reasons


def test_a_csv_source_without_a_path_is_refused(service: SessionService) -> None:
    with pytest.raises(UnprocessableError) as raised:
        service.generate(request(source={"type": "csv", "value": ""}))
    assert "missing_csv_path" in raised.value.reasons


def test_a_missing_csv_is_a_422_not_a_crash(service: SessionService) -> None:
    with pytest.raises(UnprocessableError) as raised:
        service.generate(request(source={"type": "csv", "value": "nope/missing.csv"}))
    assert "csv_not_found" in raised.value.reasons


def test_a_real_csv_is_planned(service: SessionService) -> None:
    """The committed spike CSV — the `manual` E.2 source, resolved through e2 not trusted."""
    from pathlib import Path

    csv = Path("data/spike/playlist_mixed.csv")
    if not csv.exists():  # pragma: no cover - the fixture is committed
        pytest.fail(f"expected the committed CSV fixture at {csv}")

    with pytest.raises(UnprocessableError):
        # 5 tracks cannot fill 45 minutes with a warmup and a cooldown; the point is that it
        # refuses with a structured reason rather than raising a parse error.
        service.generate(request(source={"type": "csv", "value": str(csv)}))


# ── Replay, history, feedback ────────────────────────────────────────────────────────────


def test_getting_an_unknown_session_is_a_404(service: SessionService) -> None:
    with pytest.raises(NotFoundError) as raised:
        service.get("does-not-exist")
    assert raised.value.status == 404


def test_a_stored_session_round_trips(service: SessionService) -> None:
    plan = service.generate(request())
    replayed = service.get(plan.session_id)

    assert replayed.segments == plan.segments
    assert replayed.duration_gap_s == plan.duration_gap_s


def test_listing_pages(service: SessionService) -> None:
    for _ in range(3):
        service.generate(request())

    page = service.list(limit=2, offset=0)
    assert page.total == 3
    assert len(page.items) == 2
    assert page.limit == 2


def test_feedback_on_an_unknown_session_is_a_404(service: SessionService) -> None:
    """ADR-008: keying on session_id is what makes an orphan row impossible."""
    with pytest.raises(NotFoundError):
        service.add_feedback("nope", FeedbackRequest(rating="up"))


def test_feedback_is_recorded_against_the_session(service: SessionService) -> None:
    plan = service.generate(request())
    record = service.add_feedback(plan.session_id, FeedbackRequest(rating="up", note="good"))

    assert record.session_id == plan.session_id
    assert record.rating == "up"


# ── Quality ──────────────────────────────────────────────────────────────────────────────


def test_coverage_passes_the_mart_rows_through() -> None:
    rows = [{"source": "librosa", "n_tracks": 40, "n_usable": 40, "pct_of_catalogue": 83.3}]
    service = QualityService(FakeQualityRepository(coverage=rows))  # type: ignore[arg-type]

    assert [row.model_dump() for row in service.coverage()] == rows


def test_summary_aggregates_the_four_mart_rows_into_one_record() -> None:
    """E.3 specifies a single record; the mart's grain is confidence_method."""
    by_method = [
        {"confidence_method": "cross_validated", "n_tracks": 12, "pct_of_catalogue": 25.0,
         "avg_confidence": 0.9, "n_with_bpm": 12, "n_flagged_review": 0},
        {"confidence_method": "single_source", "n_tracks": 27, "pct_of_catalogue": 56.2,
         "avg_confidence": 0.6, "n_with_bpm": 27, "n_flagged_review": 0},
        {"confidence_method": "librosa_arbitrated", "n_tracks": 4, "pct_of_catalogue": 8.3,
         "avg_confidence": 0.6, "n_with_bpm": 4, "n_flagged_review": 0},
        {"confidence_method": "unknown", "n_tracks": 5, "pct_of_catalogue": 10.4,
         "avg_confidence": None, "n_with_bpm": 0, "n_flagged_review": 0},
    ]
    summary = QualityService(FakeQualityRepository(by_method=by_method)).summary()  # type: ignore[arg-type]

    assert summary.n_tracks == 48
    assert summary.n_with_bpm == 43
    assert summary.pct_with_bpm == pytest.approx(89.6, abs=0.1)
    assert summary.by_method["single_source"] == 27


def test_summary_weights_confidence_by_track_count() -> None:
    """An unweighted mean would overstate the rare methods — single_source is 56% of the
    catalogue (ADR-006) and must dominate the average accordingly."""
    by_method = [
        {"confidence_method": "cross_validated", "n_tracks": 10, "pct_of_catalogue": 10.0,
         "avg_confidence": 0.9, "n_with_bpm": 10, "n_flagged_review": 0},
        {"confidence_method": "single_source", "n_tracks": 90, "pct_of_catalogue": 90.0,
         "avg_confidence": 0.6, "n_with_bpm": 90, "n_flagged_review": 0},
    ]
    summary = QualityService(FakeQualityRepository(by_method=by_method)).summary()  # type: ignore[arg-type]

    # Weighted: (0.9*10 + 0.6*90)/100 = 0.63. Unweighted would be 0.75.
    assert summary.avg_confidence == pytest.approx(0.63)


def test_summary_on_an_unbuilt_warehouse_is_zeros_not_a_crash() -> None:
    """A clean clone that has not run `make dbt` yet."""
    summary = QualityService(FakeQualityRepository()).summary()  # type: ignore[arg-type]

    assert summary.n_tracks == 0
    assert summary.avg_confidence is None
    assert summary.by_method == {}
