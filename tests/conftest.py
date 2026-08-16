"""Test configuration.

The Airflow bits below must run BEFORE anything imports `airflow`: Airflow reads
`AIRFLOW_HOME` and its config at import time, so setting them from inside a test would be
too late and would silently write a `airflow.db` into the repo root.

Nothing here is Airflow-specific for the rest of the suite — on Windows, where Airflow
cannot be imported at all, none of this does anything beyond setting two env vars.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# A throwaway AIRFLOW_HOME per test session, on the local filesystem. Without this Airflow
# defaults to ~/airflow and would persist a metadata DB between runs — which is exactly how
# a test suite starts passing for reasons unrelated to the code.
_AIRFLOW_HOME = Path(tempfile.gettempdir()) / "cyclebeat-airflow-test"
_AIRFLOW_HOME.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("AIRFLOW_HOME", str(_AIRFLOW_HOME))
os.environ.setdefault(
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
    f"sqlite:///{(_AIRFLOW_HOME / 'airflow.db').as_posix()}",
)
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", str(REPO_ROOT / "dags"))
# LocalExecutor needs a real DB and a running scheduler; E.5 forbids starting one in CI, so
# dag.test() runs tasks in-process under the sequential path instead.
os.environ.setdefault("AIRFLOW__CORE__EXECUTOR", "LocalExecutor")
os.environ.setdefault("CYCLEBEAT_DEMO", "1")


@pytest.fixture(scope="session")
def airflow_db() -> None:
    """Initialize the Airflow metadata DB once per session.

    `dag.test()` creates a real DagRun through `_get_or_create_dagrun`, so it needs the
    metadata schema to exist. Without this the DAG tests fail on a missing table rather
    than on anything to do with CycleBeat.
    """
    if sys.platform == "win32":  # pragma: no cover - Airflow cannot be imported here
        pytest.skip("Airflow does not support Windows")

    from airflow.utils.db import initdb

    initdb()
