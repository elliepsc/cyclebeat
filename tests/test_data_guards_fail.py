"""Each data guard fails on its own bad value, through the real chain (#60).

A guard that has only ever passed proves nothing. Each fixture below is valid except for one
value; `dbt build` on it must exit non-zero with exactly one `FAIL` line, the guard's own.
`build` is right here, unlike in `tests/test_reference_warehouse.py`: a failing test skips
the models downstream, so no other test can fail on the same cause.

The unknown `effort` goes through the real dlt loader (`ingest.ingest_pipeline.run`) pointed at
a fixture file, since patterns do not go through the lake. Sessions and feedback go through
the lake and the CLI loader, like the app store's.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests import chain

SESSION_MARTS = "+mart_feedback_summary +mart_recent_activity +mart_session_kpis"

# Two patterns, the shape of `data/cycling_patterns.json`: one mapped effort, one not.
PATTERNS = [
    {
        "id": "warmup_01", "pattern_type": "warmup", "phase": "warmup", "label": "Easy spin",
        "bpm_range": [90, 105], "energy_range": [0.2, 0.4], "loudness_range": [-20.0, -10.0],
        "resistance": 2, "cadence_target": "80-90", "effort": "easy",
        "duration_min_s": 120, "duration_max_s": 300, "instruction": "Settle in, breathe.",
        "coach_tone": "calm", "tags": ["warmup", "spin"],
    },
    {
        "id": "climb_99", "pattern_type": "climb", "phase": "main", "label": "Seated climb",
        "bpm_range": [125, 140], "energy_range": [0.6, 0.8], "loudness_range": [-8.0, -4.0],
        "resistance": 7, "cadence_target": "60-70", "effort": "brutal",
        "duration_min_s": 180, "duration_max_s": 420, "instruction": "Heavy gear, stay seated.",
        "coach_tone": "firm", "tags": ["climb", "strength"],
    },
]


def _assert_only_failure(result: subprocess.CompletedProcess[str], guard: str) -> None:
    failing = chain.failing_tests(result)
    assert result.returncode != 0, result.stdout[-4000:]
    assert len(failing) == 1 and guard in failing[0], result.stdout[-4000:]


@pytest.mark.parametrize(
    ("fixture", "guard"),
    [
        ("unknown_rating", "check_invalid_rating"),
        ("duration_out_of_bounds", "check_invalid_duration"),
    ],
)
def test_a_bad_app_store_value_fails_its_guard(tmp_path: Path, fixture: str, guard: str) -> None:
    lake_root = tmp_path / "lake"
    warehouse = tmp_path / "warehouse.duckdb"
    chain.write_lake("tests.guard_fixtures", lake_root, warehouse, tmp_path, fixture)
    chain.load(lake_root, warehouse, tmp_path)

    result = chain.dbt("build", warehouse, tmp_path, select=SESSION_MARTS)

    _assert_only_failure(result, guard)


def test_an_unknown_effort_fails_its_guard(tmp_path: Path) -> None:
    patterns = tmp_path / "cycling_patterns.json"
    patterns.write_text(json.dumps(PATTERNS), encoding="utf-8")
    warehouse = tmp_path / "warehouse.duckdb"
    chain.load_patterns(warehouse, tmp_path, patterns)

    result = chain.dbt("build", warehouse, tmp_path, select="+mart_pattern_coverage")

    _assert_only_failure(result, "check_invalid_pattern_buckets")
