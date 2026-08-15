"""Tests for the normative E.2 rules used by the phase-1 source spike.

These guard appendix E.2, which forbids variants: a change here means a breaking data
contract change with impact analysis, not a tweak. No network, no librosa — `tools.spike.e2`
is stdlib-only precisely so this suite runs in the project environment.
"""

import math

import pytest

from tools.spike.e2 import (
    normalize_bpm,
    resolve,
    window_stability,
    zone_for,
)
from tools.spike.source_coverage import plan_windows

# --- E.2 normalization: while bpm > 180: bpm /= 2 ; while bpm < 70: bpm *= 2 -------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (128.0, 128.0),  # already inside the band, untouched
        (200.0, 100.0),  # single halving
        (360.0, 180.0),  # halving lands exactly on the upper bound
        (400.0, 100.0),  # two halvings
        (60.0, 120.0),  # single doubling
        (35.0, 70.0),  # doubling lands exactly on the lower bound
        (10.0, 80.0),  # three doublings
        (180.0, 180.0),  # upper bound is inclusive, not halved
        (70.0, 70.0),  # lower bound is inclusive, not doubled
    ],
)
def test_normalize_bpm_applies_the_e2_loops(raw: float, expected: float) -> None:
    assert normalize_bpm(raw) == pytest.approx(expected)


def test_normalize_bpm_always_lands_inside_the_band() -> None:
    for raw in (1.0, 33.3, 69.9, 70.0, 180.0, 180.1, 999.0, 12345.6):
        value = normalize_bpm(raw)
        assert value is not None
        assert 70.0 <= value <= 180.0


def test_normalize_bpm_is_idempotent() -> None:
    for raw in (10.0, 60.0, 128.0, 200.0, 400.0):
        once = normalize_bpm(raw)
        assert normalize_bpm(once) == pytest.approx(once)


@pytest.mark.parametrize("absent", [None, 0, 0.0, -1.0, math.nan, math.inf, -math.inf])
def test_normalize_bpm_treats_unusable_input_as_absence(absent: float | None) -> None:
    """Deezer encodes a missing BPM as 0; feeding it to the loops would never terminate."""
    assert normalize_bpm(absent) is None


# --- E.2 zones on bpm_effective ----------------------------------------------------------


@pytest.mark.parametrize(
    ("bpm", "zone"),
    [
        (70.0, "Z1"),
        (99.0, "Z1"),
        (100.0, "Z2"),
        (115.0, "Z2"),
        (116.0, "Z3"),
        (130.0, "Z3"),
        (131.0, "Z4"),
        (145.0, "Z4"),
        (146.0, "Z5"),
        (180.0, "Z5"),
    ],
)
def test_zone_for_matches_the_e2_bands(bpm: float, zone: str) -> None:
    assert zone_for(bpm) == zone


def test_zone_for_leaves_no_gap_between_integer_bands() -> None:
    """E.2 writes integer bands; every float must still land in exactly one zone."""
    for bpm in (115.4, 115.6, 130.2, 130.8, 145.49, 145.51):
        assert zone_for(bpm) in {"Z2", "Z3", "Z4", "Z5"}


def test_zone_for_propagates_absence() -> None:
    assert zone_for(None) is None


# --- E.2 confidence rule ------------------------------------------------------------------


def test_no_source_yields_null_bpm_excluded_from_the_planner() -> None:
    result = resolve({"deezer": None, "getsongbpm": None})
    assert result["bpm_effective"] is None
    assert result["confidence"] is None
    assert result["confidence_method"] == "unknown"
    assert result["n_sources_agree"] == 0


def test_single_source_yields_0_6() -> None:
    result = resolve({"deezer": 128.0, "getsongbpm": None})
    assert result["confidence"] == 0.6
    assert result["confidence_method"] == "single_source"
    assert result["bpm_effective"] == pytest.approx(128.0)


def test_two_sources_within_tolerance_yield_0_9() -> None:
    result = resolve({"deezer": 128.0, "librosa": 130.0})
    assert result["confidence"] == 0.9
    assert result["confidence_method"] == "cross_validated"
    assert result["n_sources_agree"] == 2


def test_agreement_is_inclusive_at_exactly_three_bpm() -> None:
    assert resolve({"deezer": 128.0, "getsongbpm": 131.0})["confidence_method"] == "cross_validated"


def test_agreement_is_measured_after_normalization() -> None:
    """256 halves to 128, so a half-time source still cross-validates — the E.2 answer to
    the half/double-time pitfall, rather than a local heuristic."""
    result = resolve({"deezer": 256.0, "getsongbpm": 128.0})
    assert result["confidence_method"] == "cross_validated"
    assert result["bpm_effective"] == pytest.approx(128.0)


def test_disagreement_without_librosa_is_flagged_for_review() -> None:
    result = resolve({"deezer": 100.0, "getsongbpm": 140.0})
    assert result["confidence"] == 0.3
    assert result["confidence_method"] == "review"
    assert result["review"] is True


def test_disagreement_with_librosa_is_arbitrated_by_librosa() -> None:
    result = resolve({"deezer": 100.0, "getsongbpm": 140.0, "librosa": 128.0})
    assert result["confidence_method"] == "librosa_arbitrated"
    assert result["bpm_effective"] == pytest.approx(128.0)
    assert result["review"] is False


def test_zero_valued_sources_do_not_count_as_agreeing_sources() -> None:
    """A Deezer 0 must not become a second source that drags confidence up."""
    result = resolve({"deezer": 0.0, "librosa": 128.0})
    assert result["confidence_method"] == "single_source"
    assert result["n_sources_agree"] == 1


# --- librosa stability, the decisive phase-1 measurement -----------------------------------


def test_two_agreeing_windows_are_usable() -> None:
    assert window_stability(128.0, 130.0) == "usable"


def test_stability_tolerance_is_inclusive_at_three_bpm() -> None:
    assert window_stability(128.0, 131.0) == "usable"
    assert window_stability(128.0, 131.5) == "unstable"


def test_disagreeing_windows_are_unstable() -> None:
    assert window_stability(100.0, 140.0) == "unstable"


def test_half_time_detection_on_one_window_still_counts_as_usable() -> None:
    """The classic librosa failure: one window locks onto double time. E.2 normalization
    collapses 256 back to 128, so this is agreement, not instability."""
    assert window_stability(256.0, 128.0) == "usable"


@pytest.mark.parametrize(
    ("a", "b"),
    [(None, 128.0), (128.0, None), (None, None), (0.0, 128.0)],
)
def test_a_window_without_an_estimate_is_too_short(a: float | None, b: float | None) -> None:
    """Never silently counted as usable — that would inflate the ADR-004 floor figure."""
    assert window_stability(a, b) == "too_short"


# --- Window planning: the instrument must not decide the result ---------------------------


def test_a_real_deezer_preview_is_analysable() -> None:
    """Regression on the first live run.

    Deezer previews measured 29.986 s against a 2x15 s floor, so four tracks out of five
    were discarded as `too_short` over 14 milliseconds — the instrument, not the audio,
    was producing the result. Any preview-length clip must yield two windows.
    """
    assert len(plan_windows(29.98625850340136)) == 2
    assert len(plan_windows(30.058163265306124)) == 2


def test_a_full_track_gets_two_disjoint_sixty_second_windows() -> None:
    windows = plan_windows(210.0)
    assert windows == [(30.0, 60.0), (90.0, 60.0)]
    (offset_a, length_a), (offset_b, _) = windows
    assert offset_a + length_a <= offset_b  # disjoint, so the two estimates are independent


def test_a_short_clip_is_split_into_two_halves_that_do_not_overlap() -> None:
    windows = plan_windows(29.98625850340136)
    (offset_a, length_a), (offset_b, length_b) = windows
    assert offset_a == 0.0
    assert offset_a + length_a == pytest.approx(offset_b)
    assert offset_b + length_b == pytest.approx(29.98625850340136)


def test_a_clip_too_short_for_two_windows_yields_none() -> None:
    """10 s per window is derived from E.2's own 70 BPM floor (~11.7 beats), not picked."""
    assert plan_windows(19.0) == []
    assert plan_windows(0.0) == []
    assert len(plan_windows(20.0)) == 2
