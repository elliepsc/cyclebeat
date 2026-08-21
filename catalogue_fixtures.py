"""Catalogue builders shared by `tests/` and `evals/`.

At the repo root, and NOT named `conftest.py`, for two reasons. A `conftest.py` is only
visible to its own directory and below, and `evals/` is not below `tests/` — so the shared
helpers have to live above both. And a second `conftest` would shadow `tests/conftest.py` on
`sys.path` (pytest's `pythonpath = ["."]` makes the root importable), which is exactly the
collision that named this module instead.

`tests/conftest.py` keeps the Airflow environment setup. It stays there: it has to run before
anything imports `airflow`, and hoisting it here would impose it on the eval suite, which
never touches Airflow.
"""

from __future__ import annotations

from collections.abc import Sequence

from cyclebeat.models import PlannerTrack

# Long enough to serve as a warmup (>= 180 s) or a cooldown (>= 120 s), which most fixtures
# want by default. Real Deezer tracks sit around here.
DEFAULT_DURATION_S = 210.0


def build_track(
    track_id: str,
    bpm: float | None = None,
    duration_s: float = DEFAULT_DURATION_S,
    **overrides: object,
) -> PlannerTrack:
    """One candidate track.

    `zone` is left unset on purpose: the planner recomputes it from `bpm_effective` through
    `cyclebeat.e2`, and a fixture that pre-filled it would hide a planner that trusted the
    column instead of the contract. Pass `zone=` explicitly only to test that it is ignored.
    """
    return PlannerTrack(
        track_id=track_id,
        title=f"Track {track_id}",
        artist=f"Artist {track_id}",
        duration_s=duration_s,
        bpm_effective=bpm,
        **overrides,  # type: ignore[arg-type]
    )


def build_catalogue(specs: Sequence[tuple[float | None, float]]) -> list[PlannerTrack]:
    """A catalogue from `(bpm, duration_s)` pairs, with generated ids.

    Ids are zero-padded so lexicographic order — the planner's tiebreak — matches the order
    they are written in. A test that lists the tracks it wants in order gets them considered
    in that order, which is what makes the assertions readable.
    """
    return [
        build_track(f"t{index:03d}", bpm=bpm, duration_s=duration_s)
        for index, (bpm, duration_s) in enumerate(specs)
    ]
