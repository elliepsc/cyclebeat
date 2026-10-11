"""Shared constants and helpers for the integration suite (see conftest.py for the rules).

The target URLs are checked against the loopback allow-list HERE, at import, so no test
module can reach a request before the check has run.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
import requests

from tools.integration_target import NonLocalTargetError, local_base_url

REPO_ROOT = Path(__file__).resolve().parents[2]

# The compose project `make test-integration` creates. The persistence test acts on this
# project only, so it can never touch the developer's own `cyclebeat` stack.
COMPOSE_PROJECT = "cyclebeat-it"

# Generous for a cold container on a CI runner, but bounded: a hang is a failure.
TIMEOUT_S = 30

try:
    API_URL = local_base_url(os.environ.get("CYCLEBEAT_IT_API_URL", "http://localhost:8000"))
    WEB_URL = local_base_url(os.environ.get("CYCLEBEAT_IT_WEB_URL", "http://localhost:4173"))
except NonLocalTargetError as exc:  # refused at import, before the first request
    raise pytest.UsageError(f"integration target refused: {exc}") from exc


def wait_for_health(base_url: str, deadline_s: float) -> None:
    """Poll `/health` until it answers 200, or fail once `deadline_s` has passed."""
    end = time.monotonic() + deadline_s
    last = "no attempt"
    while time.monotonic() < end:
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                return
            last = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last = type(exc).__name__
        time.sleep(1)
    pytest.fail(f"API at {base_url} not healthy after {deadline_s:.0f}s (last: {last})")


def generate(api_url: str, **overrides: Any) -> requests.Response:
    """`POST /v1/sessions/generate` with the demo source -- the one that needs no network."""
    body = {
        "source": {"type": "demo", "value": ""},
        "level": "intermediate",
        "goal": "endurance",
        "duration_min": 45,
        **overrides,
    }
    return requests.post(f"{api_url}/v1/sessions/generate", json=body, timeout=TIMEOUT_S)
