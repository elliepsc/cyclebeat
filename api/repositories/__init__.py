"""Data access. **The only place in `api/` where SQL is written** (E.0.5).

Two stores, split by role per ADR-009:

* **Transactional** (`session.py`, `feedback.py`) — Postgres in compose and on Neon, SQLite on
  a bare clone. Small, frequent writes that must not be lost. See `database.py`.
* **Analytical** (`track.py`, `quality.py`) — read-only against the DuckDB warehouse that the
  lake and dbt build. See `warehouse.py`.

Keeping both behind the same package boundary is what lets a service depend on "a repository"
without knowing that two different engines are involved, and what let the store change in this
phase without touching a single service or service test.
"""

from api.repositories.feedback import FeedbackRepository
from api.repositories.quality import QualityRepository
from api.repositories.session import SessionRepository
from api.repositories.track import TrackRepository

__all__ = [
    "FeedbackRepository",
    "QualityRepository",
    "SessionRepository",
    "TrackRepository",
]
