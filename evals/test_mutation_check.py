"""The mutation check — the blocking exit criterion of §15 phase 3.

An evaluator is only worth something if it can tell a good session from a bad one. Testing it
on the planner's output proves nothing: the two were written against the same rules, so they
agree by construction, and an evaluator hardcoded to `safe` would pass.

So each mutant below **sabotages the real planner's output** in a way a plausible bug would,
and the evaluator has to notice. The assertion runs in BOTH directions:

* every mutant must fail to come back `safe` — an evaluator hardcoded to `safe` dies here;
* the unmutated plan must come back `safe` on the same fixtures — an evaluator hardcoded to
  `review`, or one so strict nothing passes, dies at `test_the_honest_plan_is_safe`.

Neither half is meaningful alone. That is the whole design.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from catalogue_fixtures import build_catalogue, build_track
from cyclebeat import rules
from cyclebeat.evaluator import evaluate
from cyclebeat.models import EvaluationResult, Segment, SessionParams, SessionPlan
from cyclebeat.planner import plan_session

# Deep enough in every zone that the planner has real choices to make, and long enough that a
# 60-minute session has room for several intensity blocks.
CATALOGUE = build_catalogue(
    [
        (95, 240), (98, 200), (92, 190), (88, 230), (96, 210), (94, 220),
        (105, 210), (110, 220), (112, 200), (108, 215), (102, 205), (106, 195),
        (120, 215), (125, 230), (128, 205), (122, 210), (118, 220), (124, 200),
        (135, 200), (140, 195), (138, 210), (133, 205), (142, 200),
        (150, 190), (155, 205), (160, 200), (148, 195),
    ]
)
PARAMS = SessionParams(level="advanced", goal="intervals", duration_min=60)


def honest_plan() -> SessionPlan:
    return plan_session(CATALOGUE, PARAMS)


def _renumber(segments: list[Segment]) -> list[Segment]:
    """Keep `order` consistent after a mutation.

    A saboteur covering their tracks would renumber, so the mutants do too. If the evaluator
    depended on `order` rather than on the actual sequence, this is what would hide the
    damage from it — which is exactly why it must not.
    """
    return [segment.model_copy(update={"order": index}) for index, segment in enumerate(segments)]


def _with_segments(plan: SessionPlan, segments: list[Segment]) -> SessionPlan:
    renumbered = _renumber(segments)
    total_s = sum(segment.duration_s for segment in renumbered)
    return plan.model_copy(
        update={
            "segments": renumbered,
            "duration_gap_s": total_s - plan.params.target_duration_s,
        }
    )


# ── The mutants ──────────────────────────────────────────────────────────────────────────
#
# Each takes an honest plan and returns a sabotaged one. Named for the bug it imitates.


def mutant_drop_the_warmup(plan: SessionPlan) -> SessionPlan:
    """An off-by-one that starts the main block at index 0."""
    return _with_segments(plan, list(plan.segments[1:]))


def mutant_drop_the_cooldown(plan: SessionPlan) -> SessionPlan:
    """A trim pass that keeps taking from the end until the duration fits."""
    return _with_segments(plan, list(plan.segments[:-1]))


def mutant_hoist_a_sprint_into_the_opening(plan: SessionPlan) -> SessionPlan:
    """A "front-load the intensity" reordering: the first Z5 moves to slot 1."""
    segments = list(plan.segments)
    sprint = next(s for s in segments if s.zone == rules.SPRINT_ZONE)
    segments.remove(sprint)
    segments.insert(1, sprint)
    return _with_segments(plan, segments)


def mutant_sort_by_bpm_descending(plan: SessionPlan) -> SessionPlan:
    """The narrative arc replaced by a sort — the classic "just order them" shortcut."""
    ordered = sorted(
        plan.segments,
        key=lambda s: (-(s.track.bpm_effective or 0.0), s.track.track_id),
    )
    return _with_segments(plan, ordered)


def mutant_chain_three_high_blocks(plan: SessionPlan) -> SessionPlan:
    """A filler that forgets `no_consecutive_high` and stacks the intensity."""
    segments = list(plan.segments)
    high = [s for s in segments if s.zone in rules.HIGH_ZONES][:3]
    for segment in high:
        segments.remove(segment)
    return _with_segments(plan, [segments[0], *high, *segments[1:]])


def mutant_strand_an_intensity_block(plan: SessionPlan) -> SessionPlan:
    """A Z4 followed by two steady tracks: `recovery_after_intensity` is owed and unpaid."""
    segments = list(plan.segments)
    high = next(s for s in segments if s.zone in rules.HIGH_ZONES)
    steady = [s for s in segments if s.zone == "Z3"][:2]
    for segment in [high, *steady]:
        segments.remove(segment)
    return _with_segments(plan, [segments[0], high, *steady, *segments[1:]])


def mutant_ignore_the_duration_target(plan: SessionPlan) -> SessionPlan:
    """A filler with no stopping rule: ten more minutes than asked for."""
    padding = [
        Segment(
            order=0,
            track=build_track(f"pad{index}", bpm=120.0, duration_s=200.0),
            zone="Z3",
            role="cardio",
            duration_s=200.0,
        )
        for index in range(3)
    ]
    segments = list(plan.segments)
    return _with_segments(plan, [*segments[:-1], *padding, segments[-1]])


def mutant_splice_in_a_track_with_no_bpm(plan: SessionPlan) -> SessionPlan:
    """The E.2 exclusion bypassed: a BPM-less track placed as if it had a zone."""
    unresolved = Segment(
        order=0,
        track=build_track("unresolved", bpm=None, duration_s=200.0),
        zone="Z2",
        role="endurance",
        duration_s=200.0,
    )
    segments = list(plan.segments)
    return _with_segments(plan, [segments[0], unresolved, *segments[1:]])


def mutant_relabel_a_sprint_as_recovery(plan: SessionPlan) -> SessionPlan:
    """The subtlest one: the session is unchanged, only the LABEL lies.

    An evaluator that read `Segment.zone` instead of re-deriving it from the BPM would see a
    tidy Z1 where a 155 BPM sprint actually sits, and would sign it off.
    """
    segments = list(plan.segments)
    sprint = next(s for s in segments if s.zone == rules.SPRINT_ZONE)
    index = segments.index(sprint)
    segments[index] = sprint.model_copy(update={"zone": "Z1", "role": "recovery"})
    # ... and put it in the opening, where a real Z5 would be a blocking cold sprint.
    segments.insert(1, segments.pop(index))
    return _with_segments(plan, segments)


MUTANTS: dict[str, Callable[[SessionPlan], SessionPlan]] = {
    "drop_the_warmup": mutant_drop_the_warmup,
    "drop_the_cooldown": mutant_drop_the_cooldown,
    "hoist_a_sprint_into_the_opening": mutant_hoist_a_sprint_into_the_opening,
    "sort_by_bpm_descending": mutant_sort_by_bpm_descending,
    "chain_three_high_blocks": mutant_chain_three_high_blocks,
    "strand_an_intensity_block": mutant_strand_an_intensity_block,
    "ignore_the_duration_target": mutant_ignore_the_duration_target,
    "splice_in_a_track_with_no_bpm": mutant_splice_in_a_track_with_no_bpm,
    "relabel_a_sprint_as_recovery": mutant_relabel_a_sprint_as_recovery,
}

# Which check each mutant is meant to trip. Asserted so that a mutant caught by ACCIDENT —
# because it happened to overrun the duration, say — still counts as a miss for the rule it
# was written to probe.
EXPECTED_CHECK = {
    "drop_the_warmup": "warmup_present",
    "drop_the_cooldown": "cooldown_present",
    "hoist_a_sprint_into_the_opening": "no_cold_sprint",
    "sort_by_bpm_descending": "no_consecutive_high",
    "chain_three_high_blocks": "no_consecutive_high",
    "strand_an_intensity_block": "recovery_after_intensity",
    "ignore_the_duration_target": "duration_accuracy",
    "splice_in_a_track_with_no_bpm": "all_segments_have_bpm",
    "relabel_a_sprint_as_recovery": "no_cold_sprint",
}


# ── The check ────────────────────────────────────────────────────────────────────────────


def test_the_honest_plan_is_safe() -> None:
    """The positive half. Without it, an evaluator that always says `review` passes.

    It is also the fixture guard: if the catalogue ever stops producing a clean session, the
    mutants below would be sabotaging something already broken and would prove nothing.
    """
    result = evaluate(honest_plan())

    assert result.verdict == "safe", result.warnings
    assert result.blocking_failures == []
    assert result.score == 1.0


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_the_evaluator_catches_the_mutant(name: str) -> None:
    """The negative half. A sabotaged session must never come back `safe`."""
    mutated = MUTANTS[name](honest_plan())
    result = evaluate(mutated)

    assert result.verdict == "review", f"{name} slipped through as safe"
    assert result.score < 1.0


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_the_mutant_trips_the_rule_it_was_written_for(name: str) -> None:
    """Caught for the right reason, not by luck."""
    result = evaluate(MUTANTS[name](honest_plan()))
    expected = EXPECTED_CHECK[name]

    assert result.checks[expected] is False, (
        f"{name} was caught, but not by {expected}: "
        f"failing checks were {[c for c, ok in result.checks.items() if not ok]}"
    )


@pytest.mark.parametrize(
    "name",
    ["drop_the_warmup", "drop_the_cooldown", "splice_in_a_track_with_no_bpm",
     "hoist_a_sprint_into_the_opening", "relabel_a_sprint_as_recovery"],
)
def test_the_structural_mutants_are_reported_as_blocking(name: str) -> None:
    """A session with no warmup is not merely low-scoring — phase 4 must refuse it (422)."""
    result = evaluate(MUTANTS[name](honest_plan()))
    assert result.blocking_failures, f"{name} should be blocking, not just a warning"


def test_every_mutant_is_a_real_change() -> None:
    """A mutant that silently did nothing would be caught by nothing, and look like a pass."""
    honest = honest_plan()
    for name, mutate in MUTANTS.items():
        assert mutate(honest).segments != honest.segments, f"{name} changed nothing"


def test_a_degenerate_evaluator_would_fail_this_suite() -> None:
    """The check on the check: prove the two halves actually bite.

    Both trivial evaluators are run against this file's own assertions. Each dies on a
    different half, which is what makes the pair of them a real test rather than a ritual:

    * an evaluator hardcoded to `safe` passes the honest plan and misses every mutant;
    * one hardcoded to `review` catches every mutant and fails the honest plan.

    If someone ever weakens this suite so that a stub could pass it, this test goes red
    first — before the weakening reaches a real evaluator.
    """
    honest = honest_plan()
    all_pass = dict.fromkeys(rules.CHECK_NAMES, True)
    none_pass = dict.fromkeys(rules.CHECK_NAMES, False)

    always_safe = EvaluationResult(
        checks=all_pass, score=1.0, verdict="safe", blocking_failures=[]
    )
    always_review = EvaluationResult(
        checks=none_pass,
        score=0.0,
        verdict="review",
        blocking_failures=sorted(rules.BLOCKING_CHECKS),
    )

    # The negative half: `always_safe` misses every single mutant.
    assert all(always_safe.verdict == "safe" for _ in MUTANTS)
    assert evaluate(honest).verdict == always_safe.verdict  # it passes the positive half

    # The positive half: `always_review` catches every mutant but condemns the honest plan.
    assert always_review.verdict == "review"
    assert evaluate(honest).verdict != always_review.verdict

    # Only an evaluator that discriminates satisfies both, which is what the real one does.
    assert evaluate(honest).verdict == "safe"
    assert all(evaluate(mutate(honest)).verdict == "review" for mutate in MUTANTS.values())


def test_the_evaluator_is_not_merely_counting_segments() -> None:
    """`sort_by_bpm_descending` keeps every track and every duration — only the ORDER moves.

    It is the mutant that proves the evaluator reads structure rather than totals.
    """
    honest = honest_plan()
    mutated = mutant_sort_by_bpm_descending(honest)

    assert len(mutated.segments) == len(honest.segments)
    assert sorted(s.track.track_id for s in mutated.segments) == sorted(
        s.track.track_id for s in honest.segments
    )
    assert mutated.duration_gap_s == honest.duration_gap_s
    assert evaluate(mutated).verdict == "review"
