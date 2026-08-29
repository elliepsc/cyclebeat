"""Data access. **The only place in `api/` where SQL is written** (E.0.5).

Layering (§7): `routers/` speak HTTP, `services/` hold the logic, and everything that touches
DuckDB lives here. A service never sees a connection and never sees a SQL string, which is
what lets `tests/unit/test_api_services.py` run the whole service layer against fakes with no
database at all.

E.2's dated note assigned this move to phase 4: the API used to write DuckDB best-effort from
`db/runtime.py` with the JSON file as the primary store. DuckDB is primary now, and the SQL
that did it has moved here.
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
