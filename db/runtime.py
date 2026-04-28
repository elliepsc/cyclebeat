"""
CycleBeat Runtime Database — DuckDB persistence for sessions and feedback.

Provides the SQL foundation for dbt models (staging → intermediate → marts).
Tables written here by the API are the raw source layer for dbt transforms.
"""

import json
import os
from pathlib import Path

import duckdb

_DB_ENV = os.environ.get("RUNTIME_DB_PATH", "")
_DB_PATH = _DB_ENV if _DB_ENV else str(
    Path(__file__).parent.parent / "data" / "cyclebeat_runtime.duckdb"
)

_DDL_SESSIONS = """
    CREATE TABLE IF NOT EXISTS sessions (
        title        VARCHAR,
        playlist_url VARCHAR,
        created_at   TIMESTAMP DEFAULT now(),
        duration_s   DOUBLE,
        track_count  INTEGER,
        session_json VARCHAR
    )
"""

_DDL_FEEDBACK = """
    CREATE TABLE IF NOT EXISTS feedback (
        session_title VARCHAR,
        rating        VARCHAR,
        note          VARCHAR,
        created_at    TIMESTAMP DEFAULT now()
    )
"""

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


def _open_ro():
    try:
        return duckdb.connect(_DB_PATH, read_only=True)
    except Exception:
        return duckdb.connect(_DB_PATH)


def init_db() -> None:
    con = _open_rw()
    try:
        con.execute(_DDL_SESSIONS)
        con.execute(_DDL_FEEDBACK)
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


def save_session(session: dict, playlist_url: str = "") -> None:
    init_db()
    con = _open_rw()
    try:
        con.execute(
            "INSERT INTO sessions VALUES (?, ?, now(), ?, ?, ?)",
            [
                session.get("session", {}).get("title", ""),
                playlist_url,
                session.get("session", {}).get("total_duration_s", 0.0),
                len(session.get("tracks", [])),
                json.dumps(session, ensure_ascii=False),
            ],
        )
    finally:
        con.close()


def save_feedback(session_title: str, rating: str, note: str) -> None:
    init_db()
    con = _open_rw()
    try:
        con.execute(
            "INSERT INTO feedback VALUES (?, ?, ?, now())",
            [session_title, rating, note or ""],
        )
    finally:
        con.close()


def get_feedback() -> list[dict]:
    init_db()
    con = _open_ro()
    try:
        rows = con.execute(
            "SELECT session_title, rating, note, created_at "
            "FROM feedback ORDER BY created_at"
        ).fetchall()
    finally:
        con.close()
    return [
        {"session": r[0], "rating": r[1], "note": r[2] or "", "timestamp": str(r[3])}
        for r in rows
    ]


def get_sessions() -> list[dict]:
    init_db()
    con = _open_ro()
    try:
        rows = con.execute(
            "SELECT title, playlist_url, created_at, duration_s, track_count "
            "FROM sessions ORDER BY created_at DESC"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "title": r[0],
            "playlist_url": r[1],
            "created_at": str(r[2]),
            "duration_s": r[3],
            "track_count": r[4],
        }
        for r in rows
    ]
