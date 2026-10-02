"""ADR-010: audio is never stored. A preview lives in a temporary file for the analysis only.

No network and no librosa: the HTTP session is a fake that serves a few bytes, and the analysis
step is replaced. What is pinned is the disk, not the BPM: after an analysis that succeeded,
one that failed, and a download that failed, no audio file remains anywhere.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from cyclebeat import http as http_module
from cyclebeat import resolve as resolve_module
from cyclebeat.http import PacedSession
from cyclebeat.models import RawTrack


class _Response:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        if self._fail:
            raise RuntimeError("HTTP 503")

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [b"ID3", b"\x00" * 1024]


class _FakeHttp:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def get(self, url: str, **kwargs: Any) -> _Response:
        return _Response(self._fail)


@pytest.fixture()
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Send every temporary file, and the working directory, to a directory we can inspect."""
    temp = tmp_path / "tmp"
    temp.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    monkeypatch.chdir(cwd)
    return tmp_path


def _session(scratch: Path, fail: bool = False) -> PacedSession:
    session = PacedSession(scratch / "http-cache", pacing=0.0)
    session.session = _FakeHttp(fail)
    return session


def _install_audio(monkeypatch: pytest.MonkeyPatch, analyse: Any, bpm: float | None) -> list[Path]:
    """Replace `cyclebeat.audio` so no librosa is needed. Returns the paths it was handed."""
    seen: list[Path] = []

    def fake_analyse(path: Path) -> object:
        seen.append(path)
        assert path.exists(), "the analysis must be given a real file"
        return analyse(path)

    fake = ModuleType("cyclebeat.audio")
    fake.analyse = fake_analyse  # type: ignore[attr-defined]
    fake.backbone_bpm = lambda tempo: bpm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cyclebeat.audio", fake)
    return seen


def _track() -> RawTrack:
    return RawTrack(
        track_id="42",
        source_platform="deezer",
        title="T",
        artist="A",
        duration_s=240.0,
        preview_url="https://example.invalid/p.mp3",
        ingested_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def _audio_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix in {".mp3", ".wav"}]


def _no_temp_file_left(scratch: Path) -> bool:
    return not any((scratch / "tmp").iterdir())


def test_a_successful_analysis_leaves_no_audio(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _install_audio(monkeypatch, lambda path: object(), 128.0)

    resolution = resolve_module.resolve_track_bpm(_session(scratch), _track())

    assert resolution is not None and resolution.bpm_raw == 128.0
    assert len(seen) == 1 and not seen[0].exists()
    assert _no_temp_file_left(scratch)
    assert _audio_files(scratch) == []


def test_a_failed_analysis_leaves_no_audio(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: Path) -> object:
        raise ValueError("librosa could not decode the file")

    seen = _install_audio(monkeypatch, boom, None)

    with pytest.raises(ValueError):
        resolve_module.resolve_track_bpm(_session(scratch), _track())

    assert len(seen) == 1 and not seen[0].exists()
    assert _no_temp_file_left(scratch)
    assert _audio_files(scratch) == []


def test_a_failed_download_leaves_no_audio(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install_audio(monkeypatch, lambda path: object(), 128.0)

    with pytest.raises(RuntimeError, match="503"):
        resolve_module.resolve_track_bpm(_session(scratch, fail=True), _track())

    assert seen == []  # never reached the analysis
    assert _no_temp_file_left(scratch)
    assert _audio_files(scratch) == []


def test_no_audio_cache_directory_is_created(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old code wrote `data/audio_cache/` relative to the working directory."""
    _install_audio(monkeypatch, lambda path: object(), 128.0)

    resolve_module.resolve_track_bpm(_session(scratch), _track())

    assert not (scratch / "cwd" / "data").exists()


def test_there_is_no_durable_download_api() -> None:
    """A method taking a destination path is how audio ended up on disk; it must not exist."""
    assert not hasattr(PacedSession, "download")
    assert not hasattr(resolve_module, "AUDIO_CACHE")
    assert hasattr(http_module, "temporary_download")


def test_a_track_without_a_preview_downloads_nothing(
    scratch: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _install_audio(monkeypatch, lambda path: object(), 128.0)
    track = _track().model_copy(update={"preview_url": None})

    assert resolve_module.resolve_track_bpm(_session(scratch), track) is None
    assert seen == []
    assert _no_temp_file_left(scratch)
