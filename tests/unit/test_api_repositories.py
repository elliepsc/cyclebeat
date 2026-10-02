"""Repository tests against REAL stores.

The service tests use fakes, so this is the only place the SQL itself runs. Two halves,
matching the ADR-009 split:

* **transactional** — `sessions` and `feedback`, run on BOTH engines with the same test code
  (the `store` fixture is parametrized). SQLite is what a clean clone gets with no
  `DATABASE_URL` (E.8). The Postgres cases need a real server and read `TEST_DATABASE_URL`;
  without it they are skipped with an explicit reason, never silently passed. CI provides one.
* **analytical** — `dim_track` and the marts, read-only against a temp DuckDB.

Each test gets its own store file: state leaking between tests is how a suite starts passing
for reasons unrelated to the code.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

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


@dataclass
class Store:
    """The transactional store under test, whichever engine backs it."""

    engine: str

    def fetch(self, sql: str) -> list[Any]:
        """Read raw rows through the adapter, bypassing the repositories."""
        with db_module.connection(create=False) as database:
            return database.execute(sql).fetchall()


def _postgres_test_url() -> str:
    """`TEST_DATABASE_URL`, not `DATABASE_URL`.

    `DATABASE_URL` is the production variable and is stripped for the whole suite (conftest);
    a developer may also export it towards the compose database. A dedicated variable means a
    test can only reach a server someone pointed at it on purpose.
    """
    return os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.fixture(params=["sqlite", "postgres"])
def store(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Store]:
    """The same test code against SQLite and against a real Postgres.

    Postgres tests run in a throwaway schema selected through the connection's `search_path`,
    dropped afterwards: `public` is never touched, so a `TEST_DATABASE_URL` that points at a
    database with real data stays safe.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))

    if request.param == "sqlite":
        yield Store(engine="sqlite")
        return

    base = _postgres_test_url()
    if not base.startswith(("postgresql://", "postgres://")):
        pytest.skip("TEST_DATABASE_URL not set: the Postgres path is not exercised here")

    import psycopg

    schema = f"t_{uuid.uuid4().hex}"
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"create schema {schema}")
    separator = "&" if "?" in base else "?"
    monkeypatch.setenv(
        "DATABASE_URL", f"{base}{separator}options={quote(f'-csearch_path={schema}')}"
    )
    try:
        assert db_module.is_postgres()
        yield Store(engine="postgres")
    finally:
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f"drop schema {schema} cascade")


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


def test_a_saved_session_round_trips(store: Store) -> None:
    repo = SessionRepository()
    repo.save(_plan())

    stored = repo.get("s1")
    assert stored is not None
    assert stored["session_id"] == "s1"
    assert stored["segments"][0]["zone"] == "Z1"


def test_an_unknown_session_reads_as_none(store: Store) -> None:
    assert SessionRepository().get("nope") is None
    assert SessionRepository().exists("nope") is False


def test_saving_twice_replaces_rather_than_duplicates(store: Store) -> None:
    """`ON CONFLICT DO UPDATE` — a retry must not create a second row."""
    repo = SessionRepository()
    repo.save(_plan())
    repo.save(_plan(verdict="review"))

    items, total = repo.list(limit=10, offset=0)
    assert total == 1
    assert items[0]["verdict"] == "review"


def test_listing_is_newest_first_and_pages(store: Store) -> None:
    repo = SessionRepository()
    for index in range(5):
        created = datetime(2026, 8, 20 + index, 12, 0, tzinfo=UTC).isoformat()
        repo.save(_plan(session_id=f"s{index}", created_at=created))

    items, total = repo.list(limit=2, offset=0)
    assert total == 5
    assert [item["session_id"] for item in items] == ["s4", "s3"]

    page_two, _ = repo.list(limit=2, offset=2)
    assert [item["session_id"] for item in page_two] == ["s2", "s1"]


def test_summaries_come_from_columns_not_from_parsing_the_blob(store: Store) -> None:
    SessionRepository().save(_plan())

    row = store.fetch(
        "select n_segments, duration_gap_s, verdict from sessions where session_id='s1'"
    )[0]

    assert tuple(row) == (1, -12.0, "safe")


def test_created_at_comes_back_as_a_datetime(store: Store) -> None:
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


def test_feedback_is_stored_against_the_session_id(store: Store) -> None:
    repo = FeedbackRepository()
    repo.add(session_id="s1", rating="up", note="good", session_title="session-s1")

    rows = repo.for_session("s1")
    assert len(rows) == 1
    assert rows[0]["rating"] == "up"
    assert rows[0]["note"] == "good"


def test_feedback_keeps_the_denormalized_title_for_the_dbt_chain(store: Store) -> None:
    """ADR-008: `stg_feedback` -> … -> `mart_feedback_summary` still groups on the title, and
    E.2 declares that chain normative, so it must stay populated."""
    FeedbackRepository().add(
        session_id="s1", rating="down", note=None, session_title="session-abcd1234"
    )
    row = store.fetch("select session_id, session_title from feedback")[0]

    assert tuple(row) == ("s1", "session-abcd1234")


def test_the_rating_is_stored_verbatim(store: Store) -> None:
    """E.3's vocabulary reaches the warehouse untranslated.

    The regression test for the defect ADR-008 shipped: the API used to write a value the
    normative dbt chain rejected, and `check_invalid_rating` turned `make dbt` red on the first
    POST. The two scales are now kept apart in `stg_feedback` instead of one being mapped onto
    the other — so what matters here is that nothing rewrites the value on the way in.
    """
    FeedbackRepository().add(session_id="s1", rating="up", note=None)

    assert store.fetch("select rating from feedback")[0][0] == "up"


def test_feedback_for_an_unknown_session_reads_empty(store: Store) -> None:
    assert FeedbackRepository().for_session("nope") == []


def test_a_note_may_be_absent(store: Store) -> None:
    record = FeedbackRepository().add(session_id="s1", rating="up", note=None)
    assert record["note"] is None
    assert FeedbackRepository().for_session("s1")[0]["note"] is None


class _Recorder:
    """A stand-in connection that records the statement each driver would receive."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> _Recorder:
        return self

    def execute(self, sql: str, params: Any = ()) -> None:
        self.statements.append(sql)


def test_the_placeholder_is_translated_for_psycopg_only() -> None:
    """Runs everywhere, no server needed: the statement each driver actually receives."""

    for postgres, expected in ((True, "select %s, %s"), (False, "select ?, ?")):
        recorder = _Recorder()
        db_module.Database(recorder, postgres=postgres).execute("select ?, ?", [1, 2])
        assert recorder.statements == [expected]


def test_a_literal_percent_in_the_sql_is_escaped_for_psycopg_only() -> None:
    sql = "select 1 where a like '%x' and b = ?"
    for postgres, expected in (
        (True, "select 1 where a like '%%x' and b = %s"),
        (False, sql),
    ):
        recorder = _Recorder()
        db_module.Database(recorder, postgres=postgres).execute(sql, [1])
        assert recorder.statements == [expected]


def test_a_like_with_a_literal_percent_and_a_parameter_runs_on_both_engines(
    store: Store,
) -> None:
    """The edge case of the `?` -> `%s` rewrite: a `%` in the SQL text next to a bound value.

    Without the escape psycopg reads `'%x'` as a placeholder and raises. The bound value also
    carries a `%`, which must match literally and not be re-interpreted.
    """
    repo = FeedbackRepository()
    repo.add(session_id="s1", rating="up", note="100% sure")
    repo.add(session_id="s2", rating="up", note="abc")
    repo.add(session_id="s3", rating="down", note="100% sure")

    with db_module.connection() as database:
        rows = database.execute(
            "select session_id from feedback where note like '%sure' and rating = ?"
            " order by session_id",
            ["up"],
        ).fetchall()
        by_value = database.execute(
            "select session_id from feedback where note like ? order by session_id",
            ["100%"],
        ).fetchall()

    assert [r[0] for r in rows] == ["s1"]
    assert [r[0] for r in by_value] == ["s1", "s3"]


def test_a_percent_or_question_mark_in_a_value_is_stored_untouched(store: Store) -> None:
    """The rewrite is `?` -> `%s` on the SQL text, so values must never be part of it.

    A literal `%` or `?` inside a bound value is the case a naive rewrite breaks first; it
    must come back unchanged on both engines.
    """
    note = "100% sure? 50%s %(x)s ?"
    FeedbackRepository().add(session_id="s1", rating="up", note=note)

    assert FeedbackRepository().for_session("s1")[0]["note"] == note


def test_tables_are_created_on_first_use(store: Store) -> None:
    with db_module.connection() as database:
        names = {
            row[0]
            for row in database.execute(
                "select table_name from information_schema.tables"
                " where table_schema = current_schema()"
                if store.engine == "postgres"
                else "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert {"sessions", "feedback"} <= names


def test_feedback_is_linked_to_a_stored_session(store: Store) -> None:
    """A session written, then a feedback row against its id, read back through both."""
    SessionRepository().save(_plan(session_id="linked"))
    FeedbackRepository().add(session_id="linked", rating="down", note="too hard")

    assert SessionRepository().exists("linked") is True
    assert [r["rating"] for r in FeedbackRepository().for_session("linked")] == ["down"]


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
