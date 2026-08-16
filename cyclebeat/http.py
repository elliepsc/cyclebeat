"""Paced, disk-cached HTTP session — the E.8 guardrails, in one place.

Lifted from the phase-1 spike (`tools/spike/source_coverage.py`) rather than rewritten:
both behaviours here were debugged against the real Deezer API during that run, and one
of them (the cache key) was a genuine E.8 violation caught by reading the code back.

E.8 requires: pacing >= 0.3 s between calls, aggressive response caching so review and CI
never re-fetch, and read-only calls. The lake is the permanent cache; this is the
short-lived one that stops a single run from hammering the API.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

PACING_SECONDS = 0.3  # floor imposed by E.8; never lower it
HTTP_TIMEOUT = 30
USER_AGENT = "cyclebeat/2.0 (+https://github.com/elliepsc/cyclebeat)"


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

    def cache_path(self, url: str, params: dict[str, Any] | None = None) -> Path:
        """Stable on-disk key for a request.

        sha256, not hash(): PYTHONHASHSEED randomizes str hashes per process, so hash()
        would miss the cache on every new run and re-hit the API — an E.8 violation, and
        the exact defect the phase-1 spike shipped with before it was caught.
        """
        query = urllib.parse.urlencode(sorted((params or {}).items()), doseq=True)
        key = f"{url}?{query}"
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"

    def get_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], float]:
        """GET returning (payload, latency_ms). Cached responses report 0 ms latency."""
        cached = self.cache_path(url, params)
        if cached.exists():
            self.cache_hits += 1
            payload: dict[str, Any] = json.loads(cached.read_text(encoding="utf-8"))
            return payload, 0.0

        self._wait()
        started = time.monotonic()
        response = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
        latency_ms = (time.monotonic() - started) * 1000
        response.raise_for_status()
        fetched: dict[str, Any] = response.json()
        cached.write_text(json.dumps(fetched), encoding="utf-8")
        self.calls += 1
        return fetched, latency_ms

    def download(self, url: str, destination: Path) -> Path:
        """Fetch an audio file once. Cached on disk; the cache is gitignored.

        ADR-005 leans on this: previews are cached permanently so a Deezer tightening
        degrades future ingestion rather than destroying what was already resolved.
        """
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
