"""The deterministic session evaluator (§15 phase 3, rules from ADR-007).

Takes a **finished plan** and judges it. It shares `cyclebeat.rules` with the planner — the
numbers — and shares no logic with it: every check below is re-derived from the segments, and
nothing here calls `plan_session`. An evaluator that asked the planner "was this fine?" would
pass any mutation check ever written, and the mutation check is this phase's exit criterion.

Because it reads a plan and nothing else, it also works on a session this planner did not
build: phase 6 can point it at an LLM-assembled one, and the copilot can be asked to explain
a `review` verdict, with no change here.

`verdict` is E.3's two-value enum. A blocking failure is not a third verdict — it lands in
`blocking_failures`, which phase 4 turns into the E.3 422 (ADR-007, decision 2).
"""

from __future__ import annotations

from collections.abc import Sequence

from cyclebeat import e2, rules
from cyclebeat.models import EvaluationResult, Segment, SessionParams, SessionPlan, Zone


def _zone(segment: Segment) -> Zone | None:
    """The segment's zone, RE-DERIVED from its BPM instead of read off the label.

    `Segment.zone` is what the planner claimed. Trusting it would let a saboteur relabel a
    Z5 as Z1 and walk past every intensity check — so the evaluator recomputes it through
    `e2.zone_of`, the same normative path the planner used, and never reads the field.

    `None` means the segment carries no usable BPM, which `all_segments_have_bpm` blocks on.
    """
    derived = e2.zone_of(segment.track.bpm_effective)
    return derived if derived is None else _as_zone(derived)


def _as_zone(value: str) -> Zone:
    """`e2` is stdlib-only and returns a plain `str`; the domain models use a Literal."""
    assert value in ("Z1", "Z2", "Z3", "Z4", "Z5")
    return value  # type: ignore[return-value]


def evaluate(plan: SessionPlan, params: SessionParams | None = None) -> EvaluationResult:
    """Run the ten ADR-007 checks over a plan.

    `params` defaults to the plan's own — pass it explicitly to judge a plan against
    parameters other than the ones it claims, which is what the mutation check does when it
    swaps a session's level out from under it.
    """
    params = params or plan.params
    segments = plan.segments

    checks = {
        "warmup_present": _warmup_present(segments),
        "cooldown_present": _cooldown_present(segments),
        "no_cold_sprint": _no_cold_sprint(segments),
        "all_segments_have_bpm": _all_segments_have_bpm(segments),
        "recovery_after_intensity": _recovery_after_intensity(segments),
        "no_consecutive_high": _no_consecutive_high(segments),
        "level_caps_respected": _level_caps_respected(segments, params),
        "goal_respected": _goal_respected(segments, params),
        "duration_accuracy": _duration_accuracy(segments, params),
        "bpm_coverage": _bpm_coverage_ok(plan),
    }

    # An empty session fails everything, which is correct — but it must not be reported as a
    # merely low score. It has no warmup and no cooldown, so it blocks.
    blocking = [name for name in rules.BLOCKING_CHECKS if not checks[name]]
    failed = [name for name, ok in checks.items() if not ok]

    return EvaluationResult(
        checks=checks,
        score=sum(checks.values()) / len(checks),
        # Blocking failures do NOT get their own verdict value: E.3 has two, and a blocked
        # session is one phase 4 refuses with a 422 rather than one it labels differently.
        verdict="safe" if not failed else "review",
        blocking_failures=sorted(blocking),
        warnings=[_warning_for(name) for name in failed],
    )


# ── Structure ────────────────────────────────────────────────────────────────────────────


def _warmup_present(segments: Sequence[Segment]) -> bool:
    if not segments:
        return False
    first = segments[0]
    return _zone(first) in rules.WARMUP_ZONES and first.duration_s >= rules.WARMUP_MIN_DURATION_S


def _cooldown_present(segments: Sequence[Segment]) -> bool:
    if not segments:
        return False
    last = segments[-1]
    return _zone(last) == rules.COOLDOWN_ZONE and last.duration_s >= rules.COOLDOWN_MIN_DURATION_S


def _no_cold_sprint(segments: Sequence[Segment]) -> bool:
    """No Z5 may START inside the opening window. Blocking: cold legs plus maximal effort."""
    for segment, starts_at_s in _with_start_times(segments):
        if _zone(segment) == rules.SPRINT_ZONE and starts_at_s < rules.COLD_SPRINT_WINDOW_S:
            return False
    return True


def _all_segments_have_bpm(segments: Sequence[Segment]) -> bool:
    """E.2, restated as a check: a track with no BPM is excluded from the planner.

    A segment carrying `bpm_effective = None` means the E.2 exclusion was bypassed somewhere,
    so the zone on it is meaningless and every other check is reading a fiction.
    """
    return all(segment.track.bpm_effective is not None for segment in segments)


# ── Intensity ────────────────────────────────────────────────────────────────────────────


def _recovery_after_intensity(segments: Sequence[Segment]) -> bool:
    """Every Z4/Z5 is followed by a Z1/Z2 within two positions.

    The cooldown counts: a high segment in the penultimate slot is followed by the Z1 that
    ends the session, which is a real recovery and not a loophole.
    """
    for index, segment in enumerate(segments):
        if _zone(segment) not in rules.HIGH_ZONES:
            continue
        window = segments[index + 1 : index + 1 + rules.RECOVERY_WITHIN_POSITIONS]
        if not any(_zone(following) in rules.RECOVERY_ZONES for following in window):
            return False
    return True


def _no_consecutive_high(segments: Sequence[Segment]) -> bool:
    run = 0
    for segment in segments:
        run = run + 1 if _zone(segment) in rules.HIGH_ZONES else 0
        if run > rules.MAX_CONSECUTIVE_HIGH:
            return False
    return True


def _level_caps_respected(segments: Sequence[Segment], params: SessionParams) -> bool:
    """The per-level caps. Level outranks goal: `intervals` never lifts a level cap."""
    level_rules = rules.LEVEL_RULES[params.level]
    sprints = [s for s in segments if _zone(s) == rules.SPRINT_ZONE]
    highs = [s for s in segments if _zone(s) in rules.HIGH_ZONES]

    if level_rules.max_high is not None and len(highs) > level_rules.max_high:
        return False
    if level_rules.max_sprints is not None and len(sprints) > level_rules.max_sprints:
        return False
    if level_rules.max_sprint_duration_s is not None:
        if any(s.duration_s > level_rules.max_sprint_duration_s for s in sprints):
            return False
    if level_rules.sprint_exclusion_ratio is not None:
        margin = level_rules.sprint_exclusion_ratio * params.target_duration_s
        for segment, starts_at_s in _with_start_times(segments):
            if _zone(segment) != rules.SPRINT_ZONE:
                continue
            # A sprint overlapping the excluded band counts as being in it — same definition
            # the planner places against, stated once in ADR-007.
            if starts_at_s < margin:
                return False
            if starts_at_s + segment.duration_s > params.target_duration_s - margin:
                return False
    return True


def _goal_respected(segments: Sequence[Segment], params: SessionParams) -> bool:
    """The per-goal zone filter and the intensity time budget."""
    allowed = rules.ALLOWED_ZONES_BY_GOAL[params.goal]
    if any(_zone(segment) not in allowed for segment in segments):
        return False

    budget_ratio = rules.HIGH_ZONE_BUDGET_BY_GOAL[params.goal]
    if budget_ratio is None:
        return True
    high_s = sum(s.duration_s for s in segments if _zone(s) in rules.HIGH_ZONES)
    return high_s <= budget_ratio * params.target_duration_s


# ── Budget ───────────────────────────────────────────────────────────────────────────────


def _duration_accuracy(segments: Sequence[Segment], params: SessionParams) -> bool:
    total_s = sum(segment.duration_s for segment in segments)
    return abs(total_s - params.target_duration_s) <= rules.DURATION_TOLERANCE_S


def _bpm_coverage_ok(plan: SessionPlan) -> bool:
    """Share of the catalogue that carried a BPM, recomputed from the plan alone.

    The evaluator never sees the input catalogue, so it reconstructs the denominator from the
    plan's own bookkeeping: every input track is either a segment or an exclusion, and the
    ones that had no BPM carry `EXCLUSION_NO_BPM`. That reconstruction is only valid because
    the planner accounts for every track — which `test_planner_properties.py` asserts, and
    `test_evaluator.py` cross-checks against the planner's own figure.
    """
    n_input = len(plan.segments) + len(plan.excluded)
    if not n_input:
        return False
    unresolved = sum(1 for item in plan.excluded if item.reason == rules.EXCLUSION_NO_BPM)
    return (n_input - unresolved) / n_input >= rules.MIN_BPM_COVERAGE


# ── Helpers ──────────────────────────────────────────────────────────────────────────────


def _with_start_times(segments: Sequence[Segment]) -> list[tuple[Segment, float]]:
    """Pair each segment with the session clock it starts at.

    Read off the segments themselves rather than trusting `order`: the mutation check
    reorders segments, and a check that indexed by `order` would evaluate the session the
    planner *meant* instead of the one it produced.
    """
    paired: list[tuple[Segment, float]] = []
    elapsed_s = 0.0
    for segment in segments:
        paired.append((segment, elapsed_s))
        elapsed_s += segment.duration_s
    return paired


_WARNINGS = {
    "warmup_present": "no warmup: the first segment must be Z1/Z2 and last at least 3 min",
    "cooldown_present": "no cooldown: the last segment must be Z1 and last at least 2 min",
    "no_cold_sprint": "cold sprint: a Z5 starts inside the first 5 minutes",
    "all_segments_have_bpm": "a segment carries no BPM, which E.2 excludes from the planner",
    "recovery_after_intensity": "a Z4/Z5 block is not followed by a Z1/Z2 within 2 positions",
    "no_consecutive_high": "more than 2 consecutive Z4/Z5 segments",
    "level_caps_respected": "the session breaks the caps of its level",
    "goal_respected": "the session breaks the zone rules of its goal",
    "duration_accuracy": "the session misses its target duration by more than 2 minutes",
    "bpm_coverage": "less than 60% of the catalogue carried a BPM",
}


def _warning_for(check: str) -> str:
    return f"{check}: {_WARNINGS[check]}"
