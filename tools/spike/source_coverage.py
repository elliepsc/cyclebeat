#!/usr/bin/env python
# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#     "librosa==0.10.2.post1",
#     "soundfile==0.12.1",
#     "requests>=2.32.0",
# ]
# ///
"""Phase-1 source spike — measure the real BPM coverage of the free sources.

Runs standalone through its PEP 723 header, so librosa (which drags numba/scipy, ~200 MB)
never enters `pyproject.toml`, `uv.lock` or the Docker image:

    uv run --script tools/spike/source_coverage.py --fetch --set all
    uv run --script tools/spike/source_coverage.py --report

This script MEASURES. It builds no resolver — that is phase 2.

Zero cost (E.8): every call is read-only, paced at >= 0.3 s, and cached on disk so a second
run re-fetches nothing. `--report` recomputes every figure from the raw output with no
network at all, which is what makes the report reproducible from a clean checkout.
"""

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
import urllib.parse
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from cyclebeat.e2 import normalize_bpm, resolve, window_stability  # noqa: E402

# --- Zero-cost guardrails (E.8) -----------------------------------------------------------

PACING_SECONDS = 0.3  # floor imposed by E.8; never lower it
HTTP_TIMEOUT = 30
USER_AGENT = "cyclebeat-phase1-spike/1.0 (+https://github.com/elliepsc/cyclebeat)"

SPIKE_DIR = REPO_ROOT / "data" / "spike"
CACHE_DIR = SPIKE_DIR / ".cache"
AUDIO_DIR = CACHE_DIR / "audio"
DEFAULT_RAW_OUTPUT = SPIKE_DIR / "raw_output.json"

# --- Endpoints ----------------------------------------------------------------------------
# The Deezer URLs come from the committed fixtures. GetSongBPM's is the documented one but has
# NOT been exercised — no key is held. The runbook asks you to confirm it against the dashboard
# when your key is issued, and `--getsongbpm-base` overrides it.
#
# ADR-005 removed the Jamendo/Creative-Commons path (`indie_cc` set, full-audio download): the
# BPM backbone is librosa on the Deezer 30 s preview, so there is no second catalogue to fetch.
# `data/spike/raw_output.json` still names `jamendo_tracks` in its `endpoints` block — it was
# written on 2026-07-29, before this pruning, and is left untouched as raw evidence.

DEEZER_CHART = "https://api.deezer.com/chart/0/tracks"
DEEZER_TRACK = "https://api.deezer.com/track/{track_id}"
DEEZER_SEARCH = "https://api.deezer.com/search"
GETSONGBPM_BASE = "https://api.getsong.co/search/"

# --- librosa windows ----------------------------------------------------------------------
# Two disjoint windows of the same track. Agreement within the E.2 +/-3 BPM tolerance is
# what makes an estimate "usable" — see cyclebeat/e2.window_stability.

WINDOW_A = (30.0, 60.0)  # 30 s -> 90 s
WINDOW_B = (90.0, 60.0)  # 90 s -> 150 s
SAMPLE_RATE = 22050

# Shortest window that can carry a tempo estimate. Derived from E.2's own lower bound
# rather than picked: at 70 BPM, 10 s contains ~11.7 beats, enough for the autocorrelation
# to lock on. It was 15 s in the first run, and that silently broke the measurement — a
# Deezer preview is 29.986 s, just under the resulting 2x15 s floor, so four of five tracks
# were reported `too_short` over 14 milliseconds. A threshold on the instrument must not be
# able to decide the result.
MIN_WINDOW_SECONDS = 10.0


@dataclass
class TrackMeasurement:
    """One track, one row of the report. Raw values only: E.2 is applied at report time."""

    set_name: str
    artist: str
    title: str
    deezer_id: str | None = None
    deezer_bpm_raw: float | None = None
    getsongbpm_bpm_raw: float | None = None
    librosa_window_a: float | None = None
    librosa_window_b: float | None = None
    audio_kind: str | None = None  # "deezer_preview" | None ("full_cc" predates ADR-005)
    audio_seconds: float | None = None
    latency_ms: dict[str, float] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class PacedSession:
    """requests session with the E.8 pacing floor and an on-disk response cache."""

    def __init__(self, cache_dir: Path, pacing: float = PACING_SECONDS) -> None:
        import requests

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.pacing = pacing
        self._last_call = 0.0
        self.calls = 0
        self.cache_hits = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.pacing:
            time.sleep(self.pacing - elapsed)
        self._last_call = time.monotonic()

    def get_json(self, url: str, params: dict[str, object] | None = None) -> tuple[dict, float]:
        """GET returning (payload, latency_ms). Cached responses report 0 ms latency."""
        key = f"{url}?{urllib.parse.urlencode(sorted((params or {}).items()), doseq=True)}"
        # sha256, not hash(): PYTHONHASHSEED randomizes str hashes per process, so hash()
        # would miss the cache on every new run and re-hit the APIs — an E.8 violation.
        cached = self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"
        if cached.exists():
            self.cache_hits += 1
            return json.loads(cached.read_text(encoding="utf-8")), 0.0

        self._wait()
        started = time.monotonic()
        response = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
        latency_ms = (time.monotonic() - started) * 1000
        response.raise_for_status()
        payload = response.json()
        cached.write_text(json.dumps(payload), encoding="utf-8")
        self.calls += 1
        return payload, latency_ms

    def download(self, url: str, destination: Path) -> Path:
        """Fetch an audio file once. Cached on disk; the cache is gitignored."""
        if destination.exists() and destination.stat().st_size > 0:
            self.cache_hits += 1
            return destination

        self._wait()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(url, stream=True, timeout=HTTP_TIMEOUT) as response:
            response.raise_for_status()
            with open(destination, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    handle.write(chunk)
        self.calls += 1
        return destination


# --- librosa ------------------------------------------------------------------------------


def _tempo(y, sr: int) -> float | None:
    """Single tempo estimate. librosa moved `tempo` between 0.9 and 0.10 — support both.

    Probed against librosa 0.10.2.post1 rather than assumed, after two wrong guesses:
    `hasattr(librosa.feature, "rhythm")` is **False** (the submodule is not exposed as an
    attribute until explicitly imported), so both `getattr(..., None)` and `try/except
    AttributeError` on that path fall through to the deprecated `librosa.beat.tempo`,
    which warns today and disappears in librosa 1.0. `librosa.feature.tempo` is the
    re-export that actually resolves.
    """
    import librosa

    func = getattr(librosa.feature, "tempo", None) or librosa.beat.tempo
    values = func(y=y, sr=sr)
    if values is None or len(values) == 0:
        return None
    return float(values[0])


def plan_windows(duration: float) -> list[tuple[float, float]]:
    """Choose the two (offset, length) windows to estimate tempo on.

    Pure and side-effect free so it can be tested without librosa — the first run proved
    this logic can silently decide the result on its own.

    Full tracks get the two disjoint 60 s windows; anything shorter is split in half; a
    track too short for two viable windows returns [] and is reported `too_short`.
    """
    if duration >= WINDOW_B[0] + MIN_WINDOW_SECONDS:
        return [WINDOW_A, WINDOW_B]
    if duration >= 2 * MIN_WINDOW_SECONDS:
        half = duration / 2
        return [(0.0, half), (half, half)]
    return []


def analyse_audio(path: Path) -> tuple[float | None, float | None, float | None]:
    """Estimate BPM on two disjoint windows.

    Returns (window_a_bpm, window_b_bpm, duration_seconds). A window that cannot be cut or
    estimated returns None, which `window_stability` reports as `too_short` — never as
    usable, since that would inflate the backbone coverage figure.
    """
    import librosa

    duration = float(librosa.get_duration(path=str(path)))
    windows = plan_windows(duration)
    if not windows:
        return None, None, duration

    estimates: list[float | None] = []
    for offset, length in windows:
        y, sr = librosa.load(str(path), sr=SAMPLE_RATE, offset=offset, duration=length)
        estimates.append(_tempo(y, sr) if y.size else None)
    return estimates[0], estimates[1], duration


# --- Sources ------------------------------------------------------------------------------


def fetch_deezer_track(session: PacedSession, track_id: str) -> tuple[dict, float]:
    return session.get_json(DEEZER_TRACK.format(track_id=track_id))


def search_deezer(session: PacedSession, artist: str, title: str) -> tuple[dict | None, float]:
    payload, latency = session.get_json(
        DEEZER_SEARCH, {"q": f'artist:"{artist}" track:"{title}"', "limit": 1}
    )
    data = payload.get("data") or []
    return (data[0] if data else None), latency


def fetch_getsongbpm(
    session: PacedSession, api_key: str, artist: str, title: str, base_url: str
) -> tuple[float | None, float]:
    payload, latency = session.get_json(
        base_url,
        {"api_key": api_key, "type": "both", "lookup": f"song:{title} artist:{artist}"},
    )
    search = payload.get("search")
    if not isinstance(search, list) or not search:
        return None, latency
    tempo = search[0].get("tempo")
    try:
        return (float(tempo) if tempo not in (None, "") else None), latency
    except (TypeError, ValueError):
        return None, latency


# --- Set builders -------------------------------------------------------------------------


def build_mainstream(session: PacedSession, limit: int) -> list[TrackMeasurement]:
    payload, _ = session.get_json(DEEZER_CHART, {"limit": limit})
    rows = []
    for item in payload.get("data", []):
        rows.append(
            TrackMeasurement(
                set_name="mainstream",
                artist=(item.get("artist") or {}).get("name", ""),
                title=item.get("title", ""),
                deezer_id=str(item.get("id")) if item.get("id") is not None else None,
            )
        )
    return rows


def build_mixed(_: PacedSession, csv_path: Path) -> list[TrackMeasurement]:
    with open(csv_path, encoding="utf-8", newline="") as handle:
        return [
            TrackMeasurement(set_name="mixed", artist=row["artist"], title=row["title"])
            for row in csv.DictReader(handle)
            if row.get("artist") and row.get("title")
        ]


# --- Fetch --------------------------------------------------------------------------------


def run_fetch(args: argparse.Namespace) -> int:
    session = PacedSession(CACHE_DIR)
    getsongbpm_key = os.environ.get("GETSONGBPM_API_KEY", "").strip()

    wanted = {"mainstream", "mixed"} if args.set == "all" else {args.set}
    measurements: list[TrackMeasurement] = []

    if "mainstream" in wanted:
        measurements += build_mainstream(session, args.limit)
    if "mixed" in wanted:
        measurements += build_mixed(session, SPIKE_DIR / "playlist_mixed.csv")

    # Deezer + GetSongBPM enrichment, and librosa on the Deezer preview when there is one.
    for row in measurements:
        try:
            if row.deezer_id is None:
                hit, latency = search_deezer(session, row.artist, row.title)
                row.latency_ms["deezer_search"] = latency
                if hit is None:
                    row.errors["deezer"] = "no search hit"
                else:
                    row.deezer_id = str(hit.get("id"))
            if row.deezer_id is not None:
                detail, latency = fetch_deezer_track(session, row.deezer_id)
                row.latency_ms["deezer"] = latency
                row.deezer_bpm_raw = detail.get("bpm")
                preview = detail.get("preview")
                if preview and not args.skip_audio:
                    path = session.download(preview, AUDIO_DIR / f"deezer_{row.deezer_id}.mp3")
                    a, b, seconds = analyse_audio(path)
                    row.librosa_window_a, row.librosa_window_b = a, b
                    row.audio_kind, row.audio_seconds = "deezer_preview", seconds
        except Exception as exc:  # noqa: BLE001 - a spike records failures, never aborts
            row.errors["deezer"] = f"{type(exc).__name__}: {exc}"

        if getsongbpm_key:
            try:
                bpm, latency = fetch_getsongbpm(
                    session, getsongbpm_key, row.artist, row.title, args.getsongbpm_base
                )
                row.getsongbpm_bpm_raw = bpm
                row.latency_ms["getsongbpm"] = latency
            except Exception as exc:  # noqa: BLE001
                row.errors["getsongbpm"] = f"{type(exc).__name__}: {exc}"
        else:
            row.errors["getsongbpm"] = "no GETSONGBPM_API_KEY set"

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endpoints": {
            "deezer_chart": DEEZER_CHART,
            "deezer_track": DEEZER_TRACK,
            "deezer_search": DEEZER_SEARCH,
            "getsongbpm": args.getsongbpm_base,
        },
        "http_calls": session.calls,
        "cache_hits": session.cache_hits,
        "pacing_seconds": PACING_SECONDS,
        "measurements": [asdict(m) for m in measurements],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(measurements)} tracks measured -> {args.output}")
    print(f"{session.calls} HTTP calls, {session.cache_hits} cache hits")
    return 0


# --- Report -------------------------------------------------------------------------------


def _percent(numerator: int, denominator: int) -> str:
    return "n/a" if denominator == 0 else f"{100 * numerator / denominator:.1f}%"


def summarise(measurements: list[dict]) -> dict[str, dict]:
    """Recompute every figure from raw values. No network: this is the reproducible path."""
    summary: dict[str, dict] = {}
    by_set: dict[str, list[dict]] = {}
    for row in measurements:
        by_set.setdefault(row["set_name"], []).append(row)

    for set_name, rows in sorted(by_set.items()):
        total = len(rows)
        deezer_ok = sum(1 for r in rows if normalize_bpm(r["deezer_bpm_raw"]) is not None)
        getsong_ok = sum(1 for r in rows if normalize_bpm(r["getsongbpm_bpm_raw"]) is not None)

        stability = Counter(
            window_stability(r["librosa_window_a"], r["librosa_window_b"]) for r in rows
        )
        confidence = Counter()
        agreements = 0
        multi_source = 0
        for row in rows:
            librosa_bpm = None
            if window_stability(row["librosa_window_a"], row["librosa_window_b"]) == "usable":
                librosa_bpm = normalize_bpm(row["librosa_window_a"])
            resolution = resolve(
                {
                    "deezer": row["deezer_bpm_raw"],
                    "getsongbpm": row["getsongbpm_bpm_raw"],
                    "librosa": librosa_bpm,
                }
            )
            confidence[resolution["confidence_method"]] += 1
            present = sum(
                1
                for value in (row["deezer_bpm_raw"], row["getsongbpm_bpm_raw"], librosa_bpm)
                if normalize_bpm(value) is not None
            )
            if present >= 2:
                multi_source += 1
                if resolution["confidence_method"] == "cross_validated":
                    agreements += 1

        latencies = [v for r in rows for v in r["latency_ms"].values() if v > 0]
        summary[set_name] = {
            "tracks": total,
            "deezer_bpm_usable": (deezer_ok, _percent(deezer_ok, total)),
            "getsongbpm_hit": (getsong_ok, _percent(getsong_ok, total)),
            "librosa_usable": (stability["usable"], _percent(stability["usable"], total)),
            "librosa_breakdown": dict(stability),
            "cross_source_agreement": (agreements, _percent(agreements, multi_source)),
            "confidence_distribution": dict(confidence),
            "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        }
    return summary


def run_report(args: argparse.Namespace) -> int:
    if not args.output.exists():
        print(f"No raw output at {args.output}. Run --fetch first.", file=sys.stderr)
        return 1

    payload = json.loads(args.output.read_text(encoding="utf-8"))
    summary = summarise(payload["measurements"])

    print(f"Source coverage - raw output generated at {payload['generated_at']}\n")
    for set_name, stats in summary.items():
        print(f"## {set_name} ({stats['tracks']} tracks)")
        print(f"  Deezer bpm usable     : {stats['deezer_bpm_usable'][1]}")
        print(f"  GetSongBPM hit        : {stats['getsongbpm_hit'][1]}")
        print(f"  librosa usable        : {stats['librosa_usable'][1]}")
        print(f"    breakdown           : {stats['librosa_breakdown']}")
        print(f"  Cross-source agreement: {stats['cross_source_agreement'][1]}")
        print(f"  Confidence            : {stats['confidence_distribution']}")
        print(f"  Median latency (ms)   : {stats['median_latency_ms']}\n")

    mainstream = summary.get("mainstream")
    if mainstream:
        usable, share = mainstream["deezer_bpm_usable"]
        ratio = usable / mainstream["tracks"] if mainstream["tracks"] else 0
        # The rule fired on the 2026-07-29 run (23.3%), and ADR-005 is the pivot it triggered:
        # Deezer demoted to enrichment, backbone = librosa on the Deezer preview.
        verdict = (
            "PIVOT - Deezer is enrichment, not backbone (ADR-005)"
            if ratio < 0.5
            else "Deezer usable as a backbone"
        )
        print(f"Decision rule (plan section 15): Deezer usable {share} -> {verdict}")

    if args.json:
        print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="live run; needs the API keys")
    parser.add_argument("--report", action="store_true", help="recompute offline from raw output")
    parser.add_argument("--set", choices=["all", "mainstream", "mixed"], default="all")
    parser.add_argument("--limit", type=int, default=30, help="tracks per set (default 30)")
    parser.add_argument("--output", type=Path, default=DEFAULT_RAW_OUTPUT)
    parser.add_argument("--getsongbpm-base", default=GETSONGBPM_BASE)
    parser.add_argument("--skip-audio", action="store_true", help="skip downloads and librosa")
    parser.add_argument("--json", action="store_true", help="also dump the summary as JSON")
    args = parser.parse_args()

    if args.fetch == args.report:
        parser.error("pass exactly one of --fetch or --report")
    return run_fetch(args) if args.fetch else run_report(args)


if __name__ == "__main__":
    raise SystemExit(main())
