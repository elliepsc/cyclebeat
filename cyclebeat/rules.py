"""The ADR-007 session construction rules, as constants.

Imported by BOTH `cyclebeat.planner` and `cyclebeat.evaluator`. A threshold written twice is
a threshold that drifts: the planner would build to 180 s of warmup while the evaluator
checked for 120 s, and every test would still pass.

What the two modules share is exactly this file — the **numbers**. They share no **logic**:
the evaluator re-derives every check from a finished plan and never calls into the planner.
An evaluator that asked the planner "was this fine?" would pass any mutation check ever
written, which is the whole point of the phase-3 exit criterion (ADR-007, anti-circularity).

E.2 owns the zones and the BPM normalization (`cyclebeat.e2`); E.3 owns the request and
response shapes. Nothing here re-decides either — this file only fills what they leave open.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyclebeat.models import Goal, Level, Zone

# ── Structure ────────────────────────────────────────────────────────────────────────────

WARMUP_ZONES: frozenset[Zone] = frozenset({"Z1", "Z2"})
WARMUP_MIN_DURATION_S = 180.0

COOLDOWN_ZONE: Zone = "Z1"
COOLDOWN_MIN_DURATION_S = 120.0

# A Z5 may not START inside this opening window: sprinting on cold legs is the one failure
# mode with an injury attached, which is why it blocks rather than warns.
COLD_SPRINT_WINDOW_S = 300.0

# E.3 accepts 20..120 minutes; this is how close the plan must land. Two minutes is the v1
# figure, and it is roughly half a track — tight enough to mean something, loose enough that
# a real catalogue can hit it.
DURATION_TOLERANCE_S = 120.0

MAX_CONSECUTIVE_HIGH = 2
# "followed by a Z1/Z2 within N positions" — the recovery need not be immediate, but it may
# not be deferred past the next two tracks either.
RECOVERY_WITHIN_POSITIONS = 2

# Share of the INPUT catalogue that must have resolved to a BPM. Below this the session may
# be technically sound while being built from a fraction of what the user asked for, so it
# warns rather than blocks. ADR-006 measured the committed snapshot at 89.6 % eligible.
MIN_BPM_COVERAGE = 0.60

# ── Zone families ────────────────────────────────────────────────────────────────────────

HIGH_ZONES: frozenset[Zone] = frozenset({"Z4", "Z5"})
RECOVERY_ZONES: frozenset[Zone] = frozenset({"Z1", "Z2"})
SPRINT_ZONE: Zone = "Z5"

# ── Per level ────────────────────────────────────────────────────────────────────────────

# Level rules are STRICT, not suggestions: where a level cap and a goal budget disagree, the
# level wins. `beginner` + `intervals` is therefore legal but narrow — intervals lifts the
# goal budget on Z4/Z5, it does not lift the beginner Z5 cap (ADR-007, consequences).
#
# The two caps are deliberately distinct. `max_sprints` counts Z5 only; `max_high` counts
# Z4+Z5 together. The v1 note caps beginners on Z5 and intermediates on Z4/Z5, which is not
# the same axis, so collapsing them into one number would silently invent a Z4 cap for
# beginners that no source states.


@dataclass(frozen=True)
class LevelRules:
    """The per-level caps. `None` means "no cap on this axis", not zero."""

    max_sprints: int | None
    max_high: int | None
    # A Z5 may not last longer than this. ADR-007 disambiguation 3: with full-track segments
    # (decision 3) no real track satisfies 30 s, so for a beginner this reduces in practice
    # to "no Z5 at all". It is kept literal rather than rewritten as a ban, so it re-activates
    # unchanged if phase 5 ever shortens segments to preview length.
    max_sprint_duration_s: float | None
    # No Z5 in the first or last fraction of the session: cold legs at one end, no room to
    # recover at the other.
    sprint_exclusion_ratio: float | None


LEVEL_RULES: dict[Level, LevelRules] = {
    "beginner": LevelRules(
        max_sprints=1,
        max_high=None,
        max_sprint_duration_s=30.0,
        sprint_exclusion_ratio=0.20,
    ),
    "intermediate": LevelRules(
        max_sprints=None,
        max_high=3,
        max_sprint_duration_s=None,
        sprint_exclusion_ratio=None,
    ),
    # No count cap. `advanced` still gets a warmup and a cooldown: those are structural
    # rules, not level-based ones.
    "advanced": LevelRules(
        max_sprints=None,
        max_high=None,
        max_sprint_duration_s=None,
        sprint_exclusion_ratio=None,
    ),
}

# ── Per goal ─────────────────────────────────────────────────────────────────────────────

# ADR-007, disambiguation 1: `recovery` reads "Z1/Z2 only", so Z3 is filtered out as well as
# Z4/Z5. The v1 note named two different sets in one sentence ("Z1/Z2 only, exclude Z4/Z5
# entirely"); the phrase leads with the stricter one, and stricter is the safe reading for a
# recovery ride.
ALLOWED_ZONES_BY_GOAL: dict[Goal, frozenset[Zone]] = {
    "endurance": frozenset({"Z1", "Z2", "Z3", "Z4", "Z5"}),
    "intervals": frozenset({"Z1", "Z2", "Z3", "Z4", "Z5"}),
    "recovery": frozenset({"Z1", "Z2"}),
}

# Share of the TARGET duration that Z4+Z5 may occupy. None = no goal-level budget (the level
# cap still applies). `endurance` is the only goal that budgets intensity by time rather than
# by segment count.
HIGH_ZONE_BUDGET_BY_GOAL: dict[Goal, float | None] = {
    "endurance": 0.20,
    "intervals": None,
    "recovery": 0.0,
}

# Preference order for filling the main block. The planner walks this cycle repeatedly, so
# the order is not just a ranking — it is the SHAPE of the session. Ties inside a zone are
# broken by track_id, so the whole planner stays order-independent (ADR-007, determinism).
#
# Each cycle alternates intensity with recovery on purpose. A cycle that stacked its high
# zones together would leave `recovery_after_intensity` owed at exactly the slot the next
# high zone wants, and that zone would starve: an early version listed intervals as
# (Z4, Z3, Z5, Z2, Z1) and never placed a single Z5 in a 60-minute interval session, because
# Z5's turn always fell on the slot that owed a recovery.
MAIN_ZONE_PREFERENCE_BY_GOAL: dict[Goal, tuple[Zone, ...]] = {
    # Tempo-led, with intensity spaced out by a recovery on either side.
    "endurance": ("Z3", "Z2", "Z4", "Z1", "Z5"),
    # Work / recovery / work / recovery — the shape the goal is named after.
    "intervals": ("Z4", "Z2", "Z5", "Z1", "Z3"),
    "recovery": ("Z2", "Z1"),
}

# ── Exclusion reasons ────────────────────────────────────────────────────────────────────

# Why a candidate did not make the session. Stable codes rather than prose: the frontend
# groups on them, and the evaluator reads `EXCLUSION_NO_BPM` off a finished plan to recompute
# BPM coverage without ever seeing the catalogue. `goal_<goal>_zone` is built per goal.
EXCLUSION_NO_BPM = "no_bpm"
EXCLUSION_DUPLICATE = "duplicate_track_id"
EXCLUSION_INVALID_DURATION = "invalid_duration"
EXCLUSION_NOT_NEEDED = "not_needed"

# ── Checks ───────────────────────────────────────────────────────────────────────────────

# The ten deterministic checks of ADR-007, in report order. The v1 note listed nine, one of
# which was `coaching_present` — dropped here because phase 3 generates no text and the LLM
# arrives in phase 6. The level and goal rules are split into two checks instead of one, so a
# failure names which of the two was violated.
CHECK_NAMES: tuple[str, ...] = (
    "warmup_present",
    "cooldown_present",
    "no_cold_sprint",
    "all_segments_have_bpm",
    "recovery_after_intensity",
    "no_consecutive_high",
    "level_caps_respected",
    "goal_respected",
    "duration_accuracy",
    "bpm_coverage",
)

# Failing any of these means no valid session exists: the planner raises
# NoValidSessionError (which phase 4 maps to the E.3 422) and the evaluator reports them in
# `blocking_failures` rather than inventing a third verdict. Everything else downgrades the
# verdict to "review" and adds a warning.
BLOCKING_CHECKS: frozenset[str] = frozenset(
    {
        "warmup_present",
        "cooldown_present",
        "no_cold_sprint",
        "all_segments_have_bpm",
    }
)
