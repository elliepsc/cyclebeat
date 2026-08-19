"""The three DAG tests named by E.5, in the same commit as the DAGs.

E.5 requires exactly these, and requires that no scheduler is ever started in CI:

    test_all_dags_import_without_error
    test_dag_build_warehouse_runs_on_demo_lake   (dag.test())
    test_resolve_dag_idempotent_on_same_dt       (re-run same dt -> zero duplicates)

**Platform gate, not a skipped test.** Apache Airflow does not support Windows: importing it
there dies on `os.register_at_fork`, which is POSIX-only. These tests therefore run on Linux
— CI (`ubuntu-latest`) and the WSL environment the README documents as the recommended dev
setup — and are marked as inapplicable on win32. Nothing is being bypassed: on every platform
that can host the dependency, they run and must pass.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Apache Airflow does not support Windows (os.register_at_fork is POSIX-only); "
    "run the suite from WSL or Linux - see README, 'Development environment'.",
)

DAGS_DIR = Path(__file__).resolve().parent.parent / "dags"
EXPECTED_DAG_IDS = {"dag_ingest", "dag_resolve_bpm", "dag_build_warehouse"}


@pytest.fixture()
def dagbag(airflow_db):
    from airflow.models.dagbag import DagBag

    return DagBag(dag_folder=str(DAGS_DIR), include_examples=False)


def test_all_dags_import_without_error(dagbag) -> None:
    """No import error in any DAG file, and all three E.5 DAGs are present.

    Asserting the ids too, not just the absence of errors: a DAG file that silently defines
    nothing imports perfectly well and would pass a bare error check.
    """
    assert dagbag.import_errors == {}, f"DAG import errors: {dagbag.import_errors}"
    assert EXPECTED_DAG_IDS.issubset(set(dagbag.dag_ids))


def test_dags_serialise_their_runs(dagbag) -> None:
    """Every DAG caps itself at one active run. Regression test for a real failure.

    On 2026-08-19, `load_duckdb` failed with `Could not set lock on file
    cyclebeat_runtime.duckdb: Conflicting lock is held`. The Airflow metadata DB showed two
    runs of dag_build_warehouse -- one `scheduled__`, one `manual__` -- entering that task
    within the same millisecond. DuckDB allows a single writer, so one run aborted the other.
    The same race applies to the lake DAGs: `write_partition` replaces a partition wholesale
    rather than appending, so two overlapping runs interleave over the same `dt=` directory.
    """
    for dag_id in sorted(EXPECTED_DAG_IDS):
        dag = dagbag.get_dag(dag_id)
        assert dag.max_active_runs == 1, (
            f"{dag_id} allows {dag.max_active_runs} concurrent runs; the warehouse and the "
            "lake are both single-writer."
        )


def test_dag_ingest_has_no_jamendo_branch(dagbag) -> None:
    """ADR-005 dropped `extract_jamendo` from E.5's dag_ingest. Guard the removal.

    Phase 1 amended the appendix; this is the executable half of that decision.
    """
    dag = dagbag.get_dag("dag_ingest")
    task_ids = set(dag.task_ids)
    assert "extract_jamendo" not in task_ids
    assert {"extract_deezer", "extract_csv", "write_lake_parquet"} == task_ids


def test_dag_build_warehouse_runs_on_demo_lake(tmp_path, monkeypatch, airflow_db) -> None:
    """`dag.test()` end to end against the committed demo lake — no scheduler, no network.

    The demo lake is built from `data/spike/raw_output.json`, which is committed, so this
    consumes no API quota and needs neither audio nor librosa (E.8).
    """
    from airflow.models.dagbag import DagBag

    from cyclebeat.cli import main as cli_main

    # The DAG's load task resolves the lake relative to the working directory, so the lake
    # is built at exactly the path it will look in, and the test then chdirs there.
    lake_root = tmp_path / "lake"
    db_path = tmp_path / "warehouse.duckdb"
    assert cli_main(["--lake", str(lake_root), "ingest"]) == 0

    monkeypatch.setenv("RUNTIME_DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)

    dag = DagBag(dag_folder=str(DAGS_DIR), include_examples=False).get_dag("dag_build_warehouse")
    # dbt is exercised by `make dbt` in its own step; running it inside dag.test() would
    # make this test depend on a dbt profile and a warm project dir. The load task is the
    # part that carries the E.2 contract, so that is what is asserted here.
    dag.test(run_conf={}, use_executor=False)

    import duckdb

    con = duckdb.connect(str(db_path))
    try:
        tracks = con.execute("select count(*) from raw_tracks").fetchone()
        resolved = con.execute("select count(*) from raw_resolved").fetchone()
    finally:
        con.close()
    assert tracks and tracks[0] > 0
    assert resolved and resolved[0] == tracks[0]


def test_resolve_dag_idempotent_on_same_dt(tmp_path) -> None:
    """Re-running the same `dt` must produce zero duplicates (E.5 key: track_id+source+dt).

    Exercises the real idempotency mechanism — `lake.write_partition` overwriting a
    partition plus `deduplicate` collapsing a batch — rather than a mocked stand-in.
    """
    from cyclebeat import lake
    from cyclebeat.demo import SNAPSHOT_DT, build_demo_batch
    from cyclebeat.resolve import deduplicate

    _, resolutions = build_demo_batch()
    dt: date = SNAPSHOT_DT

    for _ in range(3):
        lake.write_partition(deduplicate(resolutions, dt), lake.RESOLUTIONS, dt, tmp_path)

    rows = lake.read_dataset(lake.RESOLUTIONS, tmp_path)
    keys = [(str(row["track_id"]), str(row["source"]), str(row["dt"])) for row in rows]
    assert len(keys) == len(set(keys)), "re-running the same dt duplicated resolutions"
    assert len(rows) == len(deduplicate(resolutions, dt))
