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

SECRET_ROW = "SECRET_ROW_off_the_allowlist"


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
        # A real table and a view in the DEFAULT schema, off the allowlist, like dbt's
        # staging views: only a table that exists can prove a refusal is not a no-op.
        con.execute(f"CREATE TABLE stg_secret AS SELECT '{SECRET_ROW}' AS v")
        con.execute("CREATE VIEW stg_secret_view AS SELECT v FROM stg_secret")
        # A name with a `k`: U+212A KELVIN SIGN lowercases to ASCII `k` in Python, not in DuckDB.
        con.execute(f"CREATE TABLE stg_tracks AS SELECT '{SECRET_ROW}' AS v")
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
        # sniff_csv reads a file even on the locked engine (CVE-2024-41672, DuckDB 0.10.2):
        # the guard is the layer that holds, so its refusal is pinned here
        ("SELECT * FROM sniff_csv('/etc/passwd')", "table_not_allowed"),
        (
            "SELECT (SELECT Columns FROM sniff_csv('/etc/passwd')) FROM dim_track",
            "table_not_allowed",
        ),
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
        # the ASCII rule is for table and CTE NAMES only: strings and aliases stay free
        "SELECT count(*) AS n FROM dim_track WHERE title <> 'Caf\u00e9'",
        'SELECT title AS "titre_\u00e9" FROM dim_track',
        "SELECT upper('\u00e9t\u00e9') AS saison FROM dim_track",
    ],
)
def test_comment_and_case_variants_of_a_legit_select_pass(warehouse: Path, sql: str) -> None:
    """The guard refuses statements, not words: these must not be false positives."""
    assert query_marts(sql, db_path=warehouse)["row_count"] >= 1


def test_the_guard_output_is_a_fixed_point_of_the_guard() -> None:
    """What runs is what was checked: guarding the emitted SQL again changes nothing."""
    for sql in (
        "SELECT count(*) FROM dim_track WHERE title <> 'Caf\u00e9'",
        "WITH t AS (SELECT * FROM dim_track) SELECT (SELECT count(*) FROM t) AS n",
        "SELECT source FROM mart_bpm_coverage "
        "UNION SELECT confidence_method FROM mart_data_quality",
    ):
        emitted = guard_select(sql)
        assert guard_select(emitted) == emitted


# ── A CTE name only counts inside its own scope (phase-10 audit of PR #38, finding H1) ───
# The allowlist once collected CTE names from the whole statement: a CTE defined in ANY
# subquery whitelisted its name everywhere, so an outer FROM of that name read the real table.


@pytest.mark.parametrize(
    "sql",
    [
        # derived table
        "SELECT * FROM stg_secret, (WITH stg_secret AS (SELECT 1 x) SELECT * FROM stg_secret) t",
        # scalar subquery
        "SELECT (SELECT v FROM stg_secret) AS v, "
        "(WITH stg_secret AS (SELECT 1 x) SELECT x FROM stg_secret) AS y",
        # one branch of a set operation
        "SELECT v FROM stg_secret UNION ALL "
        "(WITH stg_secret AS (SELECT 'a' v) SELECT v FROM stg_secret)",
        # a CTE nested in a sibling CTE
        "WITH a AS (WITH stg_secret AS (SELECT 1 x) SELECT x FROM stg_secret), "
        "b AS (SELECT v FROM stg_secret) SELECT * FROM b",
        # a predicate subquery
        "SELECT * FROM stg_secret "
        "WHERE EXISTS (WITH stg_secret AS (SELECT 1) SELECT 1 FROM stg_secret)",
        # a CTE body naming the real table it shadows
        "WITH stg_secret AS (SELECT v FROM stg_secret) SELECT * FROM stg_secret",
        # Unicode folding (fix-branch audit, HIGH 1): Python's lower() maps U+212A KELVIN SIGN
        # to `k`, DuckDB does not, so this CTE "matched" the real stg_tracks in the guard only
        'WITH "stg_tracKs" AS (SELECT 1 AS x) SELECT * FROM stg_tracks',
        "WITH stg_tracKs AS (SELECT 1 AS x) SELECT * FROM stg_tracks",
        # a non-ASCII name that lowercases onto a mart is refused by the guard, not the engine
        'SELECT * FROM "dim_tracK"',
    ],
)
def test_a_cte_out_of_scope_does_not_whitelist_a_real_table(warehouse: Path, sql: str) -> None:
    with pytest.raises(ToolError) as info:
        result = query_marts(sql, db_path=warehouse)
        pytest.fail(f"ran and returned {result['rows']}")
    assert info.value.code == "table_not_allowed", info.value
    assert SECRET_ROW not in info.value.message


@pytest.mark.parametrize(
    "sql",
    [
        "WITH t AS (SELECT * FROM dim_track) SELECT * FROM t",
        "WITH t AS (SELECT * FROM dim_track) SELECT * FROM (SELECT * FROM t) s",
        "WITH t AS (SELECT * FROM dim_track) SELECT (SELECT count(*) FROM t) AS n",
        "WITH a AS (SELECT * FROM dim_track), b AS (SELECT * FROM a) SELECT * FROM b",
        "SELECT * FROM (WITH t AS (SELECT * FROM dim_track) SELECT * FROM t) s",
        "WITH dim_track AS (SELECT 1 AS track_id) SELECT * FROM dim_track",
        "SELECT * FROM dim_track d LEFT JOIN fct_session f ON true",
        "SELECT track_id::VARCHAR FROM dim_track UNION ALL SELECT session_id FROM fct_session",
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3) "
        "SELECT * FROM r",
    ],
)
def test_ctes_used_within_their_scope_still_pass(warehouse: Path, sql: str) -> None:
    """The scope fix must not refuse what the allowlist was always meant to allow."""
    assert query_marts(sql, db_path=warehouse)["row_count"] >= 1


# ── Scalar functions that read the catalogue or the configuration ────────────────────────
# The guard refuses table functions by shape. These are scalar CALLS, so they passed it, yet
# DuckDB 0.10.2 runs them on the locked engine: pg_get_viewdef / pg_get_constraintdef /
# format_type are macros over duckdb_views() / duckdb_constraints() / duckdb_types(), and
# current_setting returns absolute paths (secret_directory carries the OS user's home).


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_get_viewdef(1) FROM dim_track",
        "SELECT PG_GET_VIEWDEF(1) FROM dim_track",
        "SELECT track_id FROM dim_track WHERE pg_get_viewdef(1) IS NULL",
        "SELECT pg_get_constraintdef(1, true) FROM dim_track",
        "SELECT format_type(1, 2) FROM dim_track",
        "SELECT current_setting('secret_directory') FROM dim_track",
        "SELECT current_setting('temp_directory') FROM dim_track",
        "WITH t AS (SELECT current_setting('home_directory') AS h) SELECT * FROM t",
        # get_block_size: a macro over pragma_database_size() (fix-branch audit, LOW 2)
        "SELECT get_block_size(current_database()) FROM dim_track",
        # call shapes the locked engine EXECUTES (phase-10 probe): the name check must hold
        "SELECT pg_catalog.pg_get_viewdef(1) FROM dim_track",
        "SELECT system.pg_catalog.pg_get_viewdef(1) FROM dim_track",
        "SELECT main.current_setting('secret_directory') FROM dim_track",
        "SELECT system.main.current_setting('secret_directory') FROM dim_track",
        'SELECT "pg_get_viewdef"(1) FROM dim_track',
        "SELECT Current_Setting('secret_directory') FROM dim_track",
        "SELECT ('secret_directory').current_setting() FROM dim_track",
        "SELECT (1).pg_get_viewdef() FROM dim_track",
        "SELECT list_transform([1], x -> current_setting('secret_directory')) FROM dim_track",
        "SELECT CASE WHEN track_id = 1 THEN format_type(4, NULL) END FROM dim_track",
        "SELECT track_id FROM dim_track ORDER BY pg_get_constraintdef(1, true)",
        # sqlglot re-emits function names with Python's Unicode-aware upper(): a letter whose
        # upper case is ASCII (U+0131 dotless i, U+017F long s, U+FB06 st ligature) turned an
        # unknown name into a refused one AFTER the check (fix-branch audit, pass 2, NEW-H1)
        "SELECT current_sett\u0131ng('secret_directory') FROM dim_track",
        "SELECT current_\u017fetting('home_directory') FROM dim_track",
        "SELECT pg_get_v\u0131ewdef(1) FROM dim_track",
        "SELECT pg_get_con\ufb06raintdef(1, true) FROM dim_track",
        "SELECT get_block_\u017fize(current_database()) FROM dim_track",
        "SELECT \"current_sett\u0131ng\"('secret_directory') FROM dim_track",
    ],
)
def test_catalogue_and_configuration_functions_are_refused(sql: str) -> None:
    _refused(sql, "function_not_allowed")


def test_a_view_definition_off_the_allowlist_does_not_leak(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse), read_only=True) as con:
        oid = con.execute(
            "SELECT view_oid FROM duckdb_views() WHERE view_name = 'stg_secret_view'"
        ).fetchone()
    assert oid is not None
    with pytest.raises(ToolError) as info:
        query_marts(f"SELECT pg_get_viewdef({oid[0]}) AS d FROM dim_track", db_path=warehouse)
    assert info.value.code == "function_not_allowed"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT version() AS v FROM dim_track",
        "SELECT current_database() AS d FROM dim_track",
        "SELECT upper(title), round(bpm_effective) FROM dim_track",
    ],
)
def test_harmless_scalar_functions_still_pass(warehouse: Path, sql: str) -> None:
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


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "CVE-2024-41672: on DuckDB <= 1.0.0, sniff_csv reads a file even with "
        "enable_external_access=false. The SQL guard refuses it (test_injection_is_refused). "
        "Ticket: ROADMAP, DuckDB upgrade line. When the upgrade lands this turns red: drop "
        "the marker."
    ),
)
def test_the_locked_connection_refuses_sniff_csv(warehouse: Path, secret_file: Path) -> None:
    with locked(warehouse) as con:
        try:
            _, rows, _ = run_select(con, f"SELECT * FROM sniff_csv('{secret_file}')", 5, 5.0)
        except duckdb.Error:
            return
    raise AssertionError(f"the locked engine read the file header: {rows[0][6]}")


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
