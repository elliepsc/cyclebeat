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
