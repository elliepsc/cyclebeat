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

from tools.spike.e2 import normalize_bpm, resolve, window_stability  # noqa: E402

# --- Zero-cost guardrails (E.8) -----------------------------------------------------------

PACING_SECONDS = 0.3  # floor imposed by E.8; never lower it
HTTP_TIMEOUT = 30
USER_AGENT = "cyclebeat-phase1-spike/1.0 (+https://github.com/elliepsc/cyclebeat)"

SPIKE_DIR = REPO_ROOT / "data" / "spike"
CACHE_DIR = SPIKE_DIR / ".cache"
AUDIO_DIR = CACHE_DIR / "audio"
DEFAULT_RAW_OUTPUT = SPIKE_DIR / "raw_output.json"

# --- Endpoints ----------------------------------------------------------------------------
# Deezer and Jamendo URLs come from the committed fixtures. GetSongBPM's is the documented
# one but has NOT been exercised — no key is held. The runbook asks you to confirm it
# against the dashboard when your key is issued, and `--getsongbpm-base` overrides it.

DEEZER_CHART = "https://api.deezer.com/chart/0/tracks"
DEEZER_TRACK = "https://api.deezer.com/track/{track_id}"
DEEZER_SEARCH = "https://api.deezer.com/search"
JAMENDO_TRACKS = "https://api.jamendo.com/v3.0/tracks/"
GETSONGBPM_BASE = "https://api.getsong.co/search/"

JAMENDO_TAGS = ("electronic", "rock", "pop", "energetic")

# --- librosa windows ----------------------------------------------------------------------
# Two disjoint windows of the same track. Agreement within the E.2 +/-3 BPM tolerance is
# what makes an estimate "usable" — see tools/spike/e2.window_stability.

WINDOW_A = (30.0, 60.0)  # 30 s -> 90 s
WINDOW_B = (90.0, 60.0)  # 90 s -> 150 s
MIN_WINDOW_SECONDS = 15.0  # below this a window cannot carry a tempo estimate
SAMPLE_RATE = 22050


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
    audio_kind: str | None = None  # "full_cc" | "deezer_preview" | None
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
    """Single tempo estimate. librosa moved `tempo` between 0.9 and 0.10 — support both."""
    import librosa

    estimator = getattr(getattr(librosa, "feature", None), "rhythm", None)
    func = getattr(estimator, "tempo", None) or librosa.beat.tempo
    values = func(y=y, sr=sr)
    if values is None or len(values) == 0:
        return None
    return float(values[0])


def analyse_audio(path: Path) -> tuple[float | None, float | None, float | None]:
    """Estimate BPM on two disjoint windows.

    Returns (window_a_bpm, window_b_bpm, duration_seconds). A window that cannot be cut or
    estimated returns None, which `window_stability` reports as `too_short` — never as
    usable, since that would inflate the ADR-004 floor figure.
    """
    import librosa

    duration = float(librosa.get_duration(path=str(path)))

    if duration >= WINDOW_B[0] + MIN_WINDOW_SECONDS:
        windows = [WINDOW_A, WINDOW_B]
    elif duration >= 2 * MIN_WINDOW_SECONDS:
        # Short track (a Deezer 30 s preview lands here): split it in two halves.
        half = duration / 2
        windows = [(0.0, half), (half, half)]
    else:
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


def build_indie_cc(session: PacedSession, client_id: str, per_tag: int) -> list[dict]:
    """Jamendo CC tracks. Returns raw items so the caller keeps the full-audio URL."""
    items: list[dict] = []
    seen: set[str] = set()
    for tag in JAMENDO_TAGS:
        payload, _ = session.get_json(
            JAMENDO_TRACKS,
            {
                "client_id": client_id,
                "format": "json",
                "limit": per_tag,
                "order": "popularity_total",
                "tags": tag,
                "audioformat": "mp32",
                "include": "musicinfo",
            },
        )
        for item in payload.get("results", []):
            track_id = str(item.get("id"))
            if track_id not in seen:
                seen.add(track_id)
                items.append(item)
    return items


# --- Fetch --------------------------------------------------------------------------------


def run_fetch(args: argparse.Namespace) -> int:
    session = PacedSession(CACHE_DIR)
    jamendo_id = os.environ.get("JAMENDO_CLIENT_ID", "").strip()
    getsongbpm_key = os.environ.get("GETSONGBPM_API_KEY", "").strip()

    wanted = {"mainstream", "mixed", "indie_cc"} if args.set == "all" else {args.set}
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

    # The decisive set: librosa on FULL Creative-Commons audio (ADR-004 floor).
    if "indie_cc" in wanted:
        if not jamendo_id:
            print("JAMENDO_CLIENT_ID is not set - skipping the indie_cc set", file=sys.stderr)
        else:
            for item in build_indie_cc(session, jamendo_id, args.limit):
                row = TrackMeasurement(
                    set_name="indie_cc",
                    artist=item.get("artist_name", ""),
                    title=item.get("name", ""),
                )
                audio_url = item.get("audiodownload") or item.get("audio")
                try:
                    if audio_url and not args.skip_audio:
                        path = session.download(audio_url, AUDIO_DIR / f"jamendo_{item['id']}.mp3")
                        a, b, seconds = analyse_audio(path)
                        row.librosa_window_a, row.librosa_window_b = a, b
                        row.audio_kind, row.audio_seconds = "full_cc", seconds
                    else:
                        row.errors["librosa"] = "no audio url"
                except Exception as exc:  # noqa: BLE001
                    row.errors["librosa"] = f"{type(exc).__name__}: {exc}"
                measurements.append(row)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endpoints": {
            "deezer_chart": DEEZER_CHART,
            "deezer_track": DEEZER_TRACK,
            "deezer_search": DEEZER_SEARCH,
            "jamendo_tracks": JAMENDO_TRACKS,
            "jamendo_tags": list(JAMENDO_TAGS),
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
        verdict = "PIVOT to CSV+Jamendo+librosa (ADR-004 floor)" if ratio < 0.5 else "Deezer usable"
        print(f"Decision rule (plan section 15): Deezer usable {share} -> {verdict}")

    indie = summary.get("indie_cc")
    if indie:
        print(f"Decisive ADR-004 floor test: librosa on full CC audio {indie['librosa_usable'][1]}")

    if args.json:
        print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="live run; needs the API keys")
    parser.add_argument("--report", action="store_true", help="recompute offline from raw output")
    parser.add_argument("--set", choices=["all", "mainstream", "mixed", "indie_cc"], default="all")
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
