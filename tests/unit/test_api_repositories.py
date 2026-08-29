"""Repository tests against a REAL DuckDB in a temp directory.

The service tests use fakes, so this is the only place the SQL itself is exercised. Each test
gets its own database file: DuckDB takes one writer, and sharing one across tests would make
failures depend on execution order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from api.repositories import (
    FeedbackRepository,
    QualityRepository,
    SessionRepository,
    TrackRepository,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_runtime.duckdb"


def _plan(session_id: str = "s1", **overrides: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "session_id": session_id,
        "level": "advanced",
        "goal": "intervals",
        "duration_min": 45,
        "verdict": "safe",
        "segments": [
            {
                "order": 0,
                "track": {
                    "track_id": "t1", "title": "T", "artist": "A", "duration_s": 240.0,
                    "bpm_effective": 95.0, "zone": "Z1", "confidence": 0.6,
                    "preview_url": None,
                },
                "zone": "Z1",
                "role": "warmup",
                "duration_s": 240.0,
                "coaching": None,
            }
        ],
        "excluded": [],
        "duration_gap_s": -12.0,
        "warnings": [],
        "created_at": datetime.now(UTC).isoformat(),
    }
    plan.update(overrides)
    return plan


# ── Sessions ─────────────────────────────────────────────────────────────────────────────


def test_a_saved_session_round_trips(db_path: Path) -> None:
    repo = SessionRepository(db_path)
    repo.save(_plan())

    stored = repo.get("s1")
    assert stored is not None
    assert stored["session_id"] == "s1"
    assert stored["segments"][0]["zone"] == "Z1"


def test_an_unknown_session_reads_as_none(db_path: Path) -> None:
    assert SessionRepository(db_path).get("nope") is None
    assert SessionRepository(db_path).exists("nope") is False


def test_saving_twice_replaces_rather_than_duplicates(db_path: Path) -> None:
    """`session_id` is the primary key; a retry must not create a second row."""
    repo = SessionRepository(db_path)
    repo.save(_plan())
    repo.save(_plan(verdict="review"))

    items, total = repo.list(limit=10, offset=0)
    assert total == 1
    assert items[0]["verdict"] == "review"


def test_listing_is_newest_first_and_pages(db_path: Path) -> None:
    repo = SessionRepository(db_path)
    for index in range(5):
        created = datetime(2026, 8, 20 + index, 12, 0, tzinfo=UTC).isoformat()
        repo.save(_plan(session_id=f"s{index}", created_at=created))

    items, total = repo.list(limit=2, offset=0)
    assert total == 5
    assert [item["session_id"] for item in items] == ["s4", "s3"]

    page_two, _ = repo.list(limit=2, offset=2)
    assert [item["session_id"] for item in page_two] == ["s2", "s1"]


def test_summaries_come_from_columns_not_from_parsing_the_blob(db_path: Path) -> None:
    repo = SessionRepository(db_path)
    repo.save(_plan())

    with duckdb.connect(str(db_path), read_only=True) as con:
        row = con.execute(
            "select n_segments, duration_gap_s, verdict from fct_session where session_id='s1'"
        ).fetchone()

    assert row == (1, -12.0, "safe")


def test_reading_from_a_database_that_does_not_exist_yet(tmp_path: Path) -> None:
    """A fresh clone, before any ingest. Empty beats a 500."""
    repo = SessionRepository(tmp_path / "absent.duckdb")
    assert repo.list(limit=10, offset=0) == ([], 0)


# ── Feedback ─────────────────────────────────────────────────────────────────────────────


def test_feedback_is_stored_against_the_session_id(db_path: Path) -> None:
    repo = FeedbackRepository(db_path)
    repo.add(session_id="s1", rating="up", note="good", session_title="session-s1")

    rows = repo.for_session("s1")
    assert len(rows) == 1
    assert rows[0]["rating"] == "up"
    assert rows[0]["note"] == "good"


def test_feedback_keeps_the_denormalized_title_for_the_dbt_chain(db_path: Path) -> None:
    """ADR-008: `stg_feedback -> ... -> mart_feedback_summary` groups on session_title, and
    E.2 declares that chain normative, so it must stay populated."""
    FeedbackRepository(db_path).add(
        session_id="s1", rating="down", note=None, session_title="session-abcd1234"
    )
    with duckdb.connect(str(db_path), read_only=True) as con:
        row = con.execute("select session_id, session_title from feedback").fetchone()

    assert row == ("s1", "session-abcd1234")


def test_a_pre_existing_v1_feedback_table_is_migrated(db_path: Path) -> None:
    """The real upgrade path: a database that already holds the v1 shape.

    `CREATE TABLE IF NOT EXISTS` is a no-op there, so without the ALTER the new column would
    never appear and every insert would fail on a binder error. This is the regression test
    for exactly that — it was found by driving the endpoint, not by review.
    """
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            """
            CREATE TABLE feedback (
                session_title VARCHAR, rating VARCHAR, note VARCHAR, created_at TIMESTAMP
            )
            """
        )
        con.execute("INSERT INTO feedback VALUES ('legacy', 'up', 'old row', now())")

    FeedbackRepository(db_path).add(session_id="s1", rating="up", note="new row")

    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(
            "select session_id, session_title, note from feedback order by note"
        ).fetchall()

    # The v1 row survives with a NULL session_id, which is honest: it never had one.
    assert rows == [("s1", "", "new row"), (None, "legacy", "old row")]


def test_feedback_for_an_unknown_session_reads_empty(db_path: Path) -> None:
    assert FeedbackRepository(db_path).for_session("nope") == []


# ── Tracks and quality ───────────────────────────────────────────────────────────────────


def test_the_track_repository_filters_on_planner_eligible(db_path: Path) -> None:
    """E.2's exclusion is read off a materialized column, not re-derived (ADR-006)."""
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            """
            CREATE TABLE dim_track (
                track_id VARCHAR, title VARCHAR, artist VARCHAR, duration_s DOUBLE,
                bpm_effective DOUBLE, zone VARCHAR, confidence DOUBLE,
                preview_url VARCHAR, planner_eligible BOOLEAN
            )
            """
        )
        con.execute(
            """
            INSERT INTO dim_track VALUES
                ('ok',      'A', 'X', 240.0, 95.0, 'Z1', 0.6, NULL, true),
                ('no_bpm',  'B', 'Y', 240.0, NULL, NULL, NULL, NULL, false),
                ('zero_len','C', 'Z',   0.0, 95.0, 'Z1', 0.6, NULL, true)
            """
        )

    catalogue = TrackRepository(db_path).planner_catalogue()

    assert [t.track_id for t in catalogue] == ["ok"]
    assert TrackRepository(db_path).count() == 3


def test_the_track_repository_is_empty_without_a_warehouse(tmp_path: Path) -> None:
    assert TrackRepository(tmp_path / "absent.duckdb").planner_catalogue() == []


def test_the_quality_repository_reads_the_marts(db_path: Path) -> None:
    with duckdb.connect(str(db_path)) as con:
        con.execute(
            """
            CREATE TABLE mart_bpm_coverage (
                source VARCHAR, n_tracks BIGINT, n_usable BIGINT, pct_of_catalogue DOUBLE
            )
            """
        )
        con.execute("INSERT INTO mart_bpm_coverage VALUES ('librosa', 40, 40, 83.3)")

    rows = QualityRepository(db_path).coverage()
    assert rows == [
        {"source": "librosa", "n_tracks": 40, "n_usable": 40, "pct_of_catalogue": 83.3}
    ]


def test_the_quality_repository_is_empty_before_dbt_runs(tmp_path: Path) -> None:
    repo = QualityRepository(tmp_path / "absent.duckdb")
    assert repo.coverage() == []
    assert repo.quality_by_method() == []
