# ADR-007 — The session construction rules: what the planner builds and what the evaluator checks

- **Status**: Accepted
- **Date**: 2026-08-21
- **Owner**: Ellie

## Context

Phase 3 (§15) asks for a **deterministic session engine**: a `WorkoutPlanner` that decides
the structure of a session and a `SessionEvaluator` that judges it, with a **mutation check**
as the blocking exit criterion. Both need a ruleset. No truth source provides one.

What *is* fixed, and is not re-decided here:

- **E.2** fixes the zones (`Z1 < 100`, `Z2 100-115`, `Z3 116-130`, `Z4 131-145`, `Z5 > 145`)
  on `bpm_effective`, the BPM normalization, and "no source → bpm NULL, **excluded from the
  planner**". Implemented once in `cyclebeat/e2.py`; the planner calls it and never re-derives
  a zone.
- **E.3** fixes the request (`level`, `goal`, `duration_min` 20..120) and the response
  (`verdict`, `segments[].zone`, `segments[].duration_s`, `duration_gap_s`, `warnings`).

What is **not** fixed anywhere: how long a warmup must be, how many sprints a beginner may
take, what `goal=intervals` actually changes, how close to the target duration is close
enough, or what makes a session `review` rather than `safe`. E.0.2 forbids filling those in
silently.

The only worked ruleset in the repo is `docs-notes/cyclebeat_ultraplan.md` (v1 era, phases 3
and 5 of that document). It is **not a truth source** — the truth-source order is repo code,
then Appendix E, then the V3 body — and it predates the E.3 enums. But it is this project's
own prior art, it is coherent, and its thresholds are ordinary indoor-cycling practice rather
than invented numbers. Discarding it would mean inventing a replacement, which is worse.

Four points were put to the owner before any code was written. All four are decided below.

## Options

### 1. Where the ruleset comes from

| Option | Behaviour | Cost |
|---|---|---|
| **A — adopt the v1 ruleset, promote it here** (chosen) | The thresholds of `cyclebeat_ultraplan.md`, re-mapped onto the E.3 enums, become normative in this ADR | Requires resolving two enum conflicts and three silences (below) |
| B — the owner dictates a fresh ruleset | No inherited assumptions | Phase 3 stays blocked on a spec that does not exist, and the replacement would be no better grounded |

Option A. This ADR — not the v1 note — is what phase 3 builds against; a future change edits
this file rather than a document that is explicitly not a truth source.

### 2. How a blocking failure is expressed

E.3 fixes `verdict` to **two** values, `safe | review`, and routes "no valid session possible"
to a 422 RFC 7807 with structured reasons in `detail`. The v1 note used three
(`safe_to_run | review_needed | blocked`).

| Option | Behaviour | Cost |
|---|---|---|
| **A — 2 values + a `blocking_failures` list** (chosen) | `EvaluationResult.verdict` is E.3's `safe`/`review`; blocking conditions land in a separate `blocking_failures: list[str]` | None — the contract stays exactly as E.3 writes it |
| B — 3 values internally, collapsed at the API boundary | Richer domain vocabulary | A second enum that the contract never sees, and a mapping to maintain in the phase-4 service |

Option A. **Truth-source order applied: E.3 wins over the v1 note.** A non-empty
`blocking_failures` is what phase 4 turns into the 422 — the planner raising
`NoValidSessionError` is the same event seen one step earlier.

### 3. What a segment's `duration_s` measures

ADR-005 makes the **30-second Deezer preview** the only audio the project holds, while
`dim_track.duration_s` carries the **full** track duration.

| Option | Behaviour | Cost |
|---|---|---|
| **A — full track duration** (chosen) | `segment.duration_s = dim_track.duration_s`; a 20-120 min session needs ~6-30 tracks | The planned timeline diverges from 30 s preview playback — a phase-5 problem |
| B — 30 s per segment | The plan matches what actually plays | A 20 min session needs 40 segments and a 120 min one needs 240 — more tracks than the catalogue holds, so most of E.3's legal `duration_min` range becomes unplannable |

Option A. Option B breaks E.3's own 20..120 range on the catalogue we have. The §15 note
already defers the player question ("**à trancher en phase 5** : le player joue désormais le
preview Deezer") — this ADR keeps the planner independent of that answer.

### 4. Where the exit criterion runs

§11 places property-based tests in `tests/unit/` and "adversarial + mutation check" in
`evals/`. The repo has a flat `tests/` and a `make eval` stub that exits 1 with "phase 6".

| Option | Behaviour | Cost |
|---|---|---|
| **A — create `evals/`, wire `make eval`** (chosen) | The exit criterion is one command: `make eval` green | A new folder and a Makefile target |
| B — everything under `tests/unit/` | One suite | Diverges from §11's stated layout, and leaves `make eval` a stub |

Option A.

## Decision

### The ruleset (normative)

Implemented once in `cyclebeat/rules.py` and imported by both the planner and the evaluator.
A threshold written twice is a threshold that drifts.

**Structure** — one warmup, then main blocks, then one cooldown.

| Rule | Value |
|---|---|
| `warmup_present` | first segment zone ∈ {Z1, Z2} **and** duration ≥ **180 s** |
| `cooldown_present` | last segment zone = **Z1** **and** duration ≥ **120 s** |
| `no_cold_sprint` | no Z5 segment starts within the first **300 s** of the session |
| `duration_accuracy` | \|actual − target\| ≤ **120 s** |
| `no_consecutive_high` | never more than **2** consecutive Z4/Z5 segments |
| `recovery_after_intensity` | every Z4/Z5 segment is followed by a Z1/Z2 within **2** positions |
| `bpm_coverage` | ≥ **0.60** of the input catalogue resolved to a BPM |
| `all_segments_have_bpm` | no segment carries `bpm_effective = NULL` (E.2, restated as a check) |

**Per level.**

| Level | Rule |
|---|---|
| `beginner` | at most **1** Z5 segment, each ≤ **30 s**, none in the first or last **20 %** of the session |
| `intermediate` | at most **3** Z4/Z5 segments, each followed by a Z1/Z2 within 2 positions |
| `advanced` | no Z5 count cap; cooldown still required |

**Per goal.**

| Goal | Rule |
|---|---|
| `endurance` | prefer Z2/Z3; Z4+Z5 ≤ **20 %** of target duration |
| `intervals` | Z4/Z5 allowed without a goal-level budget; warmup, cooldown and the level caps still apply |
| `recovery` | **Z1/Z2 only** |

**Blocking set** — `warmup_present`, `cooldown_present`, `no_cold_sprint`,
`all_segments_have_bpm`. Any of these failing means no valid session exists: the planner
raises `NoValidSessionError` (→ phase-4 422) and, if a plan is evaluated anyway — which is
what the mutation check does — the evaluator reports it in `blocking_failures`. Every other
check failing yields `verdict = "review"` plus a warning naming the check.

### The three silences, disambiguated

The v1 note is silent or unsatisfiable on three points. Each is resolved here rather than in
the code, and marked `ADR-007` at its site in `cyclebeat/rules.py` — the same discipline
`cyclebeat/e2.py` uses for its own disambiguations.

1. **`goal=recovery` excludes Z3 as well.** The v1 text reads "Z1/Z2 only, exclude Z4/Z5
   entirely", which names two different sets. `Z1/Z2 only` is taken literally: Z3, Z4 and Z5
   are all filtered out, each excluded track carrying the reason `goal_recovery_zone`. The
   stricter reading is the safe one for a recovery ride, and it is the one the phrase leads
   with.

2. **`goal=hiit` is renamed `intervals`.** E.3 fixes the enum to
   `endurance | intervals | recovery`. **Truth-source order applied: E.3 wins.** The rule
   attached to it is unchanged.

3. **For a beginner, the Z5 clause reduces to "no Z5".** With decision 3 above, a segment
   lasts a whole track — 3 to 4 minutes — so "each Z5 ≤ 30 s" can never be satisfied by real
   material, and a beginner session will contain no Z5 at all. This is a *consequence*, not a
   new rule: the 30 s clause is still implemented literally, so it re-activates unchanged if
   phase 5 shortens segments to preview length. The `beginner_safe` check therefore also
   keeps its `≤ 1 Z5` half, which would otherwise be unreachable code.

### Determinism (normative)

`plan_session` is a pure function: the same catalogue and parameters produce a byte-identical
plan, and **shuffling the input catalogue changes nothing**. No randomness, no reliance on
`dict`/`set` iteration order, every sort carrying a `track_id` tiebreak. This is not a style
preference — it is what makes the property-based tests and the mutation check reproducible,
and it is asserted directly as an invariant.

### Anti-circularity (normative)

The planner and the evaluator share `cyclebeat/rules.py` — its **constants**. They share no
**logic**: the evaluator re-derives every check from the finished plan and never calls into
the planner. An evaluator that asked the planner "was this fine?" would pass any mutation
check ever written.

The mutation check asserts **both directions** on the same fixtures: every sabotaged plan
must fail to come back `safe`, **and** the unmutated planner must come back `safe`. An
evaluator hardcoded to `review` fails the second half; one hardcoded to `safe` fails the
first.

## Consequences

- **Phase 3 has a truth source of its own.** Changing a threshold now means editing this ADR
  and `cyclebeat/rules.py` together, not reinterpreting a v1 note.
- **Nothing in E.2 or E.3 moves.** No zone, score, enum value or response field is altered.
  This ADR only fills what those appendices leave open, one layer above them.
- **The 422 branch is real, and tested.** A catalogue with no Z1 track, or nothing but Z5, has
  no valid session — `NoValidSessionError` rather than a session that quietly skips its
  cooldown. `evals/test_adversarial_playlists.py` is where that is proven.
- **`beginner` + `intervals` is a legal but narrow combination.** The level cap outranks the
  goal: intervals lifts the *goal* budget on Z4/Z5, it does not lift the beginner Z5 cap. A
  beginner asking for intervals gets a Z4-based session, which is the intended reading of
  "level rules are STRICT, not suggestions".
- **The evaluator is reusable beyond the planner.** Because it takes a finished plan and
  nothing else, phase 6 can point it at an LLM-assembled session, and the copilot can be
  asked to explain a `review` verdict, with no change here.
- **Reversible.** The engine reads `dim_track`; it writes nothing. Changing any threshold is a
  re-run of `make eval`, with no ingestion, no audio and no API call.

## References

- `docs-notes/CYCLEBEAT_PLAN_V3.md` §15 phase 3 (exit criterion), §7 (layering), §11 (test
  strategy), E.2 (zones, normalization, planner exclusion), E.3 (request/response shapes).
- `docs-notes/cyclebeat_ultraplan.md` phases 3 and 5 — the prior art this ADR promotes; **not**
  a truth source.
- `docs/adr/adr-005-deezer-preview-backbone.md` (why the only audio is a 30 s preview).
- `docs/adr/adr-006-e2-open-points.md` (`planner_eligible` is false exactly when
  `bpm_effective IS NULL`).
- `cyclebeat/rules.py`, `cyclebeat/planner.py`, `cyclebeat/evaluator.py`,
  `evals/test_mutation_check.py`.
