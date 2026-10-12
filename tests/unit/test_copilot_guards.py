"""Guards of the read-only warehouse tools (E.4 `[rendu]`, ADR-012).

The six E.4 tests that need no LLM keep their E.4 names (owner decision, ROADMAP "Décisions
et points ouverts" 1); the three that need the agent loop or `trigger_resolve` arrive with
the phase-6 LLM layer. The injection cases after them are the criterion-12 brief: every one
proves a REFUSAL, and the engine-level tests prove the second layer holds even when the SQL
guard is bypassed.

Every test runs against a temp DuckDB built here -- never the real `data/` warehouse.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from api.repositories.readonly_warehouse import (
    WarehouseUnavailable,
    locked,
    run_select,
)
from api.services.warehouse_tools import (
    MARTS_ALLOWLIST,
    MAX_ROWS,
    ToolError,
    get_quality_report,
    guard_select,
    query_marts,
)


@pytest.fixture()
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute(
            "CREATE TABLE dim_track AS SELECT i AS track_id, 'title ' || i AS title, "
            "100.0 + i % 60 AS bpm_effective FROM range(500) t(i)"
        )
        con.execute("CREATE TABLE fct_session (session_id VARCHAR, duration_min INTEGER)")
        con.execute(
            "CREATE TABLE mart_bpm_coverage "
            "(source VARCHAR, n_tracks BIGINT, n_usable BIGINT, pct_of_catalogue DOUBLE)"
        )
        con.execute("INSERT INTO mart_bpm_coverage VALUES ('librosa', 40, 40, 83.3)")
        con.execute(
            "CREATE TABLE mart_data_quality (confidence_method VARCHAR, n_tracks BIGINT, "
            "pct_of_catalogue DOUBLE, avg_confidence DOUBLE, n_with_bpm BIGINT, "
            "n_flagged_review BIGINT)"
        )
        con.execute(
            "INSERT INTO mart_data_quality VALUES "
            "('cross_validated', 30, 62.5, 0.9, 30, 0), ('review', 18, 37.5, 0.3, 18, 18)"
        )
        con.execute("CREATE SCHEMA raw")
        con.execute("CREATE TABLE raw.tracks (track_id VARCHAR)")
    return path


@pytest.fixture()
def secret_file(tmp_path: Path) -> Path:
    path = tmp_path / "secret.csv"
    path.write_text("key\nsk-not-a-real-secret\n")
    return path


def _refused(sql: str, code: str | None = None) -> ToolError:
    with pytest.raises(ToolError) as info:
        guard_select(sql)
    if code is not None:
        assert info.value.code == code, info.value
    return info.value


# ── The six E.4 tests of the `[rendu]` split ─────────────────────────────────────────────


def test_rejects_prompt_injection_drop(warehouse: Path) -> None:
    """Adapted to SQL (ROADMAP decision 1): the DROP never reaches DuckDB."""
    with pytest.raises(ToolError) as info:
        query_marts("DROP TABLE dim_track", db_path=warehouse)
    assert info.value.code == "not_a_select"
    assert query_marts("SELECT count(*) FROM dim_track", db_path=warehouse)["rows"] == [[500]]


def test_rejects_multi_statement() -> None:
    _refused("SELECT * FROM raw.tracks; DELETE FROM fct_session", "multi_statement")


def test_rejects_non_select() -> None:
    _refused("UPDATE dim_track SET confidence=1", "not_a_select")


def test_rejects_table_outside_allowlist() -> None:
    _refused(
        "SELECT * FROM dim_track WHERE track_id IN (SELECT track_id FROM raw.tracks)",
        "table_not_allowed",
    )


def test_legit_question_with_delete_word_passes(warehouse: Path) -> None:
    """Adapted to SQL: the word "delete" in a SELECT is data, not a statement."""
    result = query_marts(
        "SELECT count(*) AS n FROM dim_track WHERE title <> 'delete me'", db_path=warehouse
    )
    assert result["rows"] == [[500]]


def test_limit_injected_when_absent(warehouse: Path) -> None:
    result = query_marts("SELECT track_id FROM dim_track", db_path=warehouse)
    assert result["sql"].endswith(f"LIMIT {MAX_ROWS}")
    assert result["row_count"] == MAX_ROWS


# ── Injection cases: each one is a refusal ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        # several statements, including through comments and empty statements
        ("SELECT 1 FROM dim_track; DROP TABLE dim_track", "multi_statement"),
        ("SELECT 1 FROM dim_track;; DROP TABLE dim_track", "multi_statement"),
        ("SELECT 1 FROM dim_track; -- harmless?\nDELETE FROM dim_track", "multi_statement"),
        # DDL / DML, any case
        ("DROP TABLE dim_track", "not_a_select"),
        ("dRoP tAbLe dim_track", "not_a_select"),
        ("CREATE TABLE x AS SELECT * FROM dim_track", "not_a_select"),
        ("INSERT INTO dim_track VALUES (1, 't', 120)", "not_a_select"),
        ("DELETE FROM dim_track", "not_a_select"),
        ("ALTER TABLE dim_track ADD COLUMN x INT", "not_a_select"),
        ("SELECT * INTO copy_of_tracks FROM dim_track", "not_a_select"),
        # engine and session commands
        ("ATTACH '/tmp/other.duckdb' AS other", "not_a_select"),
        ("COPY dim_track TO '/tmp/out.csv'", "not_a_select"),
        ("PRAGMA enable_profiling", "not_a_select"),
        ("SET enable_external_access = true", "not_a_select"),
        ("RESET lock_configuration", "not_a_select"),
        ("INSTALL httpfs", "not_a_select"),
        ("LOAD httpfs", "not_a_select"),
        ("CALL pragma_version()", "not_a_select"),
        ("EXPORT DATABASE '/tmp/dump'", "parse_error"),
        # reading the disk through table functions or replacement scans
        ("SELECT * FROM read_csv('/etc/passwd')", "table_not_allowed"),
        ("SELECT * FROM read_csv_auto('.env')", "table_not_allowed"),
        ("SELECT * FROM read_parquet('lake/**/*.parquet')", "table_not_allowed"),
        ("SELECT * FROM read_text('/etc/hostname')", "table_not_allowed"),
        ("SELECT * FROM glob('/home/*')", "table_not_allowed"),
        ("SELECT * FROM '/etc/passwd'", "table_not_allowed"),
        ("SELECT * FROM 'data/cyclebeat_runtime.duckdb'", "table_not_allowed"),
        ("SELECT * FROM dim_track, read_csv('/etc/passwd')", "table_not_allowed"),
        (
            "SELECT (SELECT count(*) FROM read_text('/etc/hostname')) FROM dim_track",
            "table_not_allowed",
        ),
        # a CTE does not launder a forbidden source
        ("WITH t AS (SELECT * FROM read_csv('/etc/passwd')) SELECT * FROM t", "table_not_allowed"),
        ("WITH t AS (SELECT * FROM raw.tracks) SELECT * FROM t", "table_not_allowed"),
        # catalogue and metadata, other schemas, other databases
        ("SELECT * FROM duckdb_settings()", "table_not_allowed"),
        ("SELECT * FROM information_schema.tables", "table_not_allowed"),
        ("SELECT * FROM raw.tracks", "table_not_allowed"),
        ("SELECT * FROM other.main.dim_track", "table_not_allowed"),
        ("SELECT * FROM stg_tracks", "table_not_allowed"),
        # comment and case tricks around a forbidden statement
        ("/* SELECT */ DROP TABLE dim_track", "not_a_select"),
        ("-- SELECT\nDELETE FROM dim_track", "not_a_select"),
        # nothing at all
        ("", "empty_query"),
        ("   \n  ", "empty_query"),
    ],
)
def test_injection_is_refused(sql: str, code: str) -> None:
    _refused(sql, code)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM dim_track /* ; DROP TABLE dim_track */",
        "SeLeCt count(*) FrOm DIM_TRACK",
        "WITH t AS (SELECT * FROM dim_track) SELECT count(*) FROM t",
        "SELECT * FROM main.dim_track LIMIT 5",
        "SELECT source FROM mart_bpm_coverage "
        "UNION SELECT confidence_method FROM mart_data_quality",
    ],
)
def test_comment_and_case_variants_of_a_legit_select_pass(warehouse: Path, sql: str) -> None:
    """The guard refuses statements, not words: these must not be false positives."""
    assert query_marts(sql, db_path=warehouse)["row_count"] >= 1


def test_the_allowlist_is_e4_restricted_to_existing_marts() -> None:
    assert MARTS_ALLOWLIST == {"dim_track", "fct_session", "mart_bpm_coverage", "mart_data_quality"}


def test_an_explicit_limit_above_the_cap_is_still_capped(warehouse: Path) -> None:
    result = query_marts("SELECT track_id FROM dim_track LIMIT 450", db_path=warehouse)
    assert result["row_count"] == MAX_ROWS
    assert result["truncated"] is True


def test_a_slow_query_times_out(warehouse: Path) -> None:
    with pytest.raises(ToolError) as info:
        query_marts(
            "SELECT count(*) FROM dim_track a, dim_track b, dim_track c, dim_track d",
            db_path=warehouse,
            timeout_s=0.2,
        )
    assert info.value.code == "timeout"


def test_errors_are_structured_without_stack(warehouse: Path) -> None:
    with pytest.raises(ToolError) as info:
        query_marts("SELECT no_such_column FROM dim_track", db_path=warehouse)
    payload = info.value.as_dict()
    assert payload["error"]["code"] == "query_failed"
    assert "Traceback" not in payload["error"]["message"]
    assert "\n" not in payload["error"]["message"]


# ── The engine layer holds even if the SQL guard is bypassed ─────────────────────────────


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE dim_track",
        "CREATE TABLE x (i INT)",
        "INSERT INTO fct_session VALUES ('s', 30)",
        "SET enable_external_access = true",
        "SET lock_configuration = false",
        "INSTALL httpfs",
        "LOAD httpfs",
    ],
)
def test_the_locked_connection_refuses_writes_and_unlocking(warehouse: Path, sql: str) -> None:
    with locked(warehouse) as con, pytest.raises(duckdb.Error):
        con.execute(sql)


def test_the_locked_connection_cannot_read_the_disk(
    warehouse: Path, secret_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out.csv"
    with locked(warehouse) as con:
        for sql in (
            f"SELECT * FROM read_csv_auto('{secret_file}')",
            f"SELECT * FROM '{secret_file}'",
            f"SELECT * FROM glob('{tmp_path}/*')",
            f"COPY dim_track TO '{out}'",
            f"ATTACH '{tmp_path / 'other.duckdb'}' AS other",
        ):
            with pytest.raises(duckdb.Error):
                run_select(con, sql, MAX_ROWS, 5.0)
    assert not out.exists()
    assert not (tmp_path / "other.duckdb").exists()


def test_the_warehouse_file_is_unchanged_by_the_tools(warehouse: Path) -> None:
    before = (warehouse.stat().st_size, warehouse.stat().st_mtime_ns)
    query_marts("SELECT * FROM dim_track", db_path=warehouse)
    get_quality_report(db_path=warehouse)
    assert (warehouse.stat().st_size, warehouse.stat().st_mtime_ns) == before


def test_an_absent_warehouse_is_refused_and_never_created(tmp_path: Path) -> None:
    absent = tmp_path / "absent.duckdb"
    with pytest.raises(WarehouseUnavailable), locked(absent):
        pass
    with pytest.raises(ToolError) as info:
        query_marts("SELECT * FROM dim_track", db_path=absent)
    assert info.value.code == "warehouse_unavailable"
    assert not absent.exists()


# ── get_quality_report reuses the API service ────────────────────────────────────────────


def test_quality_report_matches_the_api_service(warehouse: Path) -> None:
    report = get_quality_report(db_path=warehouse)
    assert report["summary"]["n_tracks"] == 48
    assert report["summary"]["n_flagged_review"] == 18
    assert report["coverage"] == [
        {"source": "librosa", "n_tracks": 40, "pct_of_catalogue": 83.3, "n_usable": 40}
    ]
