"""The reference dataset (#60): a small synthetic app store, as the lake holds it.

Every case is here for one thing it proves; `tests/test_reference_warehouse.py` reads the marts
it produces and compares them to values computed by hand. The rows are what two daily
`extract_to_lake` runs leave behind: each `dt` partition is a FULL copy of the store at that
day, so a row that already existed on day 1 is in both partitions.

Timestamps are aware UTC values, as the store returns them (`datetime.now(UTC)` on insert), and
the lake stores them as UTC whatever the process `TZ`: `python -m tests.reference_dataset
<lake_root>`.

Session ids are UUID-shaped like the API's; feedback titles follow the API's derived label
(`session-<first 8 of the id>`, `api/services/session.py`, `_title_for`).
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cyclebeat import lake
from cyclebeat.app_store import RawFeedback, RawSession

DAY_1 = date(2026, 10, 22)
DAY_2 = date(2026, 10, 23)

SESSION_A = "aaaaaaaa-0000-4000-8000-000000000001"
SESSION_B = "bbbbbbbb-0000-4000-8000-000000000002"
SESSION_C = "cccccccc-0000-4000-8000-000000000003"


def _at(month: int, day: int, hour: int, minute: int = 0, micro: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, 0, micro, tzinfo=UTC)


# A: in both partitions, and changed between them: the store upserts a session
# (`api/repositories/session.py`, `save`, ON CONFLICT DO UPDATE), so a later extraction can
# carry new values. Only `duration_gap_s` differs (+45.0 on D1, +30.0 on D2); stg_sessions
# keeps the latest copy. B: verdict `review`, negative gap. C: no feedback at all
# (feedback_count 0, satisfaction_pct NULL).
A = RawSession(
    session_id=SESSION_A, level="beginner", goal="endurance", duration_min=30,
    verdict="safe", n_segments=6, duration_gap_s=30.0, created_at=_at(10, 22, 7),
)
A_ON_DAY_1 = A.model_copy(update={"duration_gap_s": 45.0})
B = RawSession(
    session_id=SESSION_B, level="intermediate", goal="intervals", duration_min=45,
    verdict="review", n_segments=9, duration_gap_s=-60.0, created_at=_at(10, 23, 7),
)
C = RawSession(
    session_id=SESSION_C, level="advanced", goal="recovery", duration_min=20,
    verdict="safe", n_segments=4, duration_gap_s=0.0, created_at=_at(10, 23, 8),
)


def _api(session_id: str, rating: str, created_at: datetime) -> RawFeedback:
    return RawFeedback(
        session_id=session_id,
        session_title=f"session-{session_id[:8]}",
        rating=rating,
        note=None,
        created_at=created_at,
    )


# f1 is the same feedback in two partitions. A: 1 up / 1 down. B: 3 up / 1 down.
F1 = _api(SESSION_A, "up", _at(10, 22, 8, 0, 123456))
F2 = _api(SESSION_A, "down", _at(10, 23, 8, 0, 654321))
F3 = _api(SESSION_B, "up", _at(10, 23, 9, 0, 1))
F4 = _api(SESSION_B, "up", _at(10, 23, 9, 10))
F5 = _api(SESSION_B, "up", _at(10, 23, 9, 20))
F6 = _api(SESSION_B, "down", _at(10, 23, 9, 30))

# v1 rows: no `session_id`, the `effort` scale. No current code path writes one (#60 plan,
# step 0); they stay as a safeguard. V1B's title equals an existing session_id: it must still
# get no session context, so both feedback models attach the same way.
V1A = RawFeedback(
    session_id=None, session_title="Sunday hill ride", rating="Great", note=None,
    created_at=_at(4, 20, 10),
)
V1B = RawFeedback(
    session_id=None, session_title=SESSION_A, rating="Hard", note=None,
    created_at=_at(4, 21, 10),
)

SESSIONS: dict[date, list[RawSession]] = {
    DAY_1: [A_ON_DAY_1],
    DAY_2: [A, B, C],
}
FEEDBACK: dict[date, list[RawFeedback]] = {
    DAY_1: [V1A, V1B, F1],
    DAY_2: [V1A, V1B, F1, F2, F3, F4, F5, F6],
}


def write_lake(root: Path) -> None:
    for dt, sessions in SESSIONS.items():
        lake.write_partition(sessions, lake.SESSIONS, dt, root=root)
    for dt, feedback in FEEDBACK.items():
        lake.write_partition(feedback, lake.FEEDBACK, dt, root=root)


if __name__ == "__main__":
    write_lake(Path(sys.argv[1]))
