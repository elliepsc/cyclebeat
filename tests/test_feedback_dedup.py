"""Feedback indicators through the real chain, from a two-partition lake (#54).

`extract_to_lake` writes a FULL copy of the app-store feedback table into each day's `dt`
partition, so a feedback extracted on two days is in the lake twice. A dbt unit test cannot
carry `dt` past `stg_feedback` (it mocks a model's direct parents only, and the marts read
`stg_feedback`, which has no `dt`), so this test runs the chain itself: lake -> `load_lake` ->
`dbt build` on a temporary warehouse, then reads the three indicators the duplicate skewed.

The fixture is uneven on purpose. Session s1 was rated `up` on day 1 and `down` on day 2, and
the lake was extracted on both days: the old `up` sits in both partitions, the newer `down`
in one. Counting per partition gives s1 two `up` for one `down`, which moves both the counts
and the satisfaction ratio; counting the latest copy gives one of each.

Nothing here touches the real `data/` or `lake/`: the lake, the warehouse, dbt's target and
logs all live under `tmp_path`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb

from cyclebeat import lake
from cyclebeat.app_store import RawFeedback, RawSession
from cyclebeat.warehouse import load_lake

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
DAY_1 = date(2026, 10, 22)
DAY_2 = date(2026, 10, 23)


def _session(session_id: str, created_at: datetime) -> RawSession:
    return RawSession(
        session_id=session_id,
        level="beginner",
        goal="endurance",
        duration_min=30,
        verdict="safe",
        n_segments=6,
        duration_gap_s=0.0,
        created_at=created_at,
    )


def _feedback(session_id: str, rating: str, created_at: datetime) -> RawFeedback:
    return RawFeedback(
        session_id=session_id,
        session_title=f"session-{session_id}",
        rating=rating,
        note=None,
        created_at=created_at,
    )


def _two_day_lake(root: Path) -> None:
    """What two daily `extract_to_lake` runs leave behind, each a full copy of the store."""
    s1 = _session("s1", datetime(2026, 10, 22, 7, 0, 0))
    s2 = _session("s2", datetime(2026, 10, 23, 7, 0, 0))
    s1_up = _feedback("s1", "up", datetime(2026, 10, 22, 8, 0, 0, 123456))
    s1_down = _feedback("s1", "down", datetime(2026, 10, 23, 8, 0, 0, 654321))
    s2_up = _feedback("s2", "up", datetime(2026, 10, 23, 9, 0, 0, 1))

    lake.write_partition([s1], lake.SESSIONS, DAY_1, root=root)
    lake.write_partition([s1_up], lake.FEEDBACK, DAY_1, root=root)
    lake.write_partition([s1, s2], lake.SESSIONS, DAY_2, root=root)
    lake.write_partition([s1_up, s1_down, s2_up], lake.FEEDBACK, DAY_2, root=root)


def _dbt_build(
    warehouse: Path,
    work: Path,
    select: str = "+mart_feedback_summary +mart_session_kpis +mart_recent_activity",
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RUNTIME_DB_PATH": str(warehouse)}
    return subprocess.run(
        [
            str(Path(sys.executable).parent / "dbt"),
            "--no-use-colors",
            "build",
            "--project-dir", str(DBT_DIR),
            "--profiles-dir", str(DBT_DIR),
            "--target-path", str(work / "target"),
            "--log-path", str(work / "logs"),
            "--select", select,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def test_feedback_indicators_count_each_feedback_once(tmp_path: Path) -> None:
    lake_root = tmp_path / "lake"
    warehouse = tmp_path / "warehouse.duckdb"
    _two_day_lake(lake_root)
    load_lake(db_path=warehouse, lake_root=lake_root)

    result = _dbt_build(warehouse, tmp_path)
    assert result.returncode == 0, result.stdout[-4000:]

    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        summary = con.sql(
            "select rating, count, pct from mart_feedback_summary "
            "where rating_scale = 'satisfaction' order by rating"
        ).fetchall()
        feedback_count = dict(
            con.sql("select session_id, feedback_count from int_session_summary").fetchall()
        )
        kpis = con.sql("select avg_satisfaction_pct from mart_session_kpis").fetchone()
        recent = con.sql("select count(*) from mart_recent_activity").fetchone()
    finally:
        con.close()

    assert kpis is not None and recent is not None
    # One comparison, so a failure prints every indicator at once.
    assert {
        "mart_feedback_summary": summary,
        "int_session_summary.feedback_count": feedback_count,
        "mart_session_kpis.avg_satisfaction_pct": kpis[0],
        "mart_recent_activity rows": recent[0],
    } == {
        # Latest copy: s1 up, s1 down, s2 up.
        "mart_feedback_summary": [("down", 1, 33.33), ("up", 2, 66.67)],
        "int_session_summary.feedback_count": {"s1": 2, "s2": 1},
        # s1 50 %, s2 100 % -> 75.0.
        "mart_session_kpis.avg_satisfaction_pct": 75.0,
        # One row per feedback, not per extraction.
        "mart_recent_activity rows": 3,
    }


def test_recent_activity_key_test_fails_on_a_duplicated_feedback(tmp_path: Path) -> None:
    """The grain test is evidence only if it can fail: the same feedback twice in the latest
    partition (what a store holding a doubled insert would extract) must turn it red."""
    lake_root = tmp_path / "lake"
    warehouse = tmp_path / "warehouse.duckdb"
    s1 = _session("s1", datetime(2026, 10, 23, 7, 0, 0))
    twice = _feedback("s1", "up", datetime(2026, 10, 23, 8, 0, 0, 123456))
    lake.write_partition([s1], lake.SESSIONS, DAY_2, root=lake_root)
    lake.write_partition([twice, twice], lake.FEEDBACK, DAY_2, root=lake_root)
    load_lake(db_path=warehouse, lake_root=lake_root)

    result = _dbt_build(warehouse, tmp_path, select="+mart_recent_activity")

    assert result.returncode != 0
    failing = [line for line in result.stdout.splitlines() if " FAIL " in line]
    assert len(failing) == 1, result.stdout[-4000:]
    assert "check_recent_activity_grain" in failing[0]
