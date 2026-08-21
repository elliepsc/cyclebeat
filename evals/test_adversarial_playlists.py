"""Trap playlists: catalogues built to make the engine do the wrong thing (§11).

Each case is a way a real catalogue can be pathological — all-sprint, all-unresolved, one
track repeated, BPMs that are half-time readings — and each asserts what the engine must do
about it. The recurring shape is that a bad catalogue produces `NoValidSessionError`, never a
session that quietly drops its cooldown: refusing is a feature, and phase 4 turns the refusal
into the E.3 422.

The positive control at the end is not decoration. Without it a planner that raised on
everything would pass this entire file.
"""

from __future__ import annotations

import pytest

from catalogue_fixtures import build_catalogue, build_track
from cyclebeat import e2
from cyclebeat.evaluator import evaluate
from cyclebeat.models import SessionParams
from cyclebeat.planner import NoValidSessionError, plan_session


def params(**overrides: object) -> SessionParams:
    base: dict[str, object] = {"level": "advanced", "goal": "endurance", "duration_min": 30}
    base.update(overrides)
    return SessionParams(**base)  # type: ignore[arg-type]


# ── Catalogues with no valid session in them ─────────────────────────────────────────────


def test_an_all_sprint_playlist_is_refused() -> None:
    """Nothing to warm up or cool down with. The trap is a session that starts on a sprint."""
    catalogue = build_catalogue([(150 + index, 200) for index in range(12)])

    with pytest.raises(NoValidSessionError) as raised:
        plan_session(catalogue, params(goal="intervals"))
    assert "no_cooldown_candidate" in raised.value.reasons


def test_a_playlist_with_no_resolved_bpm_is_refused_and_every_track_is_explained() -> None:
    """E.2: no source -> bpm NULL -> excluded. Twelve exclusions, no session."""
    catalogue = build_catalogue([(None, 200) for _ in range(12)])

    with pytest.raises(NoValidSessionError):
        plan_session(catalogue, params())


def test_one_track_repeated_twenty_times_does_not_become_a_session() -> None:
    """The trap is a 20-segment session built from the same song.

    Deduplication leaves exactly one usable track, which the cooldown claims — and then
    there is nothing left to warm up with, which is the correct answer.
    """
    catalogue = [build_track("same", bpm=95, duration_s=200) for _ in range(20)]

    with pytest.raises(NoValidSessionError) as raised:
        plan_session(catalogue, params())
    assert "no_warmup_candidate" in raised.value.reasons


def test_a_single_ninety_minute_track_cannot_fill_a_thirty_minute_session() -> None:
    """The trap is stretching one track over the target, or slicing it."""
    with pytest.raises(NoValidSessionError):
        plan_session(build_catalogue([(105, 5400)]), params())


def test_a_catalogue_of_sprints_plus_one_cooldown_still_has_no_warmup() -> None:
    catalogue = build_catalogue([(95, 200), *[(150 + index, 200) for index in range(10)]])

    with pytest.raises(NoValidSessionError) as raised:
        plan_session(catalogue, params(goal="intervals"))
    assert "no_warmup_candidate" in raised.value.reasons


def test_a_recovery_goal_on_an_intensity_only_catalogue_is_refused() -> None:
    """`recovery` keeps Z1/Z2 only, so a Z3+ catalogue leaves nothing to build with."""
    catalogue = build_catalogue([(120 + index * 5, 200) for index in range(8)])

    with pytest.raises(NoValidSessionError):
        plan_session(catalogue, params(goal="recovery"))


# ── E.2 normalization traps ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("bpm", "expected_zone"),
    [
        # The boundaries E.2 states as integer bands.
        (99.0, "Z1"),
        (99.4, "Z1"),
        (100.0, "Z2"),
        (115.0, "Z2"),
        (115.4, "Z2"),
        (130.0, "Z3"),
        (145.0, "Z4"),
        (146.0, "Z5"),
        # Half-BPM values, where `zone_for`'s rounding decides. Python's `round` is
        # banker's rounding — .5 goes to the EVEN integer — so these do not all round up:
        # 99.5 -> 100 and 145.5 -> 146 cross their band, while 130.5 -> 130 does not.
        # Pinned because it is exactly the kind of behaviour a later "cleanup" would flip.
        (99.5, "Z2"),
        (115.5, "Z3"),
        (130.5, "Z3"),
        (145.5, "Z5"),
        # Normalization boundaries. 180 is the ceiling and stays; 181 halves to 90.5; 70 is
        # the floor and stays; 69 DOUBLES to 138, which is Z4 — a slow reading of a fast
        # track, and the whole reason E.2 normalizes before it maps.
        (180.0, "Z5"),
        (181.0, "Z1"),
        (70.0, "Z1"),
        (69.0, "Z4"),
    ],
)
def test_zone_boundaries_are_exactly_e2s(bpm: float, expected_zone: str) -> None:
    """Guards the rounding disambiguation in `e2.zone_for` against a silent re-tuning."""
    assert e2.zone_of(bpm) == expected_zone


def test_a_double_time_bpm_is_normalized_not_treated_as_a_sprint() -> None:
    """190 BPM is a double-time reading of 95: it belongs in Z1, and must not open a session
    as an unplaceable sprint. The known pitfall — answered by E.2, never by a local rule."""
    catalogue = build_catalogue([(190, 240), (35, 200), (360, 190), (105, 210), (120, 215)])
    plan = plan_session(catalogue, params(duration_min=20))

    by_id = {segment.track.track_id: segment.zone for segment in plan.segments}
    assert by_id["t000"] == "Z1"  # 190 -> 95
    assert by_id["t001"] == "Z1"  # 35  -> 70
    assert evaluate(plan).blocking_failures == []


def test_a_zero_bpm_is_absence_of_a_source_not_a_slow_track() -> None:
    """Deezer encodes "no BPM" as 0; feeding it to the normalization loop would not halt."""
    assert e2.zone_of(0.0) is None
    assert e2.zone_of(-5.0) is None


# ── Traps that must degrade, not explode ─────────────────────────────────────────────────


def test_a_thin_catalogue_warns_instead_of_padding_the_session() -> None:
    """The trap is reusing tracks, or claiming a 60-minute session built from 10 minutes."""
    catalogue = build_catalogue([(95, 200), (105, 210), (95, 190)])
    plan = plan_session(catalogue, params(duration_min=60))

    assert len(plan.segments) == 3
    assert any(warning.startswith("duration_accuracy") for warning in plan.warnings)
    assert evaluate(plan).verdict == "review"
    assert evaluate(plan).blocking_failures == []


def test_a_beginner_asking_for_intervals_gets_intensity_without_sprints() -> None:
    """The trap is letting the goal lift a level cap."""
    catalogue = build_catalogue(
        [(95, 240), (98, 200), (105, 210), (110, 200), (120, 215), (125, 200),
         (135, 200), (140, 195), (150, 190), (155, 205), (160, 200)]
    )
    plan = plan_session(catalogue, params(level="beginner", goal="intervals"))
    placed = [segment.zone for segment in plan.segments]

    assert "Z5" not in placed
    assert evaluate(plan).checks["level_caps_respected"] is True


def test_a_catalogue_that_is_mostly_unresolved_still_plans_and_flags_coverage() -> None:
    """The trap is silently building from the 20 % that resolved and reporting nothing."""
    resolved = [(95, 240), (105, 210), (120, 200), (95, 200)]
    catalogue = [
        *build_catalogue(resolved),
        *[build_track(f"u{index:02d}", bpm=None) for index in range(20)],
    ]
    plan = plan_session(catalogue, params(duration_min=20))
    result = evaluate(plan)

    assert any(warning.startswith("bpm_coverage") for warning in plan.warnings)
    assert result.checks["bpm_coverage"] is False
    assert result.blocking_failures == []


# ── Positive control ─────────────────────────────────────────────────────────────────────


def test_a_minimal_viable_catalogue_produces_a_safe_session() -> None:
    """Without this, a planner that refused everything would pass this whole file."""
    catalogue = build_catalogue(
        [(95, 240), (98, 200), (92, 190), (105, 210), (110, 220), (108, 200),
         (120, 215), (125, 230), (128, 205), (135, 200), (140, 195)]
    )
    plan = plan_session(catalogue, params(duration_min=30))
    result = evaluate(plan)

    assert result.verdict == "safe"
    assert result.blocking_failures == []
    assert result.score == 1.0
