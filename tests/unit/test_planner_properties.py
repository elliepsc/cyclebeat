"""Property-based invariants of the planner over generated catalogues (§11, hypothesis).

The case-by-case tests in `test_planner.py` check the rules on catalogues chosen to exercise
them. These check that the rules hold on catalogues nobody chose — which is where a greedy
filler with an off-by-one in its lookahead actually breaks.

Two of the properties below carry most of the weight:

* **order independence** — shuffling the catalogue must not change the plan. Everything else
  in phase 3 is reproducible only because this holds.
* **the planner never emits what the evaluator would block** — the one invariant that ties
  the two modules together, and the positive half of the anti-circularity argument whose
  negative half is `evals/test_mutation_check.py`.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from catalogue_fixtures import build_track
from cyclebeat import e2, rules
from cyclebeat.evaluator import evaluate
from cyclebeat.models import Goal, Level, PlannerTrack, SessionParams
from cyclebeat.planner import plan_session

LEVELS: list[Level] = ["beginner", "intermediate", "advanced"]
GOALS: list[Goal] = ["endurance", "intervals", "recovery"]

# Durations and BPMs are whole numbers, as they are in the warehouse. That is not cosmetic:
# fractional seconds would let the planner's running total and the evaluator's re-sum differ
# in the last bit and turn a budget comparison into a coin flip.
bpms = st.one_of(st.none(), st.integers(min_value=40, max_value=220).map(float))
durations = st.integers(min_value=30, max_value=600).map(float)


@st.composite
def catalogues(draw: st.DrawFn) -> list[PlannerTrack]:
    """A catalogue that is always plannable, plus arbitrary noise.

    The two seeded tracks are what stop this strategy from spending its budget on catalogues
    that raise `NoValidSessionError` — hypothesis would filter almost everything away, trip
    its own health check, and the properties would go vacuously true without saying so. A Z1
    long enough to cool down and a Z2 long enough to warm up survive every goal filter,
    including `recovery`, so a plan always comes back.
    """
    seeded = [
        build_track("aaa_z1_anchor", bpm=90.0, duration_s=200.0),
        build_track("aab_z2_anchor", bpm=105.0, duration_s=200.0),
    ]
    noise = draw(
        st.lists(
            st.tuples(bpms, durations),
            min_size=0,
            max_size=25,
        )
    )
    return seeded + [
        build_track(f"n{index:03d}", bpm=bpm, duration_s=duration_s)
        for index, (bpm, duration_s) in enumerate(noise)
    ]


session_params = st.builds(
    SessionParams,
    level=st.sampled_from(LEVELS),
    goal=st.sampled_from(GOALS),
    duration_min=st.integers(min_value=20, max_value=120),
)

# The composite strategy does its own filtering, so hypothesis' too-much-filtering heuristic
# has nothing useful to say here.
planner_settings = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)


# ── Determinism ──────────────────────────────────────────────────────────────────────────


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_planning_is_deterministic(catalogue: list[PlannerTrack], params: SessionParams) -> None:
    assert plan_session(catalogue, params) == plan_session(catalogue, params)


@planner_settings
@given(catalogue=catalogues(), params=session_params, seed=st.integers())
def test_planning_is_order_independent(
    catalogue: list[PlannerTrack], params: SessionParams, seed: int
) -> None:
    """Rotating the catalogue is a permutation, and a permutation must change nothing."""
    if not catalogue:
        return
    offset = seed % len(catalogue)
    rotated = catalogue[offset:] + catalogue[:offset]

    assert plan_session(rotated, params).segments == plan_session(catalogue, params).segments


# ── Bookkeeping ──────────────────────────────────────────────────────────────────────────


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_no_track_vanishes(catalogue: list[PlannerTrack], params: SessionParams) -> None:
    plan = plan_session(catalogue, params)
    assert len(plan.segments) + len(plan.excluded) == len(catalogue)


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_no_track_is_placed_twice(catalogue: list[PlannerTrack], params: SessionParams) -> None:
    placed = [segment.track.track_id for segment in plan_session(catalogue, params).segments]
    assert len(placed) == len(set(placed))


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_segments_are_numbered_in_order(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    segments = plan_session(catalogue, params).segments
    assert [segment.order for segment in segments] == list(range(len(segments)))


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_duration_gap_is_the_arithmetic(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    plan = plan_session(catalogue, params)
    total_s = sum(segment.duration_s for segment in plan.segments)
    assert plan.duration_gap_s == total_s - params.target_duration_s


# ── E.2 deference ────────────────────────────────────────────────────────────────────────


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_every_segment_zone_is_the_e2_zone(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    """The planner labels a segment with E.2's answer, never with its own."""
    for segment in plan_session(catalogue, params).segments:
        assert segment.zone == e2.zone_of(segment.track.bpm_effective)


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_no_segment_lacks_a_bpm(catalogue: list[PlannerTrack], params: SessionParams) -> None:
    """E.2: no source -> bpm NULL -> excluded from the planner."""
    assert all(s.track.bpm_effective is not None for s in plan_session(catalogue, params).segments)


# ── The rules, as invariants ─────────────────────────────────────────────────────────────


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_the_session_is_always_anchored(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    segments = plan_session(catalogue, params).segments

    assert segments[0].zone in rules.WARMUP_ZONES
    assert segments[0].duration_s >= rules.WARMUP_MIN_DURATION_S
    assert segments[-1].zone == rules.COOLDOWN_ZONE
    assert segments[-1].duration_s >= rules.COOLDOWN_MIN_DURATION_S


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_the_goal_zone_filter_always_holds(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    allowed = rules.ALLOWED_ZONES_BY_GOAL[params.goal]
    assert all(s.zone in allowed for s in plan_session(catalogue, params).segments)


# `duration_accuracy` and `bpm_coverage` are deliberately absent: a catalogue too thin to
# fill the target, or one that is mostly BPM-less, is a fact about the input, and the plan
# reports it as a warning rather than refusing to exist. Every other check is something the
# planner controls, so it must hold on every plan it produces.
PLANNER_GUARANTEED = tuple(
    name
    for name in rules.CHECK_NAMES
    if name not in {"duration_accuracy", "bpm_coverage"}
)


@planner_settings
@given(catalogue=catalogues(), params=session_params)
def test_the_planner_never_emits_a_plan_the_evaluator_would_block(
    catalogue: list[PlannerTrack], params: SessionParams
) -> None:
    """The invariant that couples the two modules.

    Its negative half is the mutation check: there, sabotaged plans must fail. Here, honest
    ones must pass. An evaluator hardcoded to `review` dies on this test; one hardcoded to
    `safe` dies on that one.
    """
    result = evaluate(plan_session(catalogue, params))

    assert result.blocking_failures == []
    for check in PLANNER_GUARANTEED:
        assert result.checks[check] is True, check
