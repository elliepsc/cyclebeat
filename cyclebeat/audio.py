"""librosa tempo estimation on the Deezer preview — the ADR-005 backbone.

**librosa is an optional extra** (`uv sync --extra audio`). It drags numba and scipy, and
the demo lake, the dbt build, CI and every test run off the committed snapshot instead —
so the import lives inside the functions and this module is safe to import without it.
That is what keeps E.8 true: no audio is ever fetched or analysed in review or CI.

The windowing rules and the two defects they encode come from the phase-1 spike, which
measured 82 % usable across 50 tracks with this exact logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cyclebeat.e2 import normalize_bpm, window_stability
from cyclebeat.models import WindowedTempo

WINDOW_A = (30.0, 60.0)  # 30 s -> 90 s
WINDOW_B = (90.0, 60.0)  # 90 s -> 150 s
SAMPLE_RATE = 22050

# Shortest window that can carry a tempo estimate. Derived from E.2's own 70 BPM lower
# bound rather than picked: at 70 BPM, 10 s contains ~11.7 beats, enough for the
# autocorrelation to lock on. It was 15 s in the phase-1 first run, and that silently
# decided the measurement — a Deezer preview is 29.986 s, 14 ms under the resulting
# 2x15 s floor, so four of the first five tracks were reported `too_short`.
MIN_WINDOW_SECONDS = 10.0


def plan_windows(duration: float) -> list[tuple[float, float]]:
    """Choose the two (offset, length) windows to estimate tempo on.

    Pure and side-effect free so it is testable without librosa — the phase-1 run proved
    this logic can decide the result on its own.

    Full tracks get the two disjoint 60 s windows; anything shorter is split in half; a
    track too short for two viable windows returns [] and is reported `too_short`.
    """
    if duration >= WINDOW_B[0] + MIN_WINDOW_SECONDS:
        return [WINDOW_A, WINDOW_B]
    if duration >= 2 * MIN_WINDOW_SECONDS:
        half = duration / 2
        return [(0.0, half), (half, half)]
    return []


def _tempo(y: Any, sr: int) -> float | None:
    """Single tempo estimate. librosa moved `tempo` between 0.9 and 0.10 — support both.

    Probed against librosa 0.10.2.post1 rather than assumed: `librosa.feature.rhythm` is
    NOT exposed as an attribute until explicitly imported, so both `getattr(..., None)`
    and `try/except AttributeError` on that path fall through to the deprecated
    `librosa.beat.tempo`, which warns today and disappears in librosa 1.0.
    `librosa.feature.tempo` is the re-export that actually resolves.
    """
    import librosa

    func = getattr(librosa.feature, "tempo", None) or librosa.beat.tempo
    values = func(y=y, sr=sr)
    if values is None or len(values) == 0:
        return None
    return float(values[0])


def analyse(path: Path) -> WindowedTempo:
    """Estimate BPM on two disjoint windows of a local audio file.

    A window that cannot be cut or estimated yields None, which `window_stability` reports
    as `too_short` — never as usable, since that would inflate the backbone coverage.
    """
    import librosa

    duration = float(librosa.get_duration(path=str(path)))
    windows = plan_windows(duration)
    estimates: list[float | None] = []
    for offset, length in windows:
        y, sr = librosa.load(path, sr=SAMPLE_RATE, offset=offset, duration=length)
        estimates.append(_tempo(y, sr) if len(y) else None)
    while len(estimates) < 2:
        estimates.append(None)

    a, b = estimates[0], estimates[1]
    return WindowedTempo(
        window_a=a, window_b=b, seconds=duration, stability=window_stability(a, b)
    )


def backbone_bpm(tempo: WindowedTempo) -> float | None:
    """The single librosa BPM that enters resolution, or None when it is not trustworthy.

    Only a `usable` pair counts: librosa almost always returns *a* number, so accepting
    every answer would report ~100 % coverage and prove nothing. This is the phase-1
    criterion, reusing E.2's own +/-3 BPM tolerance rather than inventing one.

    The two windows are normalized BEFORE being averaged. `window_stability` compares them
    after normalization, so a half-time pair such as (128, 256) is correctly `usable` —
    averaging the raw values would yield 192 and then normalize to 96, inventing a tempo
    neither window reported.
    """
    if tempo.stability != "usable":
        return None
    a = normalize_bpm(tempo.window_a)
    b = normalize_bpm(tempo.window_b)
    if a is None or b is None:
        return None
    return (a + b) / 2.0
