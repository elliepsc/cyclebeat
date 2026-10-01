"""Parquet lake — partitioned by ingestion date, per E.5.

    lake/raw/tracks/dt=YYYY-MM-DD/tracks.parquet
    lake/raw/resolutions/dt=YYYY-MM-DD/resolutions.parquet

The lake is also the permanent cache E.8 asks for: once a track and a source's opinion are
written, no re-fetch is ever needed to rebuild the warehouse. ADR-005 leans on this — if
Deezer tightened preview access tomorrow, everything already resolved stays resolved.

Parquet is written through DuckDB's `COPY ... TO ... (FORMAT PARQUET)` rather than pyarrow:
duckdb is already a declared dependency, so this adds none (E.0.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

LAKE_ROOT = Path("lake")
TRACKS = "raw/tracks"
RESOLUTIONS = "raw/resolutions"

# The transactional side of the lake (ADR-009). `sessions` and `feedback` are produced by the
# API into Postgres/SQLite and EXTRACTED here, so the warehouse is fed by the same lake as
# everything else instead of dbt reaching across into an OLTP database. Keeping one entry
# point into the warehouse is what makes `make ingest && make dbt` reproducible from cold.
SESSIONS = "raw/sessions"
FEEDBACK = "raw/feedback"

# Stable identifiers for the two lake datasets, used by the DAGs to declare their ordering
# to Airflow (`Asset(...)`). Logical URIs, deliberately not filesystem paths: the lake root
# differs between the container, CI and a checkout, while the identity does not. They live
# here rather than in `dags/` because that folder is not importable from a bare DagBag, and
# because building the Asset object -- the only Airflow-aware part -- stays in the DAGs.
ASSET_TRACKS = "cyclebeat://lake/raw/tracks"
ASSET_RESOLUTIONS = "cyclebeat://lake/raw/resolutions"
ASSET_APP_DB = "cyclebeat://lake/raw/app_db"


def partition_dir(dataset: str, dt: date | str, root: Path | None = None) -> Path:
    """`lake/<dataset>/dt=YYYY-MM-DD/`. The `dt=` prefix is what makes it a Hive partition,
    which DuckDB's `hive_partitioning` reads back as a real column."""
    stamp = dt.isoformat() if isinstance(dt, date) else str(dt)
    return (root or LAKE_ROOT) / dataset / f"dt={stamp}"


def _sql_type(annotation: Any) -> str:
    """Map a pydantic field annotation onto a DuckDB column type.

    Read from the MODEL, not from the first row's values: inferring from values would type
    a column VARCHAR whenever its first row happens to be None, and `bpm_raw` is None for
    every track Deezer has no BPM for — which is most of them.
    """
    text = str(annotation)
    if "bool" in text:
        return "BOOLEAN"
    if "datetime" in text:
        return "TIMESTAMP"
    if "float" in text:
        return "DOUBLE"
    if "int" in text:
        return "INTEGER"
    return "VARCHAR"


def _rows_to_relation(con: duckdb.DuckDBPyConnection, rows: Sequence[BaseModel]) -> None:
    """Materialize the pydantic rows as a DuckDB temp table named `payload`."""
    fields = type(rows[0]).model_fields
    columns = list(fields.keys())
    ddl = ", ".join(f'"{name}" {_sql_type(field.annotation)}' for name, field in fields.items())
    con.execute(f"CREATE OR REPLACE TEMP TABLE payload ({ddl})")

    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(f'"{column}"' for column in columns)
    tuples = [tuple(row.model_dump()[column] for column in columns) for row in rows]
    con.executemany(f"INSERT INTO payload ({column_list}) VALUES ({placeholders})", tuples)


def write_partition(
    rows: Sequence[BaseModel],
    dataset: str,
    dt: date | str,
    root: Path | None = None,
    filename: str = "part.parquet",
) -> Path | None:
    """Write one partition. Returns the file path, or None when there is nothing to write.

    Overwrites the partition rather than appending: re-running the same `dt` must not
    duplicate rows, which is the idempotency E.5 requires of the whole pipeline.
    """
    if not rows:
        return None

    directory = partition_dir(dataset, dt, root)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename

    con = duckdb.connect()
    try:
        _rows_to_relation(con, rows)
        con.execute(
            f"COPY payload TO '{destination.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE 1)"
        )
    finally:
        con.close()
    return destination


def read_dataset(dataset: str, root: Path | None = None) -> list[dict[str, Any]]:
    """Read every partition of a dataset back, with `dt` recovered from the path."""
    base = (root or LAKE_ROOT) / dataset
    if not base.exists():
        return []

    pattern = (base / "**" / "*.parquet").as_posix()
    con = duckdb.connect()
    try:
        cursor = con.execute(
            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true)"
        )
        columns = [description[0] for description in cursor.description or []]
        # strict=True: a row whose arity differs from the cursor description means the
        # Parquet schema drifted from the model, which must fail loudly rather than
        # silently truncate a column out of the warehouse.
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        con.close()
