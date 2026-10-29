"""The lake stores UTC, whatever the time zone of the process that writes it (#57).

Before #57, an aware UTC value went into a DuckDB `TIMESTAMP` column through the session time
zone, which DuckDB takes from the process `TZ`: on a host in Europe/Paris the lake held local
wall time, +2 h in summer and +1 h in winter. Reading back is time-zone independent (the Parquet
column is `isAdjustedToUTC=0`), so only the WRITE has to run under a non-UTC `TZ`, and it runs in
a subprocess: DuckDB reads the zone when it loads, not when a test changes `os.environ`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from cyclebeat import lake
from cyclebeat.app_store import RawFeedback

REPO_ROOT = Path(__file__).resolve().parents[1]
PARIS = "Europe/Paris"


def _run_under(tz: str, argv: list[str]) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "TZ": tz, "PYTHONPATH": str(REPO_ROOT)}
    environment.pop("DATABASE_URL", None)
    return subprocess.run(
        argv, cwd=REPO_ROOT, env=environment, capture_output=True, text=True, timeout=300,
        check=False,
    )


def _values(path: Path, column: str) -> list[datetime]:
    with duckdb.connect() as con:
        rows = con.execute(f"select {column} from read_parquet('{path.as_posix()}')").fetchall()
    return [row[0] for row in rows]


# 22:30Z in summer and 23:30Z in winter: the last two hours (CEST) and the last hour (CET) of
# a UTC day, where a shifted value also lands on the next calendar day.
_WRITE_UNDER_TZ = """
import sys
from datetime import UTC, datetime
from pathlib import Path
from cyclebeat import lake
from cyclebeat.app_store import RawFeedback

summer = datetime(2026, 7, 10, 22, 30, tzinfo=UTC)
winter = datetime(2026, 12, 10, 23, 30, tzinfo=UTC)
rows = [
    RawFeedback(session_id="summer", rating="up", created_at=summer),
    RawFeedback(session_id="winter", rating="up", created_at=winter),
]
lake.write_partition(rows, lake.FEEDBACK, "2026-12-10", root=Path(sys.argv[1]))
"""


def test_an_aware_utc_timestamp_reads_back_unchanged_under_a_non_utc_tz(tmp_path: Path) -> None:
    result = _run_under(PARIS, [sys.executable, "-c", _WRITE_UNDER_TZ, str(tmp_path)])
    assert result.returncode == 0, result.stderr[-4000:]

    part = lake.partition_dir(lake.FEEDBACK, "2026-12-10", tmp_path) / "part.parquet"
    with duckdb.connect() as con:
        back = dict(con.execute(
            "select session_id, created_at from read_parquet(?)", [part.as_posix()]
        ).fetchall())
        days = dict(con.execute(
            "select session_id, cast(date_trunc('day', created_at) as date) "
            "from read_parquet(?)", [part.as_posix()]
        ).fetchall())

    assert back == {
        "summer": datetime(2026, 7, 10, 22, 30),
        "winter": datetime(2026, 12, 10, 23, 30),
    }
    # What `stg_sessions.session_date` and `stg_feedback.feedback_date` compute.
    assert days == {"summer": date(2026, 7, 10), "winter": date(2026, 12, 10)}


def test_the_lake_writer_refuses_a_naive_timestamp(tmp_path: Path) -> None:
    """A naive value has no zone to convert from: it is refused, never assumed."""
    row = RawFeedback(session_id="s1", rating="up", created_at=datetime(2026, 7, 10, 22, 30))
    try:
        lake.write_partition([row], lake.FEEDBACK, "2026-07-10", root=tmp_path)
    except ValueError as error:
        assert "created_at" in str(error)
    else:
        raise AssertionError("a naive created_at was written to the lake")
    assert not (tmp_path / lake.FEEDBACK).exists()


def test_an_aware_non_utc_timestamp_is_written_as_its_utc_instant(tmp_path: Path) -> None:
    plus_two = timezone(timedelta(hours=2))
    row = RawFeedback(
        session_id="s1",
        rating="up",
        created_at=datetime(2026, 7, 29, 17, 43, 42, tzinfo=plus_two),
    )
    lake.write_partition([row], lake.FEEDBACK, "2026-07-29", root=tmp_path)

    part = lake.partition_dir(lake.FEEDBACK, "2026-07-29", tmp_path) / "part.parquet"
    assert _values(part, "created_at") == [
        datetime(2026, 7, 29, 15, 43, 42, tzinfo=UTC).replace(tzinfo=None)
    ]
