"""The whole dbt project on the reference dataset (#60), through the real chain.

`tests/reference_dataset.py` is written as a two-partition lake, the demo snapshot adds the
tracks, the CLI loads the lake, the dlt pipeline loads the real pattern file, then dbt runs on
the temporary warehouse. That gives every data test rows to run on: before #60, on a copy of
the local warehouse (0 sessions, 0 feedback), 35 of the 78 data tests ran over empty models.

`dbt run` then `dbt test`, not `dbt build`: under `build` a failing data test skips everything
downstream, and a reconciliation below would then fail on a missing table instead of on its
own assertion.

Every expected value is computed by hand from the dataset, with its arithmetic, and was written
before the first run. The reconciliations compare a mart total to a count taken from the
Python dataset itself, not from another model.

`TZ=UTC` is set in every step's environment (`tests/chain.py`): the lake writes UTC time as
local time (#57), and `last_session_at` below is the UTC value.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from tests import chain
from tests import reference_dataset as ref


@dataclass(frozen=True)
class Warehouse:
    path: Path
    work: Path
    tested: Any  # the `dbt test` CompletedProcess


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Warehouse]:
    work = tmp_path_factory.mktemp("reference")
    lake_root = work / "lake"
    path = work / "warehouse.duckdb"

    chain.write_lake("tests.reference_dataset", lake_root, path, work)
    chain.ingest_demo_tracks(lake_root, path, work)
    chain.load(lake_root, path, work)
    chain.load_patterns(path, work)
    chain.checked(chain.dbt("run", path, work))
    tested = chain.dbt("test", path, work)
    yield Warehouse(path=path, work=work, tested=tested)


def _query(warehouse: Warehouse, sql: str) -> list[tuple[Any, ...]]:
    con = duckdb.connect(str(warehouse.path), read_only=True)
    try:
        return con.sql(sql).fetchall()
    finally:
        con.close()


def _scalar(warehouse: Warehouse, sql: str) -> Any:
    return _query(warehouse, sql)[0][0]


# The dataset's own counts, the oracle of the reconciliations.
DISTINCT_FEEDBACK = {
    (f.session_id, f.session_title, f.created_at)
    for partition in ref.FEEDBACK.values()
    for f in partition
}
DISTINCT_SESSIONS = {s.session_id for partition in ref.SESSIONS.values() for s in partition}
ATTACHED_FEEDBACK = {key for key in DISTINCT_FEEDBACK if key[0] in DISTINCT_SESSIONS}


def test_every_data_test_passes(warehouse: Warehouse) -> None:
    assert warehouse.tested.returncode == 0, warehouse.tested.stdout[-4000:]


def vacuous_tests(manifest: dict[str, Any], con: duckdb.DuckDBPyConnection) -> list[str]:
    """Data tests whose every tested model has 0 rows (the #60 method).

    A generic test tests its `attached_node`; a singular test, every model it depends on. A
    test that depends on no model (a source test) cannot be measured this way: it is reported
    too, rather than skipped.
    """
    rows: dict[str, int] = {}

    def count(node_id: str) -> int:
        if node_id not in rows:
            node = manifest["nodes"][node_id]
            rows[node_id] = int(
                con.sql(f'select count(*) from "{node["schema"]}"."{node["alias"]}"')
                .fetchall()[0][0]
            )
        return rows[node_id]

    vacuous = []
    for test_id, node in manifest["nodes"].items():
        if node["resource_type"] != "test":
            continue
        attached = node.get("attached_node")
        models = [attached] if attached else [
            dep for dep in node["depends_on"]["nodes"] if dep.startswith("model.")
        ]
        if not models:
            vacuous.append(f"{test_id} (tests no model)")
        elif all(count(model) == 0 for model in models):
            vacuous.append(test_id)
    return sorted(vacuous)


def test_no_data_test_runs_over_an_empty_model(warehouse: Warehouse) -> None:
    manifest = json.loads((warehouse.work / "target" / "manifest.json").read_text())
    n_tests = sum(1 for n in manifest["nodes"].values() if n["resource_type"] == "test")
    con = duckdb.connect(str(warehouse.path), read_only=True)
    try:
        vacuous = vacuous_tests(manifest, con)
    finally:
        con.close()
    # 78 data tests at #60's start, plus `check_feedback_enriched_grain` added by #60.
    assert n_tests == 79
    assert vacuous == []


def test_indicators_match_the_values_computed_by_hand(warehouse: Warehouse) -> None:
    kpis = _query(
        warehouse,
        "select total_sessions, avg_duration_min, total_tracks_used, sessions_flagged_review, "
        "avg_abs_duration_gap_s, last_session_at, avg_satisfaction_pct from mart_session_kpis",
    )
    summary = _query(
        warehouse,
        "select rating_scale, rating, count, pct from mart_feedback_summary "
        "order by rating_scale, rating",
    )
    per_session = _query(
        warehouse,
        "select session_id, feedback_count, satisfaction_pct from int_session_summary "
        "order by session_id",
    )
    # One comparison, so a failure prints every indicator at once.
    assert {
        "mart_session_kpis": kpis,
        "mart_feedback_summary": summary,
        "int_session_summary": per_session,
    } == {
        "mart_session_kpis": [(
            # total_sessions: A, B, C; A's copy in D1 and D2 counts once.
            3,
            # avg_duration_min: round((30 + 45 + 20) / 3, 1) = round(31.666..., 1).
            31.7,
            # total_tracks_used: 6 + 9 + 4.
            19,
            # sessions_flagged_review: B only.
            1,
            # avg_abs_duration_gap_s: (|30| + |-60| + |0|) / 3 = 90 / 3.
            30.0,
            # last_session_at: C, 2026-10-23 08:00 UTC (a UTC value only because TZ=UTC, #57).
            datetime(2026, 10, 23, 8, 0),
            # avg_satisfaction_pct: round(avg(A 50.0, B 75.0), 1); C has no satisfaction
            # rating, its NULL is skipped (0 would give 41.7).
            62.5,
        )],
        "mart_feedback_summary": [
            # effort: Great 1 (V1A), Hard 1 (V1B), 1 / 2 each.
            ("effort", "Great", 1, 50.0),
            ("effort", "Hard", 1, 50.0),
            # satisfaction: up = 1 (A) + 3 (B) = 4, down = 1 (A) + 1 (B) = 2, out of 6:
            # round(100 * 2 / 6, 2) = 33.33, round(100 * 4 / 6, 2) = 66.67.
            ("satisfaction", "down", 2, 33.33),
            ("satisfaction", "up", 4, 66.67),
        ],
        "int_session_summary": [
            # A: 2 feedback, round(100 * 1 / 2, 1). B: 4, round(100 * 3 / 4, 1).
            # C: no feedback, so 0 and NULL.
            (ref.SESSION_A, 2, 50.0),
            (ref.SESSION_B, 4, 75.0),
            (ref.SESSION_C, 0, None),
        ],
    }


def test_the_latest_copy_of_a_changed_session_wins(warehouse: Warehouse) -> None:
    """A's `duration_gap_s` is +45.0 on D1 and +30.0 on D2: the latest partition wins."""
    gap = _scalar(
        warehouse,
        f"select duration_gap_s from fct_session where session_id = '{ref.SESSION_A}'",
    )
    assert gap == 30.0


def test_feedback_summary_total_is_the_distinct_feedback(warehouse: Warehouse) -> None:
    """R1: 8 distinct feedback (F1, V1A and V1B are in both partitions, counted once)."""
    assert len(DISTINCT_FEEDBACK) == 8
    total = _scalar(warehouse, "select sum(count) from mart_feedback_summary")
    assert total == len(DISTINCT_FEEDBACK)


def test_total_sessions_is_the_distinct_sessions(warehouse: Warehouse) -> None:
    """R2: 3 distinct session_id in the lake (A is in both partitions, with two values)."""
    assert len(DISTINCT_SESSIONS) == 3
    total = _scalar(warehouse, "select total_sessions from mart_session_kpis")
    assert total == len(DISTINCT_SESSIONS)


def test_session_summary_counts_the_feedback_attached_by_session_id(
    warehouse: Warehouse,
) -> None:
    """R3: `int_session_summary` attaches by `session_id` only: A 2 + B 4 + C 0 = 6; the two
    v1 rows (NULL `session_id`) are attached to nothing."""
    assert len(ATTACHED_FEEDBACK) == 6
    total = _scalar(warehouse, "select sum(feedback_count) from int_session_summary")
    assert total == len(ATTACHED_FEEDBACK)


def test_both_feedback_models_attach_the_same_way(warehouse: Warehouse) -> None:
    """R4: the feedback `int_feedback_enriched` gives a session context (`level`, not NULL
    in `stg_sessions`) are exactly those `int_session_summary` counts: 6. V1B, whose title
    equals session A's id, is not one of them (#60)."""
    with_context = _scalar(
        warehouse, "select count(*) from int_feedback_enriched where level is not null"
    )
    attached = _scalar(warehouse, "select sum(feedback_count) from int_session_summary")
    assert (with_context, attached) == (len(ATTACHED_FEEDBACK), len(ATTACHED_FEEDBACK))


def test_feedback_enrichment_keeps_one_row_per_feedback(warehouse: Warehouse) -> None:
    """R5: the session join does not fan out: 8 rows, one per distinct feedback."""
    rows = _scalar(warehouse, "select count(*) from int_feedback_enriched")
    assert rows == len(DISTINCT_FEEDBACK)


def test_recent_activity_holds_every_feedback_under_its_limit(warehouse: Warehouse) -> None:
    """R6: 8 distinct feedback, fewer than the mart's 20, so all of them, once."""
    rows = _scalar(warehouse, "select count(*) from mart_recent_activity")
    assert rows == min(20, len(DISTINCT_FEEDBACK))
