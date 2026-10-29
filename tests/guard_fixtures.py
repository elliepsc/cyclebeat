"""Lakes that a data guard must reject (#60), one per guard.

Run as `python -m tests.guard_fixtures <lake_root> <fixture>`, like
`tests/reference_dataset.py`. Each fixture is a valid store except for one row, so the
guard it targets is the only test that can fail on it.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from pathlib import Path

from cyclebeat import lake
from cyclebeat.app_store import RawFeedback, RawSession

DT = date(2026, 10, 23)
SESSION = "dddddddd-0000-4000-8000-000000000004"


def _session(duration_min: int) -> RawSession:
    return RawSession(
        session_id=SESSION, level="beginner", goal="endurance", duration_min=duration_min,
        verdict="safe", n_segments=6, duration_gap_s=0.0,
        created_at=datetime(2026, 10, 23, 7, 0, tzinfo=UTC),
    )


def unknown_rating(root: Path) -> None:
    """A rating on neither scale: `rating_scale` = 'unknown', which `check_invalid_rating`
    fails (never put into the `else` of a real scale)."""
    lake.write_partition([_session(30)], lake.SESSIONS, DT, root=root)
    lake.write_partition(
        [RawFeedback(
            session_id=SESSION, session_title=f"session-{SESSION[:8]}", rating="meh",
            note=None, created_at=datetime(2026, 10, 23, 8, 0, tzinfo=UTC),
        )],
        lake.FEEDBACK, DT, root=root,
    )


def duration_out_of_bounds(root: Path) -> None:
    """150 minutes, gap 0: `duration_s` = 9000 > 7200, which `check_invalid_duration` fails."""
    lake.write_partition([_session(150)], lake.SESSIONS, DT, root=root)


FIXTURES = {
    "unknown_rating": unknown_rating,
    "duration_out_of_bounds": duration_out_of_bounds,
}


if __name__ == "__main__":
    FIXTURES[sys.argv[2]](Path(sys.argv[1]))
