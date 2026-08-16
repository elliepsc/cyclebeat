"""dag_build_warehouse — load_duckdb <- lake -> dbt_build (E.5).

`load_duckdb` replays the whole lake into DuckDB (full replace from the partitions, so it is
idempotent) and materializes the E.2 verdict from `cyclebeat.e2`. `dbt_build` then runs
`dbt build` as a BashOperator, exactly as E.5 specifies.

This is the DAG `test_dag_build_warehouse_runs_on_demo_lake` exercises end to end with
`dag.test()` against the committed demo lake — no scheduler, no network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = PROJECT_ROOT / "dbt"


@dag(
    dag_id="dag_build_warehouse",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 8, 1, tz="UTC"),
    catchup=False,
    tags=["cyclebeat", "phase-2", "warehouse"],
    doc_md=__doc__,
)
def dag_build_warehouse() -> None:
    @task(task_id="load_duckdb")
    def load_duckdb() -> dict[str, int]:
        """Lake -> DuckDB raw layer + the materialized E.2 verdict dbt reads."""
        from cyclebeat.warehouse import load_lake

        return load_lake()

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {PROJECT_ROOT.as_posix()} && "
            f"dbt build --project-dir {DBT_DIR.as_posix()} "
            f"--profiles-dir {DBT_DIR.as_posix()}"
        ),
        env={**os.environ},
        # No retry: a failing dbt test is a data-contract violation to fix, never a flake
        # to paper over. E.5 puts retries on extraction tasks only.
        retries=0,
    )

    load_duckdb() >> dbt_build


dag_build_warehouse()
