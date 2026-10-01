"""CycleBeat runtime DuckDB — the cycling-pattern knowledge base.

**Patterns only.** Sessions and feedback used to live here too; ADR-009 moved them to the
transactional store (`api/repositories/`), and the warehouse now receives them through the
lake like every other dataset. What remains is the phase-0 ingestion of the 40-pattern KB,
which `ingest/ingest_pipeline.py` calls.

The session and feedback helpers that used to sit below were deleted rather than left: they
had no callers after the contract-first rewrite, and `save_feedback` was actively BROKEN —
adding `session_id` to the table left its positional `INSERT ... VALUES (?, ?, ?, now())`
supplying four values for five columns. Dead code that raises is worse than no code, and
removing it makes ADR-008/009's claim that the SQL left this module actually true.
"""

import json
import os
from pathlib import Path

import duckdb

_DB_ENV = os.environ.get("RUNTIME_DB_PATH", "")
_DB_PATH = _DB_ENV if _DB_ENV else str(
    Path(__file__).parent.parent / "data" / "cyclebeat_runtime.duckdb"
)

_DDL_PATTERNS = """
    CREATE TABLE IF NOT EXISTS patterns (
        id             VARCHAR,
        pattern_type   VARCHAR,
        phase          VARCHAR,
        label          VARCHAR,
        bpm_min        DOUBLE,
        bpm_max        DOUBLE,
        energy_min     DOUBLE,
        energy_max     DOUBLE,
        loudness_min   DOUBLE,
        loudness_max   DOUBLE,
        resistance     INTEGER,
        cadence_target VARCHAR,
        effort         VARCHAR,
        duration_min_s INTEGER,
        duration_max_s INTEGER,
        instruction    VARCHAR,
        coach_tone     VARCHAR,
        tags           VARCHAR
    )
"""


def _open_rw():
    return duckdb.connect(_DB_PATH)



def init_db() -> None:
    con = _open_rw()
    try:
        con.execute(_DDL_PATTERNS)
    finally:
        con.close()


def save_patterns(patterns: list[dict]) -> None:
    """Upsert the full pattern knowledge base. Called once during ingestion."""
    init_db()
    con = _open_rw()
    try:
        con.execute("DELETE FROM patterns")
        for p in patterns:
            bpm = p.get("bpm_range", [0, 0])
            energy = p.get("energy_range", [0, 0])
            loudness = p.get("loudness_range", [0, 0])
            con.execute(
                "INSERT INTO patterns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    p.get("id", ""),
                    p.get("pattern_type", ""),
                    p.get("phase", ""),
                    p.get("label", ""),
                    float(bpm[0]) if len(bpm) > 0 else 0.0,
                    float(bpm[1]) if len(bpm) > 1 else 0.0,
                    float(energy[0]) if len(energy) > 0 else 0.0,
                    float(energy[1]) if len(energy) > 1 else 0.0,
                    float(loudness[0]) if len(loudness) > 0 else 0.0,
                    float(loudness[1]) if len(loudness) > 1 else 0.0,
                    int(p.get("resistance", 0)),
                    str(p.get("cadence_target", "")),
                    p.get("effort", ""),
                    int(p.get("duration_min_s", 0)),
                    int(p.get("duration_max_s", 0)),
                    p.get("instruction", ""),
                    p.get("coach_tone", ""),
                    json.dumps(p.get("tags", [])),
                ],
            )
    finally:
        con.close()
