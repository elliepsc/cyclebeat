"""Workflow (d): the data-quality reads, served from the warehouse baked into the image."""

from __future__ import annotations

import requests

from tests.integration.stack import TIMEOUT_S


def test_quality_coverage(api: str) -> None:
    response = requests.get(f"{api}/v1/quality/coverage", timeout=TIMEOUT_S)
    assert response.status_code == 200
    rows = response.json()
    assert rows, "the demo warehouse has at least one BPM source"
    for row in rows:
        assert row["n_tracks"] >= 0
        assert 0 <= row["pct_of_catalogue"] <= 100


def test_quality_summary(api: str) -> None:
    response = requests.get(f"{api}/v1/quality/summary", timeout=TIMEOUT_S)
    assert response.status_code == 200
    summary = response.json()
    assert summary["n_tracks"] > 0
    assert 0 < summary["n_with_bpm"] <= summary["n_tracks"]
