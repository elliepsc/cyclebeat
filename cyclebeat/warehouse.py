"""Lake -> DuckDB. The `load_duckdb` half of `dag_build_warehouse` (E.5).

dbt reads what this writes. The tables are the E.2 raw layer:

    raw.tracks       one row per (track_id, dt)
    raw.resolutions  one row per (track_id, source, dt)

Loading is a full replace from the lake, not an append: the lake is the source of truth and
already deduplicated per partition, so rebuilding from it is idempotent by construction.
That is also what makes `make dbt` runnable from cold on a clean clone.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from cyclebeat.lake import LAKE_ROOT, RESOLUTIONS, TRACKS

DEFAULT_DB = Path("data") / "cyclebeat_runtime.duckdb"

_TRACKS_DDL = """
    CREATE TABLE IF NOT EXISTS raw_tracks (
        track_id        VARCHAR,
        source_platform VARCHAR,
        title           VARCHAR,
        artist          VARCHAR,
        duration_s      DOUBLE,
        preview_url     VARCHAR,
        ingested_at     TIMESTAMP,
        dt              DATE
    )
"""

_RESOLUTIONS_DDL = """
    CREATE TABLE IF NOT EXISTS raw_resolutions (
        track_id    VARCHAR,
        source      VARCHAR,
        bpm_raw     DOUBLE,
        resolved_at TIMESTAMP,
        latency_ms  INTEGER,
        dt          DATE
    )
"""

# The transactional side (ADR-009). Produced by the API into Postgres/SQLite, extracted into
# the lake by `cyclebeat.app_store`, and loaded here like any other dataset.
#
# CREATE OR REPLACE, not CREATE IF NOT EXISTS. Both tables already exist on any machine that
# ran v1 or the ADR-008 build, in shapes that do not match -- and IF NOT EXISTS is a silent
# no-op against them, which is precisely how the earlier `feedback` binder error happened.
# Replacing is also simply correct here: ADR-009 makes the lake the single source for the
# warehouse, and `_load_dataset` already does a full replace from it, so any row that exists
# only in DuckDB is an orphan of the superseded design rather than data to preserve.
#
# `sessions` keeps the OLTP name; the E.2 fact table `fct_session` is a dbt model built ON
# TOP of it, not a table the API writes -- the correction ADR-009 makes to ADR-008.
_SESSIONS_DDL = """
    CREATE OR REPLACE TABLE sessions (
        session_id     VARCHAR,
        level          VARCHAR,
        goal           VARCHAR,
        duration_min   INTEGER,
        verdict        VARCHAR,
        n_segments     INTEGER,
        duration_gap_s DOUBLE,
        created_at     TIMESTAMP,
        dt             DATE
    )
"""

_FEEDBACK_DDL = """
    CREATE OR REPLACE TABLE feedback (
        session_id    VARCHAR,
        session_title VARCHAR,
        rating        VARCHAR,
        note          VARCHAR,
        created_at    TIMESTAMP,
        dt            DATE
    )
"""

# The E.2 verdict, materialized from Python rather than recomputed in SQL. E.2 forbids
# variants of the confidence rule, so there is exactly one implementation (`cyclebeat.e2`)
# and dbt only ever READS its output. Re-deriving the rule in a model would be the second
# implementation the appendix rules out.
_RESOLVED_DDL = """
    CREATE TABLE IF NOT EXISTS raw_resolved (
        track_id          VARCHAR,
        bpm_effective     DOUBLE,
        zone              VARCHAR,
        confidence        DOUBLE,
        confidence_method VARCHAR,
        n_sources_agree   INTEGER,
        review            BOOLEAN
    )
"""


def database_path() -> Path:
    """Honour RUNTIME_DB_PATH, which compose and CI both set."""
    configured = os.environ.get("RUNTIME_DB_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_DB


def _load_dataset(
    con: duckdb.DuckDBPyConnection, table: str, dataset: str, root: Path
) -> int:
    pattern = (root / dataset / "**" / "*.parquet").as_posix()
    if not (root / dataset).exists():
        return 0
    con.execute(f"DELETE FROM {table}")
    con.execute(
        f"INSERT INTO {table} SELECT * FROM read_parquet('{pattern}', hive_partitioning = true)"
    )
    count = con.execute(f"SELECT count(*) FROM {table}").fetchone()
    return int(count[0]) if count else 0


def load_lake(db_path: Path | None = None, lake_root: Path | None = None) -> dict[str, int]:
    """Load the lake into DuckDB and materialize the E.2 verdict. Row counts per table.

    Full replace, not append: the lake is the source of truth and is already deduplicated
    per partition, so rebuilding from it is idempotent by construction. That is what makes
    `make ingest && make dbt` runnable from cold on a clean clone.
    """
    from cyclebeat.lake import FEEDBACK, SESSIONS, read_dataset
    from cyclebeat.resolve import cross_validate

    target = db_path or database_path()
    root = lake_root or LAKE_ROOT
    target.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(target))
    try:
        con.execute(_TRACKS_DDL)
        con.execute(_RESOLUTIONS_DDL)
        con.execute(_RESOLVED_DDL)
        con.execute(_SESSIONS_DDL)
        con.execute(_FEEDBACK_DDL)

        counts = {
            "raw_tracks": _load_dataset(con, "raw_tracks", TRACKS, root),
            "raw_resolutions": _load_dataset(con, "raw_resolutions", RESOLUTIONS, root),
            # The app store may legitimately be empty (nobody has generated a session yet),
            # in which case no partition exists and these stay 0 -- the warehouse still
            # builds, which is what keeps `make dbt` runnable on a clean clone.
            "sessions": _load_dataset(con, "sessions", SESSIONS, root),
            "feedback": _load_dataset(con, "feedback", FEEDBACK, root),
        }

        track_ids = [str(row["track_id"]) for row in read_dataset(TRACKS, root)]
        resolved = cross_validate(read_dataset(RESOLUTIONS, root), track_ids)
        con.execute("DELETE FROM raw_resolved")
        if resolved:
            con.executemany(
                "INSERT INTO raw_resolved VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        row.track_id,
                        row.bpm_effective,
                        row.zone,
                        row.confidence,
                        row.confidence_method,
                        row.n_sources_agree,
                        row.review,
                    )
                    for row in resolved
                ],
            )
        counts["raw_resolved"] = len(resolved)
        return counts
    finally:
        con.close()
