"""The deterministic session engine (§15 phase 3, rules from ADR-007).

`plan_session` is a **pure function**: the same catalogue and parameters produce the same
plan, and shuffling the input catalogue changes nothing. That is not a style preference — it
is what makes the property-based tests and the mutation check reproducible, so every sort
here carries a `track_id` tiebreak and nothing iterates a `set`.

Zones come from `cyclebeat.e2`, never from a local comparison and never from the `zone`
column handed in: E.2 forbids variants, and the half-time / double-time trap is answered by
its normalization rather than by a heuristic invented here.

No FastAPI, no I/O, no LLM. The layering of §7 depends on this module being importable and
testable on its own.
"""

from __future__ import annotations

from collections.abc import Sequence

from cyclebeat import e2, rules
from cyclebeat.models import (
    ExcludedTrack,
    Goal,
    PlannerTrack,
    Segment,
    SegmentRole,
    SessionParams,
    SessionPlan,
    Zone,
)


class NoValidSessionError(Exception):
    """No session satisfying the ADR-007 blocking rules can be built from this catalogue.

    Raised rather than returning a session that quietly skips its cooldown. Phase 4 maps this
    onto the E.3 422 (`RFC 7807`, structured reasons in `detail`) — which is why `reasons` is
    a list of stable machine-readable codes and not a prose message.
    """

    def __init__(self, *reasons: str) -> None:
        self.reasons = list(reasons)
        super().__init__("; ".join(reasons))


def plan_session(tracks: Sequence[PlannerTrack], params: SessionParams) -> SessionPlan:
    """Build a session from a catalogue, or raise `NoValidSessionError`.

    Every input track ends up either in a segment or in `excluded` with a reason: a track is
    never silently dropped. Asserted as a property, not left to review.
    """
    excluded: list[ExcludedTrack] = []

    candidates = _eligible(tracks, params.goal, excluded)

    # The cooldown is picked FIRST even though it comes last in the session. It is the more
    # constrained of the two anchors — it must be Z1, while a warmup may be Z1 *or* Z2 — so a
    # catalogue holding a single Z1 track would otherwise see the warmup take it and the
    # cooldown fail on a session that was perfectly buildable.
    cooldown = _pick_anchor(
        candidates,
        zones=frozenset({rules.COOLDOWN_ZONE}),
        min_duration_s=rules.COOLDOWN_MIN_DURATION_S,
    )
    if cooldown is None:
        raise NoValidSessionError("no_cooldown_candidate")
    candidates = [track for track in candidates if track.track_id != cooldown.track_id]

    warmup = _pick_anchor(
        candidates,
        zones=rules.WARMUP_ZONES,
        min_duration_s=rules.WARMUP_MIN_DURATION_S,
    )
    if warmup is None:
        raise NoValidSessionError("no_warmup_candidate")
    candidates = [track for track in candidates if track.track_id != warmup.track_id]

    main, leftover = _fill_main_block(
        candidates,
        params,
        warmup_s=warmup.duration_s,
        cooldown_s=cooldown.duration_s,
    )
    excluded.extend(
        ExcludedTrack(track_id=t.track_id, reason=rules.EXCLUSION_NOT_NEEDED) for t in leftover
    )

    placed = [warmup, *main, cooldown]
    segments = _to_segments(placed)
    total_s = sum(segment.duration_s for segment in segments)

    return SessionPlan(
        params=params,
        segments=segments,
        excluded=excluded,
        duration_gap_s=total_s - params.target_duration_s,
        warnings=_warnings(tracks, total_s, params),
    )


# ── Eligibility ──────────────────────────────────────────────────────────────────────────


def _eligible(
    tracks: Sequence[PlannerTrack], goal: Goal, excluded: list[ExcludedTrack]
) -> list[PlannerTrack]:
    """Drop what cannot be placed, recording a reason for each drop.

    The `zone` column handed in is ignored on purpose: it is recomputed from `bpm_effective`
    through `e2.zone_of`. `dim_track` materializes the same E.2 rule, so the two agree — but
    trusting the column would make the planner's correctness depend on an upstream write it
    does not control.
    """
    allowed = rules.ALLOWED_ZONES_BY_GOAL[goal]
    seen: dict[str, None] = {}
    kept: list[PlannerTrack] = []

    # Sorting up front is what makes the whole planner order-independent: two shuffles of the
    # same catalogue enter the loop below in the same order.
    for track in sorted(tracks, key=lambda t: t.track_id):
        if track.track_id in seen:
            excluded.append(
                ExcludedTrack(track_id=track.track_id, reason=rules.EXCLUSION_DUPLICATE)
            )
            continue
        seen[track.track_id] = None

        # E.2: no source -> bpm NULL -> excluded from the planner. This is exactly
        # `dim_track.planner_eligible` being false (ADR-006).
        zone = e2.zone_of(track.bpm_effective)
        if zone is None:
            excluded.append(ExcludedTrack(track_id=track.track_id, reason=rules.EXCLUSION_NO_BPM))
            continue
        if track.duration_s <= 0:
            excluded.append(
                ExcludedTrack(
                    track_id=track.track_id, reason=rules.EXCLUSION_INVALID_DURATION
                )
            )
            continue
        if zone not in allowed:
            excluded.append(ExcludedTrack(track_id=track.track_id, reason=f"goal_{goal}_zone"))
            continue

        kept.append(track.model_copy(update={"zone": zone}))

    return kept


def _pick_anchor(
    candidates: Sequence[PlannerTrack], zones: frozenset[Zone], min_duration_s: float
) -> PlannerTrack | None:
    """Choose the warmup or the cooldown: the SHORTEST track that clears the minimum.

    Shortest, because an anchor that overruns eats the budget the main block needs — a 7
    minute cooldown on a 20 minute session leaves no session. Ties break on `track_id`.
    """
    eligible = [
        track
        for track in candidates
        if track.zone in zones and track.duration_s >= min_duration_s
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda t: (t.duration_s, t.track_id))


# ── The main block ───────────────────────────────────────────────────────────────────────


def _fill_main_block(
    candidates: Sequence[PlannerTrack],
    params: SessionParams,
    warmup_s: float,
    cooldown_s: float,
) -> tuple[list[PlannerTrack], list[PlannerTrack]]:
    """Fill the middle of the session, respecting every ADR-007 rule as it goes.

    Constraints are enforced at placement time rather than repaired afterwards, so the plan
    that comes out is correct by construction. In particular the blocking rules can never be
    violated here, which is what lets the planner promise that its own output never carries a
    `blocking_failures` entry.

    Returns the placed tracks and the ones left over.
    """
    level_rules = rules.LEVEL_RULES[params.level]
    budget_ratio = rules.HIGH_ZONE_BUDGET_BY_GOAL[params.goal]
    high_budget_s = None if budget_ratio is None else budget_ratio * params.target_duration_s

    # One bucket per zone, each in `track_id` order. Round-robin across the goal's preference
    # order gives variety for free: endurance alternates Z3/Z2/Z4..., intervals leads on Z4.
    buckets: dict[Zone, list[PlannerTrack]] = {}
    for track in candidates:
        assert track.zone is not None  # guaranteed by _eligible
        buckets.setdefault(track.zone, []).append(track)
    for bucket in buckets.values():
        bucket.sort(key=lambda t: t.track_id)

    preference = rules.MAIN_ZONE_PREFERENCE_BY_GOAL[params.goal]
    placed: list[PlannerTrack] = []
    elapsed_s = 0.0
    n_high = 0
    n_sprints = 0
    high_seconds = 0.0
    anchor_duration_s = warmup_s + cooldown_s

    made_progress = True
    while made_progress:
        made_progress = False
        for zone in preference:
            bucket = buckets.get(zone, [])
            if not bucket:
                continue
            track = bucket[0]

            starts_at_s = warmup_s + elapsed_s
            if not _fits_duration(elapsed_s, track.duration_s, params, anchor_duration_s):
                continue
            if not _allowed_here(
                zone=zone,
                track=track,
                placed=placed,
                starts_at_s=starts_at_s,
                n_high=n_high,
                n_sprints=n_sprints,
                high_seconds=high_seconds,
                high_budget_s=high_budget_s,
                level_rules=level_rules,
                params=params,
            ):
                continue

            bucket.pop(0)
            placed.append(track)
            elapsed_s += track.duration_s
            if zone in rules.HIGH_ZONES:
                n_high += 1
                high_seconds += track.duration_s
                if zone == rules.SPRINT_ZONE:
                    n_sprints += 1
            made_progress = True

    leftover = sorted(
        (track for bucket in buckets.values() for track in bucket),
        key=lambda t: t.track_id,
    )
    return placed, leftover


def _fits_duration(
    elapsed_s: float, duration_s: float, params: SessionParams, anchor_duration_s: float
) -> bool:
    """Would this track still leave the session inside the ±2 min tolerance?"""
    total = anchor_duration_s + elapsed_s + duration_s
    return total <= params.target_duration_s + rules.DURATION_TOLERANCE_S


def _allowed_here(
    *,
    zone: Zone,
    track: PlannerTrack,
    placed: Sequence[PlannerTrack],
    starts_at_s: float,
    n_high: int,
    n_sprints: int,
    high_seconds: float,
    high_budget_s: float | None,
    level_rules: rules.LevelRules,
    params: SessionParams,
) -> bool:
    """Every ADR-007 placement rule, in one place, for one candidate."""
    # `recovery_after_intensity`, enforced FORWARD. A high segment needs a Z1/Z2 within two
    # positions, so when the segment two back was high and the one between was not a
    # recovery, this slot is the last chance to supply one — whatever zone was wanted here.
    #
    # This is the only rule that constrains a non-high candidate, which is why it sits above
    # the early return. It also completes itself at the end of the session for free: the
    # cooldown is Z1, so a high segment in either of the last two main slots is covered.
    if len(placed) >= rules.RECOVERY_WITHIN_POSITIONS:
        two_back = placed[-rules.RECOVERY_WITHIN_POSITIONS]
        between = placed[-rules.RECOVERY_WITHIN_POSITIONS + 1 :]
        owed = two_back.zone in rules.HIGH_ZONES and not any(
            segment.zone in rules.RECOVERY_ZONES for segment in between
        )
        if owed and zone not in rules.RECOVERY_ZONES:
            return False

    if zone not in rules.HIGH_ZONES:
        # Past that, a recovery or steady track never breaks a rule: every other constraint
        # bounds intensity. Placing one is also what unblocks the next high segment.
        return True

    # Blocking: sprinting on cold legs. `starts_at_s` includes the warmup.
    if zone == rules.SPRINT_ZONE and starts_at_s < rules.COLD_SPRINT_WINDOW_S:
        return False

    if level_rules.max_high is not None and n_high >= level_rules.max_high:
        return False
    if zone == rules.SPRINT_ZONE:
        if level_rules.max_sprints is not None and n_sprints >= level_rules.max_sprints:
            return False
        if (
            level_rules.max_sprint_duration_s is not None
            and track.duration_s > level_rules.max_sprint_duration_s
        ):
            return False
        if level_rules.sprint_exclusion_ratio is not None:
            margin = level_rules.sprint_exclusion_ratio * params.target_duration_s
            # A sprint OVERLAPPING the excluded band counts as being in it, so the tail is
            # measured on the segment's end, not its start. The band is taken against the
            # target rather than the final total, which is not known yet;
            # `duration_accuracy` keeps those two within ±2 min of each other.
            ends_at_s = starts_at_s + track.duration_s
            if starts_at_s < margin or ends_at_s > params.target_duration_s - margin:
                return False

    if high_budget_s is not None and high_seconds + track.duration_s > high_budget_s:
        return False

    # `no_consecutive_high`: never a third high track in a row. Enforcing it here — rather
    # than repairing afterwards — is why a Z1/Z2 track always separates intensity blocks.
    trailing = 0
    for previous in reversed(placed):
        if previous.zone in rules.HIGH_ZONES:
            trailing += 1
        else:
            break
    return trailing < rules.MAX_CONSECUTIVE_HIGH


# ── Assembly ─────────────────────────────────────────────────────────────────────────────


def _to_segments(placed: Sequence[PlannerTrack]) -> list[Segment]:
    """Number the tracks and label each one's role."""
    segments: list[Segment] = []
    n_cardio = 0
    for order, track in enumerate(placed):
        assert track.zone is not None  # guaranteed by _eligible
        role, n_cardio = _role_for(
            zone=track.zone,
            order=order,
            last_order=len(placed) - 1,
            previous=placed[order - 1] if order else None,
            n_cardio=n_cardio,
        )
        segments.append(
            Segment(
                order=order,
                track=track,
                zone=track.zone,
                role=role,
                duration_s=track.duration_s,
            )
        )
    return segments


def _role_for(
    *,
    zone: Zone,
    order: int,
    last_order: int,
    previous: PlannerTrack | None,
    n_cardio: int,
) -> tuple[SegmentRole, int]:
    """Label a segment.

    Narrative only — no rule keys off a role, so a mislabelled segment cannot make an unsafe
    session look safe. The evaluator reads zones, never roles.
    """
    if order == 0:
        return "warmup", n_cardio
    if order == last_order:
        return "cooldown", n_cardio
    if zone == "Z5":
        return "sprint", n_cardio
    if zone == "Z4":
        return "intensity", n_cardio
    if zone == "Z3":
        # Alternate the two labels so a long tempo stretch does not read as one flat block.
        return ("cardio" if n_cardio % 2 else "endurance"), n_cardio + 1
    if previous is not None and previous.zone in rules.HIGH_ZONES:
        return "recovery", n_cardio
    return ("endurance" if zone == "Z2" else "recovery"), n_cardio


def _warnings(
    tracks: Sequence[PlannerTrack], total_s: float, params: SessionParams
) -> list[str]:
    """Soft problems the plan carries. Blocking ones cannot reach here — they raise."""
    warnings: list[str] = []

    if abs(total_s - params.target_duration_s) > rules.DURATION_TOLERANCE_S:
        gap_min = (total_s - params.target_duration_s) / 60.0
        warnings.append(f"duration_accuracy: session misses the target by {gap_min:+.1f} min")

    coverage = _bpm_coverage(tracks)
    if coverage < rules.MIN_BPM_COVERAGE:
        warnings.append(
            f"bpm_coverage: only {coverage:.0%} of the catalogue carries a BPM "
            f"(floor {rules.MIN_BPM_COVERAGE:.0%})"
        )

    return warnings


def _bpm_coverage(tracks: Sequence[PlannerTrack]) -> float:
    """Share of the INPUT catalogue that resolved to a BPM.

    Measures *resolution*, not placement: a track the planner simply did not need is not a
    coverage problem. This is the question `mart_data_quality` asks of the warehouse, asked
    of one request's catalogue.

    The evaluator computes the same ratio from the finished plan instead — it counts the
    `no_bpm` exclusions — because it never sees the catalogue. Two derivations of one number
    is exactly the kind of thing that drifts, so `test_evaluator.py` asserts they agree.
    """
    if not tracks:
        return 0.0
    resolved = sum(1 for track in tracks if e2.zone_of(track.bpm_effective) is not None)
    return resolved / len(tracks)
