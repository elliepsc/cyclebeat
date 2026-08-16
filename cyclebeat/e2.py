"""Normative E.2 data rules, in pure Python.

Deliberately dependency-free (stdlib only): every layer imports it — the resolver, the
dbt-facing loaders, the tests, and the phase-1 spike script (which pulls librosa through
its own PEP 723 header). Nothing here may be re-implemented elsewhere: appendix E.2
forbids variants, so this module is moved between packages rather than copied.

Where E.2 is silent, the gap is filled by ADR-006 rather than invented locally. Both
points below were measured in the phase-1 spike and escalated to the owner before being
written down; each is marked ADR-006 at its site.
"""

import math

# E.2 normalization bounds and the single agreement tolerance of the appendix.
BPM_UPPER = 180.0
BPM_LOWER = 70.0
AGREEMENT_TOLERANCE = 3.0

CONFIDENCE_CROSS_VALIDATED = 0.9
CONFIDENCE_SINGLE_SOURCE = 0.6
CONFIDENCE_REVIEW = 0.3


def normalize_bpm(bpm: float | None) -> float | None:
    """Apply the E.2 normalization verbatim: halve above 180, double below 70.

    A missing, non-finite or non-positive value is *absence of a source*, not a BPM —
    Deezer encodes it as `0`, and E.2 counts a track with no source as `bpm NULL`. It is
    returned as None rather than fed to the loops, which would not terminate on 0.
    """
    if bpm is None:
        return None
    value = float(bpm)
    if not math.isfinite(value) or value <= 0:
        return None
    while value > BPM_UPPER:
        value /= 2.0
    while value < BPM_LOWER:
        value *= 2.0
    return value


def zone_for(bpm: float | None) -> str | None:
    """Map a normalized bpm_effective onto the E.2 zones.

    Z1 < 100, Z2 100-115, Z3 116-130, Z4 131-145, Z5 > 145.

    DISAMBIGUATION: the appendix states integer bands, which leaves 115.4 or 130.7
    unassigned. The value is rounded to the nearest integer first, so the bands stay
    exactly as written and every input lands in exactly one zone.
    """
    if bpm is None:
        return None
    rounded = round(bpm)
    if rounded < 100:
        return "Z1"
    if rounded <= 115:
        return "Z2"
    if rounded <= 130:
        return "Z3"
    if rounded <= 145:
        return "Z4"
    return "Z5"


def resolve(sources: dict[str, float | None]) -> dict[str, object]:
    """Apply the E.2 confidence rule to a mapping of source name -> raw BPM.

    Returns bpm_effective, zone, confidence, confidence_method, n_sources_agree and the
    review flag. Inputs are normalized here, so callers pass raw source values.

    E.2, no other formula allowed:
      - 2+ sources agreeing within +/-3 BPM  -> 0.9 `cross_validated`
      - exactly 1 source                     -> 0.6 `single_source`
      - disagreement > 3 BPM                 -> librosa arbitrates, else 0.3 + `review`
      - no source                            -> bpm NULL, excluded from the planner

    ADR-006 settles the two points E.2 leaves open (phase 1 measured them and refused to
    invent them):

    1. `bpm_effective` when sources agree is **librosa's** normalized value, not the mean.
       ADR-005 makes librosa-on-preview the backbone and the Deezer `bpm` field pure
       enrichment, so the enrichment source raises confidence and never moves the number.
       It also keeps one estimator across the catalogue: the majority `single_source`
       tracks already carry librosa's value, so the two buckets stay comparable. Measured
       cost against the mean on the 50 spike tracks: <= 1.48 BPM, and zero zone changes.
    2. Arbitration scores **0.6**, the `single_source` value: once the disagreeing source
       is discarded, exactly one trusted source remains, which is what 0.6 means. The
       method stays `librosa_arbitrated` so the case is still auditable in the marts.
    """
    normalized = {name: n for name, raw in sources.items() if (n := normalize_bpm(raw)) is not None}

    if not normalized:
        return {
            "bpm_effective": None,
            "zone": None,
            "confidence": None,
            "confidence_method": "unknown",
            "n_sources_agree": 0,
            "review": False,
        }

    if len(normalized) == 1:
        (bpm,) = normalized.values()
        return {
            "bpm_effective": bpm,
            "zone": zone_for(bpm),
            "confidence": CONFIDENCE_SINGLE_SOURCE,
            "confidence_method": "single_source",
            "n_sources_agree": 1,
            "review": False,
        }

    values = list(normalized.values())
    if max(values) - min(values) <= AGREEMENT_TOLERANCE:
        # ADR-006 (1): the backbone's value wins; enrichment only raised the confidence.
        # Falls back to the mean only when librosa is not among the agreeing sources,
        # which the ADR-005 pipeline does not produce but a CSV+Deezer pair would.
        bpm = normalized.get("librosa", sum(values) / len(values))
        return {
            "bpm_effective": bpm,
            "zone": zone_for(bpm),
            "confidence": CONFIDENCE_CROSS_VALIDATED,
            "confidence_method": "cross_validated",
            "n_sources_agree": len(values),
            "review": False,
        }

    if "librosa" in normalized:
        # ADR-006 (2): one trusted source survives arbitration, which is what 0.6 means.
        bpm = normalized["librosa"]
        return {
            "bpm_effective": bpm,
            "zone": zone_for(bpm),
            "confidence": CONFIDENCE_SINGLE_SOURCE,
            "confidence_method": "librosa_arbitrated",
            "n_sources_agree": 1,
            "review": False,
        }

    bpm = sum(values) / len(values)
    return {
        "bpm_effective": bpm,
        "zone": zone_for(bpm),
        "confidence": CONFIDENCE_REVIEW,
        "confidence_method": "review",
        "n_sources_agree": 0,
        "review": True,
    }


def window_stability(bpm_a: float | None, bpm_b: float | None) -> str:
    """Decide whether a librosa estimate counts as usable.

    The decisive measurement of the phase-1 spike. librosa almost always returns *a*
    number, so counting "librosa answered" would report ~100% and prove nothing. A track
    counts as usable only when two disjoint windows of the SAME track agree, using the
    +/-3 BPM tolerance already fixed by E.2 for cross-source agreement — reused, not
    invented.

    Returns "usable", "unstable", or "too_short" when a window could not be estimated.
    """
    a = normalize_bpm(bpm_a)
    b = normalize_bpm(bpm_b)
    if a is None or b is None:
        return "too_short"
    return "usable" if abs(a - b) <= AGREEMENT_TOLERANCE else "unstable"
