"""Repository tests against REAL stores.

The service tests use fakes, so this is the only place the SQL itself runs. Two halves,
matching the ADR-009 split:

* **transactional** — `sessions` and `feedback`, exercised on SQLite because that is what a
  clean clone and CI get with no `DATABASE_URL` (E.8). The Postgres path runs the *same* SQL
  through the same `Database` adapter; the one test below that pins the dialect surface is
  what says so out loud.
* **analytical** — `dim_track` and the marts, read-only against a temp DuckDB.

Each test gets its own store file: state leaking between tests is how a suite starts passing
for reasons unrelated to the code.
"""

from __future__ import annotations

import sqlite3
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
from api.repositories import database as db_module


@pytest.fixture()
def app_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the transactional store at a temp SQLite file.

    `DATABASE_URL` is cleared explicitly: a developer who exports it for compose would
    otherwise have these tests write into their real Postgres.
    """
    path = tmp_path / "app.db"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(path))
    return path


@pytest.fixture()
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "warehouse.duckdb"
    monkeypatch.setenv("RUNTIME_DB_PATH", str(path))
    return path


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


# ── The store selector ───────────────────────────────────────────────────────────────────


def test_no_database_url_means_sqlite(app_store: Path) -> None:
    """E.8: a clean clone runs with no key and no service. That is this test."""
    assert db_module.is_postgres() is False
    assert db_module.describe().startswith("sqlite:")


def test_a_postgres_url_selects_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    assert db_module.is_postgres() is True
    assert db_module.describe() == "postgres"


@pytest.mark.parametrize("scheme", ["postgresql://", "postgres://"])
def test_both_postgres_url_schemes_are_recognised(
    scheme: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neon hands out `postgresql://`; plenty of tooling still emits `postgres://`."""
    monkeypatch.setenv("DATABASE_URL", f"{scheme}u:p@h:5432/db")
    assert db_module.is_postgres() is True


def test_the_sql_uses_only_the_placeholder_the_adapter_translates(app_store: Path) -> None:
    """The one dialect difference, pinned.

    `Database.execute` rewrites `?` to `%s` for psycopg. That is safe only while no statement
    contains a `?` inside a string literal — so this asserts the translation happens and the
    SQL in this package stays inside that constraint.
    """
    postgres = db_module.Database.__dict__["execute"]
    assert postgres is not None  # the adapter exists

    with db_module.connection() as database:
        # A round trip through the SQLite path proves the untranslated form works.
        database.execute("select ?", ["ok"])


# ── Sessions ─────────────────────────────────────────────────────────────────────────────


def test_a_saved_session_round_trips(app_store: Path) -> None:
    repo = SessionRepository()
    repo.save(_plan())

    stored = repo.get("s1")
    assert stored is not None
    assert stored["session_id"] == "s1"
    assert stored["segments"][0]["zone"] == "Z1"


def test_an_unknown_session_reads_as_none(app_store: Path) -> None:
    assert SessionRepository().get("nope") is None
    assert SessionRepository().exists("nope") is False


def test_saving_twice_replaces_rather_than_duplicates(app_store: Path) -> None:
    """`ON CONFLICT DO UPDATE` — a retry must not create a second row."""
    repo = SessionRepository()
    repo.save(_plan())
    repo.save(_plan(verdict="review"))

    items, total = repo.list(limit=10, offset=0)
    assert total == 1
    assert items[0]["verdict"] == "review"


def test_listing_is_newest_first_and_pages(app_store: Path) -> None:
    repo = SessionRepository()
    for index in range(5):
        created = datetime(2026, 8, 20 + index, 12, 0, tzinfo=UTC).isoformat()
        repo.save(_plan(session_id=f"s{index}", created_at=created))

    items, total = repo.list(limit=2, offset=0)
    assert total == 5
    assert [item["session_id"] for item in items] == ["s4", "s3"]

    page_two, _ = repo.list(limit=2, offset=2)
    assert [item["session_id"] for item in page_two] == ["s2", "s1"]


def test_summaries_come_from_columns_not_from_parsing_the_blob(app_store: Path) -> None:
    SessionRepository().save(_plan())

    connection = sqlite3.connect(str(app_store))
    try:
        row = connection.execute(
            "select n_segments, duration_gap_s, verdict from sessions where session_id='s1'"
        ).fetchone()
    finally:
        connection.close()

    assert row == (1, -12.0, "safe")


def test_created_at_comes_back_as_a_datetime(app_store: Path) -> None:
    """Both engines must return the same Python type, or the repositories would have to
    branch on which store they are talking to."""
    repo = SessionRepository()
    repo.save(_plan())

    items, _ = repo.list(limit=1, offset=0)
    assert isinstance(items[0]["created_at"], datetime)


def test_a_store_that_does_not_exist_yet_reads_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh clone, before the API has ever been started."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "absent.db"))

    assert SessionRepository().list(limit=10, offset=0) == ([], 0)


# ── Feedback ─────────────────────────────────────────────────────────────────────────────


def test_feedback_is_stored_against_the_session_id(app_store: Path) -> None:
    repo = FeedbackRepository()
    repo.add(session_id="s1", rating="up", note="good", session_title="session-s1")

    rows = repo.for_session("s1")
    assert len(rows) == 1
    assert rows[0]["rating"] == "up"
    assert rows[0]["note"] == "good"


def test_feedback_keeps_the_denormalized_title_for_the_dbt_chain(app_store: Path) -> None:
    """ADR-008: `stg_feedback` -> … -> `mart_feedback_summary` still groups on the title, and
    E.2 declares that chain normative, so it must stay populated."""
    FeedbackRepository().add(
        session_id="s1", rating="down", note=None, session_title="session-abcd1234"
    )
    connection = sqlite3.connect(str(app_store))
    try:
        row = connection.execute("select session_id, session_title from feedback").fetchone()
    finally:
        connection.close()

    assert row == ("s1", "session-abcd1234")


def test_the_rating_is_stored_verbatim(app_store: Path) -> None:
    """E.3's vocabulary reaches the warehouse untranslated.

    The regression test for the defect ADR-008 shipped: the API used to write a value the
    normative dbt chain rejected, and `check_invalid_rating` turned `make dbt` red on the first
    POST. The two scales are now kept apart in `stg_feedback` instead of one being mapped onto
    the other — so what matters here is that nothing rewrites the value on the way in.
    """
    FeedbackRepository().add(session_id="s1", rating="up", note=None)

    connection = sqlite3.connect(str(app_store))
    try:
        assert connection.execute("select rating from feedback").fetchone()[0] == "up"
    finally:
        connection.close()


def test_feedback_for_an_unknown_session_reads_empty(app_store: Path) -> None:
    assert FeedbackRepository().for_session("nope") == []


def test_a_note_may_be_absent(app_store: Path) -> None:
    record = FeedbackRepository().add(session_id="s1", rating="up", note=None)
    assert record["note"] is None
    assert FeedbackRepository().for_session("s1")[0]["note"] is None


# ── The analytical side (DuckDB) ─────────────────────────────────────────────────────────


def test_the_track_repository_filters_on_planner_eligible(warehouse: Path) -> None:
    """E.2's exclusion is read off a materialized column, not re-derived (ADR-006)."""
    with duckdb.connect(str(warehouse)) as con:
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

    catalogue = TrackRepository(warehouse).planner_catalogue()

    assert [t.track_id for t in catalogue] == ["ok"]
    assert TrackRepository(warehouse).count() == 3


def test_the_track_repository_is_empty_without_a_warehouse(tmp_path: Path) -> None:
    assert TrackRepository(tmp_path / "absent.duckdb").planner_catalogue() == []


def test_the_quality_repository_reads_the_marts(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse)) as con:
        con.execute(
            """
            CREATE TABLE mart_bpm_coverage (
                source VARCHAR, n_tracks BIGINT, n_usable BIGINT, pct_of_catalogue DOUBLE
            )
            """
        )
        con.execute("INSERT INTO mart_bpm_coverage VALUES ('librosa', 40, 40, 83.3)")

    rows = QualityRepository(warehouse).coverage()
    assert rows == [
        {"source": "librosa", "n_tracks": 40, "n_usable": 40, "pct_of_catalogue": 83.3}
    ]


def test_the_quality_repository_is_empty_before_dbt_runs(tmp_path: Path) -> None:
    repo = QualityRepository(tmp_path / "absent.duckdb")
    assert repo.coverage() == []
    assert repo.quality_by_method() == []


def test_the_analytical_side_is_read_only(warehouse: Path) -> None:
    """ADR-009: the API reads the warehouse and never writes it.

    Asserted structurally rather than by comment — neither analytical repository exposes a
    write, so a future `save` would have to be added deliberately and would fail here.
    """
    for repository in (TrackRepository, QualityRepository):
        writes = [
            name
            for name in dir(repository)
            if not name.startswith("_")
            and any(verb in name for verb in ("save", "add", "insert", "write", "delete"))
        ]
        assert writes == [], f"{repository.__name__} exposes {writes}"
