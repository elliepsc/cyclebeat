"""Phase 0 behaviour guards for the ingestion pipeline.

The v1 pipeline staged into DuckDB via dlt, then loaded vectors into the vector
store. That second step is gone (ADR-001); these tests pin what must survive:
the dlt source still yields the knowledge base, and the run still lands the
patterns in the DuckDB that dbt reads.
"""

import importlib
import json

import pytest


@pytest.fixture
def patterns_file(tmp_path):
    """A two-pattern knowledge base, so the test does not depend on the real 40."""
    payload = [
        {
            "id": "warmup_01",
            "pattern_type": "warmup",
            "phase": "warmup",
            "label": "Easy spin",
            "bpm_range": [90, 105],
            "energy_range": [0.2, 0.4],
            "loudness_range": [-20.0, -10.0],
            "resistance": 2,
            "cadence_target": "80-90",
            "effort": "easy",
            "duration_min_s": 120,
            "duration_max_s": 300,
            "instruction": "Settle in, breathe.",
            "coach_tone": "calm",
            "tags": ["warmup", "spin"],
        },
        {
            "id": "climb_01",
            "pattern_type": "climb",
            "phase": "main",
            "label": "Seated climb",
            "bpm_range": [125, 140],
            "energy_range": [0.6, 0.8],
            "loudness_range": [-8.0, -4.0],
            "resistance": 7,
            "cadence_target": "60-70",
            "effort": "hard",
            "duration_min_s": 180,
            "duration_max_s": 420,
            "instruction": "Heavy gear, stay seated.",
            "coach_tone": "firm",
            "tags": ["climb", "strength"],
        },
    ]
    path = tmp_path / "cycling_patterns.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_source_yields_every_pattern(patterns_file):
    from ingest.ingest_pipeline import cycling_patterns_source

    resources = list(cycling_patterns_source(str(patterns_file)).resources.values())
    assert len(resources) == 1
    rows = list(resources[0])
    assert [row["id"] for row in rows] == ["warmup_01", "climb_01"]


def test_run_stages_patterns_into_the_runtime_duckdb(patterns_file, tmp_path, monkeypatch):
    """dlt staging still runs and the patterns land in the DuckDB dbt reads."""
    import duckdb

    db_path = tmp_path / "runtime.duckdb"
    monkeypatch.setenv("RUNTIME_DB_PATH", str(db_path))
    monkeypatch.chdir(tmp_path)

    import db.runtime
    import ingest.ingest_pipeline

    importlib.reload(db.runtime)
    importlib.reload(ingest.ingest_pipeline)

    count = ingest.ingest_pipeline.run(str(patterns_file))
    assert count == 2

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute("SELECT id, phase FROM patterns ORDER BY id").fetchall()
    finally:
        con.close()
    assert rows == [("climb_01", "main"), ("warmup_01", "warmup")]

    importlib.reload(db.runtime)
    importlib.reload(ingest.ingest_pipeline)
