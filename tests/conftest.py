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
from collections.abc import Iterator
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


# ── Store isolation ─────────────────────────────────────────────────────────────────────
# The API's transactional store defaults to data/cyclebeat_app.db, and a developer may have
# DATABASE_URL exported for compose. Without this, any test that drives the app (the contract
# suite, the service tests) writes real sessions into that store -- and `make ingest` then
# carries them into the warehouse, so the dbt result depends on what the tests happened to do.
REAL_APP_DB = REPO_ROOT / "data" / "cyclebeat_app.db"


def _fingerprint(path: Path) -> tuple[bool, int, int]:
    if not path.exists():
        return (False, 0, 0)
    stat = path.stat()
    return (True, stat.st_size, stat.st_mtime_ns)


_REAL_APP_DB_AT_START = _fingerprint(REAL_APP_DB)


@pytest.fixture(autouse=True, scope="session")
def _isolated_app_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """No DATABASE_URL, and a throwaway SQLite file, for the whole suite."""
    path = tmp_path_factory.mktemp("app-store") / "app.db"
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv("DATABASE_URL", raising=False)
        patch.setenv("APP_DB_PATH", str(path))
        yield path


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the run if anything wrote to the real app store, whatever the test did."""
    if _fingerprint(REAL_APP_DB) != _REAL_APP_DB_AT_START:
        print(f"\nFAILED: the suite modified {REAL_APP_DB}; a test escaped store isolation")
        session.exitstatus = 1
