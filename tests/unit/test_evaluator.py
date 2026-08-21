"""The ADR-007 checks, case by case, on the evaluator.

The evaluator is tested on plans BUILT BY HAND, not on planner output. Handing it what the
planner produced would only prove the two agree — which is the circularity the phase-3 exit
criterion exists to rule out. `evals/test_mutation_check.py` covers the pairing; here the
inputs are constructed to fail one specific check at a time.
"""

from __future__ import annotations

import pytest

from catalogue_fixtures import build_track
from cyclebeat import rules
from cyclebeat.evaluator import evaluate
from cyclebeat.models import ExcludedTrack, Segment, SessionParams, SessionPlan
from cyclebeat.planner import plan_session


def params(**overrides: object) -> SessionParams:
    base: dict[str, object] = {"level": "advanced", "goal": "intervals", "duration_min": 30}
    base.update(overrides)
    return SessionParams(**base)  # type: ignore[arg-type]


def segment(order: int, bpm: float | None, duration_s: float) -> Segment:
    """One segment. The `zone` label is derived here only so the model validates.

    The evaluator recomputes it from the BPM and never reads the field — which is what
    `test_a_relabelled_zone_does_not_fool_the_evaluator` proves.
    """
    from cyclebeat import e2

    zone = e2.zone_of(bpm) or "Z1"
    return Segment(
        order=order,
        track=build_track(f"s{order:02d}", bpm=bpm, duration_s=duration_s),
        zone=zone,  # type: ignore[arg-type]
        role="endurance",
        duration_s=duration_s,
    )


def build_plan(specs: list[tuple[float | None, float]], **overrides: object) -> SessionPlan:
    """A plan from `(bpm, duration_s)` pairs, bypassing the planner entirely."""
    segments = [segment(order, bpm, duration_s) for order, (bpm, duration_s) in enumerate(specs)]
    session_params = overrides.pop("params", None) or params()
    return SessionPlan(
        params=session_params,  # type: ignore[arg-type]
        segments=segments,
        excluded=overrides.pop("excluded", []),  # type: ignore[arg-type]
        duration_gap_s=sum(s.duration_s for s in segments) - session_params.target_duration_s,  # type: ignore[union-attr]
    )


# A session that passes all ten checks: 30 min target, warmup, spaced intensity, cooldown.
GOOD = [
    (95, 240),   # Z1 warmup, >= 180 s
    (120, 220),  # Z3
    (138, 200),  # Z4
    (105, 210),  # Z2 recovery
    (150, 190),  # Z5, starts at 870 s -> past the cold window
    (98, 200),   # Z1 recovery
    (125, 210),  # Z3
    (95, 340),   # Z1 cooldown
]


def test_a_sound_session_is_safe() -> None:
    result = evaluate(build_plan(GOOD))

    assert result.verdict == "safe"
    assert result.blocking_failures == []
    assert result.score == 1.0
    assert all(result.checks.values())


def test_every_adr_007_check_is_reported() -> None:
    """The report is the contract: a check that stops being computed must break a test."""
    result = evaluate(build_plan(GOOD))
    assert set(result.checks) == set(rules.CHECK_NAMES)


# ── Blocking failures ────────────────────────────────────────────────────────────────────


def test_missing_warmup_blocks() -> None:
    result = evaluate(build_plan(GOOD[1:]))

    assert result.checks["warmup_present"] is False
    assert "warmup_present" in result.blocking_failures
    assert result.verdict == "review"


def test_a_warmup_that_is_too_short_blocks() -> None:
    """Right zone, wrong length: 90 s is not a warmup."""
    result = evaluate(build_plan([(95, 90), *GOOD[1:]]))
    assert "warmup_present" in result.blocking_failures


def test_missing_cooldown_blocks() -> None:
    result = evaluate(build_plan(GOOD[:-1]))
    assert "cooldown_present" in result.blocking_failures


def test_a_z2_cooldown_blocks() -> None:
    """ADR-007 requires Z1 to close the session, not merely a low zone."""
    result = evaluate(build_plan([*GOOD[:-1], (110, 340)]))
    assert "cooldown_present" in result.blocking_failures


def test_a_cold_sprint_blocks() -> None:
    """A Z5 starting at 240 s is inside the 5-minute window."""
    result = evaluate(build_plan([(95, 240), (150, 190), *GOOD[1:]]))

    assert result.checks["no_cold_sprint"] is False
    assert "no_cold_sprint" in result.blocking_failures


def test_a_sprint_just_past_the_window_does_not_block() -> None:
    """The boundary is checked on the START time: 300 s exactly is allowed."""
    result = evaluate(build_plan([(95, 300), (150, 190), (105, 210), (95, 200), (95, 340)]))
    assert result.checks["no_cold_sprint"] is True


def test_a_segment_without_bpm_blocks() -> None:
    """E.2 excludes a BPM-less track from the planner; a plan carrying one is broken."""
    result = evaluate(build_plan([*GOOD[:4], (None, 200), *GOOD[4:]]))

    assert result.checks["all_segments_have_bpm"] is False
    assert "all_segments_have_bpm" in result.blocking_failures


def test_an_empty_session_blocks_rather_than_scoring_low() -> None:
    result = evaluate(build_plan([]))

    assert result.verdict == "review"
    assert "warmup_present" in result.blocking_failures
    assert "cooldown_present" in result.blocking_failures


# ── Non-blocking failures ────────────────────────────────────────────────────────────────


def test_three_consecutive_high_zones_fail_without_blocking() -> None:
    plan = build_plan([(95, 240), (135, 200), (140, 200), (150, 200), (105, 210), (95, 340)])
    result = evaluate(plan)

    assert result.checks["no_consecutive_high"] is False
    assert result.blocking_failures == []
    assert result.verdict == "review"


def test_intensity_without_a_recovery_within_two_positions_fails() -> None:
    plan = build_plan([(95, 240), (138, 200), (120, 210), (125, 200), (105, 210), (95, 340)])
    result = evaluate(plan)
    assert result.checks["recovery_after_intensity"] is False


def test_the_cooldown_counts_as_the_recovery_for_a_late_sprint() -> None:
    """A Z4 in the penultimate slot is followed by the Z1 that ends the session."""
    plan = build_plan([(95, 240), (120, 210), (105, 200), (138, 200), (95, 340)])
    result = evaluate(plan)
    assert result.checks["recovery_after_intensity"] is True


def test_a_session_that_misses_its_target_fails_duration_accuracy() -> None:
    plan = build_plan(GOOD, params=params(duration_min=60))
    result = evaluate(plan)

    assert result.checks["duration_accuracy"] is False
    assert result.blocking_failures == []


def test_low_bpm_coverage_fails() -> None:
    """Half the catalogue unresolved is below the 60 % floor."""
    unresolved = [ExcludedTrack(track_id=f"x{i}", reason=rules.EXCLUSION_NO_BPM) for i in range(9)]
    plan = build_plan(GOOD, excluded=unresolved)
    result = evaluate(plan)

    assert result.checks["bpm_coverage"] is False


def test_exclusions_that_are_not_about_bpm_do_not_hurt_coverage() -> None:
    """A track the planner simply did not need is not a data-quality problem."""
    spare = [ExcludedTrack(track_id=f"x{i}", reason=rules.EXCLUSION_NOT_NEEDED) for i in range(40)]
    result = evaluate(build_plan(GOOD, excluded=spare))

    assert result.checks["bpm_coverage"] is True


# ── Level and goal ───────────────────────────────────────────────────────────────────────


def test_a_beginner_session_with_a_full_length_sprint_fails_its_level() -> None:
    result = evaluate(build_plan(GOOD, params=params(level="beginner")))

    assert result.checks["level_caps_respected"] is False
    assert result.blocking_failures == []


def test_the_same_session_passes_for_an_advanced_rider() -> None:
    """The plan is unchanged — only the level moves, and with it the verdict."""
    assert evaluate(build_plan(GOOD, params=params(level="advanced"))).verdict == "safe"


def test_an_intermediate_rider_may_not_take_four_high_blocks() -> None:
    plan = build_plan(
        [(95, 240), (135, 200), (105, 200), (138, 200), (98, 200),
         (140, 200), (110, 200), (133, 200), (95, 340)],
        params=params(level="intermediate", duration_min=32),
    )
    assert evaluate(plan).checks["level_caps_respected"] is False


def test_a_recovery_goal_rejects_a_z3_segment() -> None:
    result = evaluate(build_plan(GOOD, params=params(goal="recovery")))
    assert result.checks["goal_respected"] is False


def test_an_endurance_goal_rejects_intensity_over_its_budget() -> None:
    result = evaluate(build_plan(GOOD, params=params(goal="endurance")))
    assert result.checks["goal_respected"] is False


def test_params_can_be_overridden_to_judge_a_plan_against_other_parameters() -> None:
    plan = build_plan(GOOD, params=params(level="advanced"))

    assert evaluate(plan).checks["level_caps_respected"] is True
    assert evaluate(plan, params(level="beginner")).checks["level_caps_respected"] is False


# ── The evaluator does not trust the plan's labels ───────────────────────────────────────


def test_a_relabelled_zone_does_not_fool_the_evaluator() -> None:
    """Rewriting a sprint's `zone` to Z1 must not hide it from the intensity checks.

    This is the reason the evaluator recomputes zones through `e2.zone_of` instead of reading
    `Segment.zone`: the label is the planner's claim, the BPM is the fact.
    """
    honest = build_plan([(95, 240), (150, 190), *GOOD[1:]])
    assert "no_cold_sprint" in evaluate(honest).blocking_failures

    lying = honest.model_copy(
        update={
            "segments": [
                s.model_copy(update={"zone": "Z1"}) if s.order == 1 else s
                for s in honest.segments
            ]
        }
    )
    assert "no_cold_sprint" in evaluate(lying).blocking_failures


# ── Agreement with the planner's own figure ──────────────────────────────────────────────


@pytest.mark.parametrize("n_unresolved", [0, 3, 6, 9, 12])
def test_coverage_from_a_plan_matches_the_coverage_from_the_catalogue(n_unresolved: int) -> None:
    """The evaluator reconstructs BPM coverage from the plan; the planner reads it off the
    catalogue. Two derivations of one number drift unless something pins them together."""
    from cyclebeat.planner import _bpm_coverage

    resolved = [(95, 240), (105, 210), (120, 200), (95, 200), (110, 215), (125, 190)]
    catalogue = [
        *[build_track(f"r{i:02d}", bpm=bpm, duration_s=d) for i, (bpm, d) in enumerate(resolved)],
        *[build_track(f"u{i:02d}", bpm=None) for i in range(n_unresolved)],
    ]
    plan = plan_session(catalogue, params(goal="endurance", duration_min=20))

    n_input = len(plan.segments) + len(plan.excluded)
    unresolved = sum(1 for e in plan.excluded if e.reason == rules.EXCLUSION_NO_BPM)

    assert (n_input - unresolved) / n_input == pytest.approx(_bpm_coverage(catalogue))
