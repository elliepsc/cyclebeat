"""Run the real pipeline steps on a temporary warehouse, each in its own process (#60).

Every step runs as a subprocess with `TZ=UTC` set explicitly: the lake writes an aware UTC
timestamp in the DuckDB session time zone and drops the zone (#57), so on a host in
Europe/Paris the same row would come out two hours later, and every expected time with it.
The step is the real entry point (the CLI, the dlt pipeline, dbt), never a reimplementation.

Nothing here touches the real `data/` or `lake/`: the lake, the warehouse, dbt's target, logs
and profiles dir, and dlt's working files all live under the `work` directory given.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
PYTHON = sys.executable


def env(warehouse: Path, work: Path) -> dict[str, str]:
    environment = {
        **os.environ,
        "TZ": "UTC",
        "RUNTIME_DB_PATH": str(warehouse),
        "PYTHONPATH": str(REPO_ROOT),
        "DLT_DATA_DIR": str(work / "dlt"),
    }
    # The chain never reads the app store, and a configured one must not leak in.
    environment.pop("DATABASE_URL", None)
    return environment


def run(
    argv: list[str], warehouse: Path, work: Path, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd or REPO_ROOT,
        env=env(warehouse, work),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def checked(result: subprocess.CompletedProcess[str]) -> subprocess.CompletedProcess[str]:
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
    return result


def write_lake(module: str, lake_root: Path, warehouse: Path, work: Path) -> None:
    """Write a synthetic app-store lake with `python -m <module> <lake_root>`."""
    checked(run([PYTHON, "-m", module, str(lake_root)], warehouse, work))


def ingest_demo_tracks(lake_root: Path, warehouse: Path, work: Path) -> None:
    """Tracks and resolutions from the committed demo snapshot, offline (E.8)."""
    checked(run(
        [PYTHON, "-m", "cyclebeat.cli", "--lake", str(lake_root), "ingest"], warehouse, work
    ))


def load(lake_root: Path, warehouse: Path, work: Path) -> None:
    checked(run(
        [PYTHON, "-m", "cyclebeat.cli", "--lake", str(lake_root), "load", "--db", str(warehouse)],
        warehouse,
        work,
    ))


def load_patterns(warehouse: Path, work: Path, patterns_path: Path | None = None) -> None:
    """The real dlt loader (`ingest.ingest_pipeline.run`), on the real file or a fixture.

    `db/runtime.py` reads `RUNTIME_DB_PATH` at import, which a fresh process gets right; dlt's
    staging database lands in the working directory, hence `cwd=work`.
    """
    argument = "" if patterns_path is None else repr(str(patterns_path))
    code = f"from ingest.ingest_pipeline import run; run({argument})"
    work.mkdir(parents=True, exist_ok=True)
    checked(run([PYTHON, "-c", code], warehouse, work, cwd=work))


def dbt(
    command: str, warehouse: Path, work: Path, select: str | None = None
) -> subprocess.CompletedProcess[str]:
    profiles = work / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    shutil.copy(DBT_DIR / "profiles.yml", profiles / "profiles.yml")
    argv = [
        str(Path(PYTHON).parent / "dbt"),
        "--no-use-colors",
        command,
        "--project-dir", str(DBT_DIR),
        "--profiles-dir", str(profiles),
        "--target-path", str(work / "target"),
        "--log-path", str(work / "logs"),
    ]
    if select is not None:
        argv += ["--select", select]
    return run(argv, warehouse, work)


def failing_tests(result: subprocess.CompletedProcess[str]) -> list[str]:
    """The `FAIL` lines of a dbt run, one per failing test."""
    return [line for line in result.stdout.splitlines() if " FAIL " in line]
