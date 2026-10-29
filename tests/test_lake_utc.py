"""The lake stores UTC, whatever the time zone of the process that writes it (#57).

Before #57, an aware UTC value went into a DuckDB `TIMESTAMP` column through the session time
zone, which DuckDB takes from the process `TZ`: on a host in Europe/Paris the lake held local
wall time, +2 h in summer and +1 h in winter. Reading back is time-zone independent (the Parquet
column is `isAdjustedToUTC=0`), so only the WRITE has to run under a non-UTC `TZ`, and it runs in
a subprocess: DuckDB reads the zone when it loads, not when a test changes `os.environ`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

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


# ── A partition written before #57 ──────────────────────────────────────────────────────

PRE_57_LAKE = REPO_ROOT / "tests" / "fixtures" / "pre_57_lake"
PRE_57_WALL_TIME = datetime(2026, 7, 29, 17, 43, 42)  # 15:43:42Z written as Paris time
SNAPSHOT_UTC = datetime(2026, 7, 29, 15, 43, 42)


def test_a_pre_57_partition_rewritten_for_the_same_dt_keeps_no_old_row(tmp_path: Path) -> None:
    """The re-extraction the owner runs on the real lake, on a copy of the real partitions.

    The demo ingest rewrites `dt=2026-07-29` under a non-UTC `TZ`. The replacement must be
    whole: one file per partition, every row at the UTC instant, none left at the old value.
    """
    lake_root = tmp_path / "lake"
    shutil.copytree(PRE_57_LAKE / "raw", lake_root / "raw")
    before = {
        dataset: len(_values(lake.partition_dir(dataset, "2026-07-29", lake_root)
                             / "part.parquet", column))
        for dataset, column in ((lake.TRACKS, "ingested_at"), (lake.RESOLUTIONS, "resolved_at"))
    }
    assert set(_values(
        lake.partition_dir(lake.TRACKS, "2026-07-29", lake_root) / "part.parquet", "ingested_at"
    )) == {PRE_57_WALL_TIME}

    result = _run_under(
        PARIS, [sys.executable, "-m", "cyclebeat.cli", "--lake", str(lake_root), "ingest"]
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]

    for dataset, column in ((lake.TRACKS, "ingested_at"), (lake.RESOLUTIONS, "resolved_at")):
        partition = lake.partition_dir(dataset, "2026-07-29", lake_root)
        assert [path.name for path in partition.iterdir()] == ["part.parquet"]
        values = _values(partition / "part.parquet", column)
        assert len(values) == before[dataset]
        assert set(values) == {SNAPSHOT_UTC}, f"{dataset}: an old-format row is left"


# ── An unreadable date fails the extraction ─────────────────────────────────────────────

_GOOD_SESSION = ("s1", "advanced", "intervals", 45, "safe", 1, -12.0, "2026-10-23T07:00:00+00:00")


Row = tuple[object, ...]


def _store_rows(sessions: list[Row], feedback: list[Row]) -> Callable[[str], list[Row]]:
    """Stand-in for `app_store._rows`: what each SELECT of the store would return."""

    def rows(sql: str) -> list[Row]:
        return list(sessions) if "from sessions" in sql else list(feedback)

    return rows


@pytest.mark.parametrize("value", ["not-a-date", "", None, 42])
def test_an_unreadable_session_date_fails_the_extraction(
    value: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cyclebeat import app_store

    bad = ("s2", "advanced", "intervals", 45, "safe", 1, 0.0, value)
    monkeypatch.setattr(app_store, "_rows", _store_rows([_GOOD_SESSION, bad], []))

    with pytest.raises(ValueError) as error:
        app_store.extract_to_lake(dt=date(2026, 10, 23), root=tmp_path)
    assert "s2" in str(error.value)
    assert repr(value) in str(error.value)
    assert not (tmp_path / lake.SESSIONS).exists()


def test_an_unreadable_feedback_date_writes_no_partition_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sessions are readable, the feedback is not: nothing is written, not even sessions."""
    from cyclebeat import app_store

    bad = ("s1", "session-s1", "up", None, "not-a-date")
    monkeypatch.setattr(app_store, "_rows", _store_rows([_GOOD_SESSION], [bad]))

    with pytest.raises(ValueError) as error:
        app_store.extract_to_lake(dt=date(2026, 10, 23), root=tmp_path)
    assert "s1" in str(error.value)
    assert "'not-a-date'" in str(error.value)
    assert not (tmp_path / lake.SESSIONS).exists()
    assert not (tmp_path / lake.FEEDBACK).exists()


def test_the_cli_exits_non_zero_and_names_the_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cyclebeat import app_store, cli

    bad = ("s2", "advanced", "intervals", 45, "safe", 1, 0.0, "not-a-date")
    monkeypatch.setattr(app_store, "_rows", _store_rows([_GOOD_SESSION, bad], []))

    code = cli.main(["--lake", str(tmp_path), "extract-app"])

    assert code != 0
    assert "s2" in capsys.readouterr().err
    assert not (tmp_path / lake.SESSIONS).exists()
