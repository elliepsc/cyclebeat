"""The exposure database behind the read-only tools (ADR-012 note, 13 October 2026).

Three bypasses of the SQL guard in one phase (CTE scope, catalogue functions, Unicode folding)
had one cause: the guard inferred from SQL text which tables would be read. The structural fix
is that a table the tools may not read does not EXIST where their SQL runs: an in-memory
database holding copies of the allowed marts only, with path settings neutralised, then locked.
Every test here runs SQL straight on that connection, without the guard, on purpose.

Every test builds its own temp warehouse -- never the real `data/` one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pytest

from api.repositories.readonly_warehouse import WarehouseUnavailable, exposed, run_select
from api.services import warehouse_tools
from api.services.warehouse_tools import MARTS_ALLOWLIST, ToolError, query_marts

SECRET_ROW = "SECRET_ROW_not_exposed"


@pytest.fixture()
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE dim_track AS SELECT i AS track_id FROM range(7) t(i)")
        con.execute("CREATE TABLE fct_session (session_id VARCHAR)")
        con.execute("CREATE TABLE mart_bpm_coverage AS SELECT 'librosa' AS source")
        # mart_data_quality deliberately absent: a mart `make dbt` has not built yet
        con.execute(f"CREATE TABLE stg_secret AS SELECT '{SECRET_ROW}' AS v")
        con.execute("CREATE VIEW stg_secret_view AS SELECT v FROM stg_secret")
        con.execute("CREATE SCHEMA raw")
        con.execute(f"CREATE TABLE raw.tracks AS SELECT '{SECRET_ROW}' AS v")
    return path


def _run(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[object, ...]]:
    return run_select(con, sql, 200, 5.0)[1]


def test_only_the_allowed_marts_exist(warehouse: Path) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        tables = {r[0] for r in _run(con, "SELECT table_name FROM duckdb_tables()")}
        views = _run(con, "SELECT view_name FROM duckdb_views() WHERE NOT internal")
        assert _run(con, "SELECT count(*) FROM dim_track") == [(7,)]
    assert tables == {"dim_track", "fct_session", "mart_bpm_coverage"}
    assert views == []


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM stg_secret",
        "SELECT * FROM stg_secret_view",
        "SELECT * FROM raw.tracks",
        "SELECT * FROM main.stg_secret",
    ],
)
def test_a_table_off_the_allowlist_cannot_be_read_without_the_guard(
    warehouse: Path, sql: str
) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con, pytest.raises(duckdb.CatalogException):
        _run(con, sql)


def test_catalogue_functions_find_nothing_to_leak(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse), read_only=True) as source:
        oid = source.execute(
            "SELECT view_oid FROM duckdb_views() WHERE view_name = 'stg_secret_view'"
        ).fetchone()
    assert oid is not None
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        assert _run(con, f"SELECT pg_get_viewdef({oid[0]})") == [(None,)]
        names = {r[0] for r in _run(con, "SELECT database_name FROM duckdb_databases()")}
        paths = _run(con, "SELECT path FROM duckdb_databases() WHERE path IS NOT NULL")
    assert names <= {"memory", "system", "temp"}
    assert paths == []


@pytest.mark.parametrize("setting", ["secret_directory", "home_directory", "temp_directory"])
def test_path_settings_are_neutralised(warehouse: Path, setting: str) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        value = str(_run(con, f"SELECT current_setting('{setting}')")[0][0])
    assert str(Path.home()) not in value
    assert str(warehouse.parent) not in value


@pytest.mark.parametrize(
    "sql",
    [
        "SET enable_external_access = true",
        "SET lock_configuration = false",
        "SET secret_directory = '/tmp'",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
    ],
)
def test_the_exposure_database_is_locked(warehouse: Path, sql: str) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con, pytest.raises(duckdb.Error):
        _run(con, sql)


def test_the_warehouse_cannot_be_attached_again(warehouse: Path) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con, pytest.raises(duckdb.Error):
        con.execute(f"ATTACH '{warehouse}' AS again (READ_ONLY)")


def test_a_write_dies_with_the_call(warehouse: Path) -> None:
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        con.execute("CREATE TABLE scratch AS SELECT 1 AS x")
        con.execute("DELETE FROM dim_track")
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        assert _run(con, "SELECT count(*) FROM dim_track") == [(7,)]
        with pytest.raises(duckdb.CatalogException):
            _run(con, "SELECT * FROM scratch")


def test_the_warehouse_file_is_untouched(warehouse: Path) -> None:
    before = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        _run(con, "SELECT count(*) FROM dim_track")
    assert hashlib.sha256(warehouse.read_bytes()).hexdigest() == before


def test_an_absent_warehouse_is_refused_and_never_created(tmp_path: Path) -> None:
    missing = tmp_path / "absent.duckdb"
    with pytest.raises(WarehouseUnavailable), exposed(missing, MARTS_ALLOWLIST):
        pass
    assert not missing.exists()


def test_query_marts_runs_on_the_exposure_database(
    warehouse: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second line holds alone: even with the guard switched off, nothing else is there."""
    monkeypatch.setattr(warehouse_tools, "guard_select", lambda sql: sql)
    with pytest.raises(ToolError) as info:
        query_marts("SELECT * FROM stg_secret", db_path=warehouse)
    assert info.value.code == "query_failed"
    assert SECRET_ROW not in info.value.message
    assert query_marts("SELECT count(*) FROM dim_track", db_path=warehouse)["rows"] == [[7]]


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "CVE-2024-41672: on DuckDB <= 1.0.0, sniff_csv reads a file even with "
        "enable_external_access=false, on the exposure database too. The SQL guard refuses it. "
        "Ticket: ROADMAP, DuckDB upgrade line. When the upgrade lands this turns red: drop "
        "the marker."
    ),
)
def test_the_exposure_database_refuses_sniff_csv(warehouse: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.csv"
    secret.write_text("TOPSECRET_42,b\nx,y\n")
    with exposed(warehouse, MARTS_ALLOWLIST) as con:
        try:
            rows = _run(con, f"SELECT Columns FROM sniff_csv('{secret}')")
        except duckdb.Error:
            return
    raise AssertionError(f"the exposure database read the file header: {rows}")
