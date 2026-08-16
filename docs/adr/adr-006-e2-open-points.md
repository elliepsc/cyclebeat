# ADR-006 — The two points E.2 leaves open: `bpm_effective` and the arbitration score

- **Status**: Accepted
- **Date**: 2026-08-15
- **Owner**: Ellie

## Context

Appendix E.2 fixes the confidence *scores* and forbids any other formula. It does **not** say:

1. **which number becomes `bpm_effective`** when several sources agree within ±3 BPM, and
2. **what score a track gets after librosa arbitration** (the ">3 BPM disagreement, librosa
   arbitrates" branch).

The phase-1 spike hit both, refused to invent them, and recorded them as open inputs for the
phase-2 resolver (`docs/spikes/phase1-source-coverage.md`, open point 3). The spike shipped a
provisional behaviour — mean of the agreeing sources, and a **null** score for arbitration —
explicitly marked as a disambiguation rather than a decision.

Leaving them open is not viable in phase 2: `dim_track.confidence` is a real column, and a
NULL score for 8 % of the catalogue would be indistinguishable from "no source at all", which
E.2 gives a specific and different meaning (bpm NULL, excluded from the planner).

Both were measured over the 50 tracks of the committed spike output before being decided.

## Options

### 1. `bpm_effective` when sources agree

| Option | Behaviour | Measured effect |
|---|---|---|
| **A — librosa's value** (chosen) | The backbone's number wins; the Deezer `bpm` field only raises confidence | vs the mean: **≤ 1.48 BPM** difference (mean 0.73), **0 zone changes** across the 13 cross-validated tracks |
| B — mean of the agreeing sources | Averages two independent estimates; slightly lower variance | same figures, opposite sign |

The numbers do not decide this — the difference never crosses a zone boundary. The doctrine
does: **ADR-005 defines the Deezer `bpm` field as *enrichment*** — "participates in
cross-validation and raises confidence" — and an enrichment source that silently moves the
resolved value is not enrichment. Option A also keeps one estimator across the whole
catalogue: the majority `single_source` tracks already carry librosa's number, so
`cross_validated` and `single_source` tracks stay directly comparable instead of being
produced by two different formulas.

### 2. The score after librosa arbitration

| Option | Score | Cost |
|---|---|---|
| **A — 0.6, reusing `single_source`** (chosen) | Once the disagreeing source is discarded, exactly one trusted source remains — which is precisely what 0.6 means in E.2 | Reuses a value the appendix already fixes |
| B — a dedicated 0.45 | Marks "one source, and another actively disagreed" as weaker than an uncontested single source | **0.45 appears nowhere in E.2** — inventing a threshold is what E.0.2 forbids |

Option B is arguably more informative, and it was offered with that argument. It was rejected
because it invents a number, and because the information it would encode is not lost under
option A: `confidence_method` still reads `librosa_arbitrated`, so the case stays fully
auditable in `dim_track` and `mart_data_quality` without a bespoke score.

## Decision

1. **`bpm_effective` = librosa's normalized value** when the agreeing sources include librosa.
   When they do not — a CSV + Deezer pair, which the ADR-005 pipeline does not currently
   produce — the mean remains the answer, since there is no backbone value to prefer.
2. **librosa arbitration scores 0.6**, with `confidence_method = 'librosa_arbitrated'` and
   `n_sources_agree = 1`.

Both live in `cyclebeat/e2.py`, the single normative implementation, marked ADR-006 at their
site. E.2's scores, normalization and source enum are **unchanged**.

## Consequences

- **Every resolved track now carries a score.** `confidence IS NULL` means exactly one thing —
  no source had an opinion — which is what E.2 says it should mean. That is asserted by
  `dbt/tests/check_confidence_matches_method.sql`.
- **Measured distribution on the committed snapshot** (48 unique tracks — the warehouse grain
  is `track_id`, while the phase-1 report counts 50 *measurements*):
  `single_source` 27 (56.2 %), `cross_validated` 12 (25.0 %), `librosa_arbitrated` 4 (8.3 %),
  `unknown` 5 (10.4 %). **31 of 48 tracks (64.6 %) sit at 0.6** — the dominant regime ADR-005
  predicted, now including arbitration.
- **The planner (phase 3) inherits a clean contract**: `dim_track.planner_eligible` is false
  exactly when `bpm_effective IS NULL`, so the planner filters on a column instead of
  re-deriving E.2.
- **Not a breaking change to E.2**: no score, threshold or enum value is altered. This ADR only
  fills two gaps the appendix left, and the appendix is annotated with a dated note pointing
  here.
- **Reversible cheaply.** `raw.resolutions` stores each source's raw opinion, not the verdict,
  so reversing either decision is a re-run of `cross_validate` over the lake — no audio is
  re-downloaded and no API is called.

## References

- `docs-notes/CYCLEBEAT_PLAN_V3.md` E.2 (confidence rule + the dated 2026-08-15 notes).
- `docs/adr/adr-005-deezer-preview-backbone.md` (backbone vs enrichment).
- `docs/spikes/phase1-source-coverage.md` (the measurements, and open point 3 that raised this).
- `cyclebeat/e2.py`, `tests/test_spike_coverage.py` (the ADR-006 test block).
