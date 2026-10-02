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
import os
import tempfile
import time
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PACING_SECONDS = 0.3  # floor imposed by E.8; never lower it
HTTP_TIMEOUT = 30
USER_AGENT = "cyclebeat/2.0 (+https://github.com/elliepsc/cyclebeat)"


@contextmanager
def temporary_download(http_session: Any, url: str) -> Iterator[Path]:
    """Download `url` to a temporary file that is deleted when the block exits.

    ADR-010: audio is never stored durably. The file lives only for the analysis, and the
    `finally` removes it whether the download failed, the caller raised, or all went well.
    Nothing here knows about a cache directory, so there is no path to leave audio in.
    """
    descriptor, name = tempfile.mkstemp(prefix="cyclebeat_preview_", suffix=".mp3")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            with http_session.get(url, stream=True, timeout=HTTP_TIMEOUT) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1 << 16):
                    handle.write(chunk)
        yield path
    finally:
        path.unlink(missing_ok=True)


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

    @contextmanager
    def download_temporary(self, url: str) -> Iterator[Path]:
        """Paced audio download into a temporary file removed on exit (see `temporary_download`).

        Not cached: ADR-010 forbids keeping audio, so a track that needs analysing again is
        downloaded again. Only the JSON metadata responses are cached (`get_json`).
        """
        self._wait()
        with temporary_download(self.session, url) as path:
            self.calls += 1
            yield path
