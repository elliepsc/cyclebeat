"""The suite must never touch the real transactional store (see tests/conftest.py)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from api.repositories import SessionRepository
from api.repositories import database as db_module

REAL_APP_DB = Path(__file__).resolve().parents[2] / "data" / "cyclebeat_app.db"


def _fingerprint() -> tuple[bool, int, int]:
    if not REAL_APP_DB.exists():
        return (False, 0, 0)
    stat = REAL_APP_DB.stat()
    return (True, stat.st_size, stat.st_mtime_ns)


def test_the_store_is_redirected_away_from_the_real_database() -> None:
    assert "DATABASE_URL" not in os.environ
    assert db_module.is_postgres() is False
    assert Path(os.environ["APP_DB_PATH"]).resolve() != REAL_APP_DB.resolve()


def test_a_write_through_the_repository_leaves_the_real_database_untouched() -> None:
    before = _fingerprint()
    SessionRepository().save(
        {
            "session_id": "isolation-probe",
            "level": "advanced",
            "goal": "intervals",
            "duration_min": 45,
            "verdict": "safe",
            "segments": [],
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    assert SessionRepository().exists("isolation-probe")
    assert _fingerprint() == before
