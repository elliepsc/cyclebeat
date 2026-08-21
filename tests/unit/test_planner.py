"""The ADR-007 construction rules, case by case, on the planner.

Every case that the v1 note named is here under the same intent, re-mapped onto the E.3
enums. The names are kept close to the originals so the lineage is readable.
"""

from __future__ import annotations

import pytest

from catalogue_fixtures import build_catalogue, build_track
from cyclebeat import rules
from cyclebeat.models import SessionParams
from cyclebeat.planner import NoValidSessionError, plan_session

# A catalogue with enough of every zone to build a real 30-minute session.
MIXED = [
    (95, 200), (98, 240), (92, 190), (88, 230), (96, 210),      # Z1
    (105, 210), (110, 220), (112, 200), (108, 215), (102, 205),  # Z2
    (120, 215), (125, 230), (128, 205), (122, 210), (118, 220),  # Z3
    (135, 200), (140, 195), (138, 210), (133, 205),              # Z4
    (150, 190), (155, 205), (160, 200), (148, 195),              # Z5
]


def params(**overrides: object) -> SessionParams:
    base: dict[str, object] = {
        "level": "advanced",
        "goal": "endurance",
        "duration_min": 30,
    }
    base.update(overrides)
    return SessionParams(**base)  # type: ignore[arg-type]


def zones(plan: object) -> list[str]:
    return [segment.zone for segment in plan.segments]  # type: ignore[attr-defined]


# ── Structure ────────────────────────────────────────────────────────────────────────────


def test_warmup_always_first_regardless_of_input_order() -> None:
    """The first segment is a warmup even when the catalogue leads with a sprint."""
    catalogue = build_catalogue(list(reversed(MIXED)))
    plan = plan_session(catalogue, params())

    first = plan.segments[0]
    assert first.zone in rules.WARMUP_ZONES
    assert first.duration_s >= rules.WARMUP_MIN_DURATION_S
    assert first.role == "warmup"


def test_cooldown_always_last() -> None:
    plan = plan_session(build_catalogue(MIXED), params())

    last = plan.segments[-1]
    assert last.zone == rules.COOLDOWN_ZONE
    assert last.duration_s >= rules.COOLDOWN_MIN_DURATION_S
    assert last.role == "cooldown"


def test_no_warmup_candidate_raises_rather_than_dropping_the_rule() -> None:
    """A catalogue whose only Z1/Z2 tracks are too short has no valid session.

    The point of the test is that it does NOT return a session with a 40-second warmup.
    """
    catalogue = build_catalogue([(95, 130), (95, 125), (120, 200), (125, 210)])
    with pytest.raises(NoValidSessionError) as raised:
        plan_session(catalogue, params())
    assert "no_warmup_candidate" in raised.value.reasons


def test_no_cooldown_candidate_raises() -> None:
    """No Z1 at all: a warmup is available (Z2) but the session cannot be closed."""
    catalogue = build_catalogue([(105, 210), (110, 220), (120, 215), (125, 230)])
    with pytest.raises(NoValidSessionError) as raised:
        plan_session(catalogue, params())
    assert "no_cooldown_candidate" in raised.value.reasons


def test_the_cooldown_is_claimed_before_the_warmup() -> None:
    """With exactly one Z1 track, the Z1 goes to the cooldown and a Z2 warms up.

    Picking the warmup first would take the only Z1 and fail a session that is buildable.
    """
    catalogue = build_catalogue([(95, 200), (105, 210), (110, 220), (120, 215), (125, 230)])
    plan = plan_session(catalogue, params())

    assert plan.segments[0].zone == "Z2"
    assert plan.segments[-1].zone == "Z1"


def test_anchors_take_the_shortest_qualifying_track() -> None:
    """A 7-minute cooldown on a 20-minute session would eat the session."""
    catalogue = build_catalogue([(95, 400), (95, 190), (95, 420), (105, 210), (120, 215)])
    plan = plan_session(catalogue, params(duration_min=20))

    assert plan.segments[-1].duration_s == 190


# ── Level rules ──────────────────────────────────────────────────────────────────────────


def test_beginner_gets_no_sprint() -> None:
    """A beginner Z5 would have to last <= 30 s, which no real track does (ADR-007 §3)."""
    plan = plan_session(build_catalogue(MIXED), params(level="beginner", goal="intervals"))
    assert "Z5" not in zones(plan)


def test_intermediate_caps_high_zones_at_three() -> None:
    plan = plan_session(build_catalogue(MIXED), params(level="intermediate", goal="intervals"))
    high = [zone for zone in zones(plan) if zone in rules.HIGH_ZONES]
    assert len(high) <= rules.LEVEL_RULES["intermediate"].max_high  # type: ignore[operator]


def test_advanced_has_no_count_cap_but_still_gets_a_cooldown() -> None:
    plan = plan_session(build_catalogue(MIXED), params(level="advanced", goal="intervals"))
    assert "Z5" in zones(plan)
    assert plan.segments[-1].zone == "Z1"


def test_level_outranks_goal() -> None:
    """`intervals` lifts the goal budget on intensity; it does not lift a level cap."""
    beginner = plan_session(build_catalogue(MIXED), params(level="beginner", goal="intervals"))
    advanced = plan_session(build_catalogue(MIXED), params(level="advanced", goal="intervals"))

    assert "Z5" not in zones(beginner)
    assert "Z5" in zones(advanced)


# ── Goal rules ───────────────────────────────────────────────────────────────────────────


def test_goal_recovery_keeps_only_z1_and_z2() -> None:
    """ADR-007 disambiguation 1: "Z1/Z2 only" drops Z3 as well as Z4/Z5."""
    plan = plan_session(build_catalogue(MIXED), params(goal="recovery", duration_min=20))
    assert set(zones(plan)) <= {"Z1", "Z2"}


def test_goal_recovery_records_a_reason_for_every_zone_it_drops() -> None:
    plan = plan_session(build_catalogue(MIXED), params(goal="recovery", duration_min=20))
    reasons = {item.reason for item in plan.excluded}
    assert "goal_recovery_zone" in reasons


def test_goal_endurance_budgets_intensity_at_twenty_percent() -> None:
    plan = plan_session(build_catalogue(MIXED), params(goal="endurance", duration_min=30))
    high_s = sum(s.duration_s for s in plan.segments if s.zone in rules.HIGH_ZONES)
    assert high_s <= 0.20 * plan.params.target_duration_s


def test_goal_intervals_actually_places_sprints() -> None:
    """Regression: an earlier zone-preference order starved Z5 out of every session."""
    plan = plan_session(build_catalogue(MIXED), params(goal="intervals", duration_min=60))
    assert "Z5" in zones(plan)


# ── Intensity spacing ────────────────────────────────────────────────────────────────────


def test_never_more_than_two_consecutive_high_zones() -> None:
    plan = plan_session(build_catalogue(MIXED), params(goal="intervals", duration_min=60))

    run = 0
    for zone in zones(plan):
        run = run + 1 if zone in rules.HIGH_ZONES else 0
        assert run <= rules.MAX_CONSECUTIVE_HIGH


def test_recovery_follows_every_intensity_block() -> None:
    plan = plan_session(build_catalogue(MIXED), params(goal="intervals", duration_min=60))
    placed = zones(plan)

    for index, zone in enumerate(placed):
        if zone not in rules.HIGH_ZONES:
            continue
        window = placed[index + 1 : index + 1 + rules.RECOVERY_WITHIN_POSITIONS]
        assert any(following in rules.RECOVERY_ZONES for following in window)


def test_no_sprint_inside_the_opening_five_minutes() -> None:
    plan = plan_session(build_catalogue(MIXED), params(goal="intervals", duration_min=60))

    elapsed_s = 0.0
    for segment in plan.segments:
        if segment.zone == rules.SPRINT_ZONE:
            assert elapsed_s >= rules.COLD_SPRINT_WINDOW_S
        elapsed_s += segment.duration_s


# ── Duration ─────────────────────────────────────────────────────────────────────────────


def test_session_lands_within_two_minutes_of_target() -> None:
    for duration_min in (20, 30, 45, 60):
        plan = plan_session(build_catalogue(MIXED), params(duration_min=duration_min))
        assert abs(plan.duration_gap_s) <= rules.DURATION_TOLERANCE_S, duration_min


def test_duration_gap_is_the_actual_arithmetic() -> None:
    plan = plan_session(build_catalogue(MIXED), params(duration_min=30))
    total_s = sum(segment.duration_s for segment in plan.segments)
    assert plan.duration_gap_s == pytest.approx(total_s - plan.params.target_duration_s)


def test_a_catalogue_too_thin_to_fill_the_target_warns_instead_of_stretching() -> None:
    catalogue = build_catalogue([(95, 200), (105, 210), (95, 190)])
    plan = plan_session(catalogue, params(duration_min=60))

    assert plan.duration_gap_s < -rules.DURATION_TOLERANCE_S
    assert any(warning.startswith("duration_accuracy") for warning in plan.warnings)


# ── Bookkeeping ──────────────────────────────────────────────────────────────────────────


def test_every_input_track_is_placed_or_excluded() -> None:
    catalogue = build_catalogue(MIXED)
    plan = plan_session(catalogue, params())

    assert len(plan.segments) + len(plan.excluded) == len(catalogue)
    accounted = {s.track.track_id for s in plan.segments} | {e.track_id for e in plan.excluded}
    assert accounted == {track.track_id for track in catalogue}


def test_a_track_without_bpm_is_excluded_with_the_e2_reason() -> None:
    catalogue = build_catalogue([*MIXED, (None, 200)])
    plan = plan_session(catalogue, params())

    reasons = {item.track_id: item.reason for item in plan.excluded}
    assert reasons[catalogue[-1].track_id] == rules.EXCLUSION_NO_BPM


def test_a_repeated_track_is_used_once_and_the_copies_are_flagged() -> None:
    catalogue = [*build_catalogue(MIXED), build_track("t000", bpm=95, duration_s=200)]
    plan = plan_session(catalogue, params())

    placed = [s.track.track_id for s in plan.segments]
    assert len(placed) == len(set(placed))
    assert rules.EXCLUSION_DUPLICATE in {item.reason for item in plan.excluded}


def test_a_zero_length_track_is_excluded() -> None:
    catalogue = [*build_catalogue(MIXED), build_track("zzz", bpm=95, duration_s=0)]
    plan = plan_session(catalogue, params())

    reasons = {item.track_id: item.reason for item in plan.excluded}
    assert reasons["zzz"] == rules.EXCLUSION_INVALID_DURATION


# ── E.2 deference ────────────────────────────────────────────────────────────────────────


def test_zones_come_from_e2_not_from_the_column_handed_in() -> None:
    """A lying `zone` column must not steer the planner (E.2 owns the mapping)."""
    catalogue = [
        build_track("a", bpm=95, duration_s=200, zone="Z5"),
        build_track("b", bpm=105, duration_s=210, zone="Z5"),
        build_track("c", bpm=95, duration_s=190, zone="Z4"),
        build_track("d", bpm=120, duration_s=215, zone="Z1"),
    ]
    plan = plan_session(catalogue, params(duration_min=20))

    by_id = {s.track.track_id: s.zone for s in plan.segments}
    assert by_id["b"] == "Z2"
    assert by_id.get("d") in (None, "Z3")


def test_half_time_bpm_is_normalized_by_e2_not_by_a_local_heuristic() -> None:
    """190 BPM is a double-time reading of 95 and belongs in Z1, not Z5."""
    catalogue = [
        build_track("a", bpm=190, duration_s=200),
        build_track("b", bpm=35, duration_s=210),
        build_track("c", bpm=210, duration_s=190),
        build_track("d", bpm=120, duration_s=215),
    ]
    plan = plan_session(catalogue, params(duration_min=20))

    by_id = {s.track.track_id: s.zone for s in plan.segments}
    assert by_id["a"] == "Z1"
    assert by_id["b"] == "Z1"
    assert by_id["c"] == "Z2"


# ── Determinism ──────────────────────────────────────────────────────────────────────────


def test_planning_twice_gives_the_same_plan() -> None:
    catalogue = build_catalogue(MIXED)
    assert plan_session(catalogue, params()) == plan_session(catalogue, params())


def test_shuffling_the_catalogue_changes_nothing() -> None:
    """Order-independence is what makes the property tests and the mutation check stable."""
    catalogue = build_catalogue(MIXED)
    shuffled = [catalogue[index] for index in (7, 2, 19, 0, 13, 22, 5, 11, 3, 16, 9, 1)]
    shuffled += [track for track in catalogue if track not in shuffled]

    assert plan_session(shuffled, params()).segments == plan_session(catalogue, params()).segments
