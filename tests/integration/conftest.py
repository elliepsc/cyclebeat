"""Black-box integration tests against a running compose stack (phase 8, criterion 9).

Run with `make test-integration`, which brings the stack up as its own compose project
(`cyclebeat-it`), runs this directory, then tears it down with `down -v`. Excluded from
`make test-unit` (`--ignore=tests/integration` in pyproject's addopts).

Two rules hold for every test here:

- **Local only.** The targets come from CYCLEBEAT_IT_API_URL / CYCLEBEAT_IT_WEB_URL and are
  checked against a loopback allow-list (`tools.integration_target`) when `stack.py` loads,
  before any request. These tests write sessions and recreate a container: never production.
- **A missing stack fails, it never skips.** If the API does not answer, every test errors.
  A suite that skips when its system is absent reports green while testing nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from tests.integration.stack import API_URL, TIMEOUT_S, WEB_URL


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test in this directory carries the `integration` marker."""
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def api() -> str:
    """The API base URL, once it is known to answer. Fails -- never skips -- otherwise."""
    try:
        response = requests.get(f"{API_URL}/health", timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        pytest.fail(
            f"No API at {API_URL} ({type(exc).__name__}). Start the stack with "
            "`make test-integration`, or `docker compose up --build`."
        )
    assert response.status_code == 200, f"/health answered {response.status_code}"
    return API_URL


@pytest.fixture(scope="session")
def web() -> str:
    """The web base URL, once it answers. Fails -- never skips -- otherwise."""
    try:
        requests.get(f"{WEB_URL}/", timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        pytest.fail(f"No web server at {WEB_URL} ({type(exc).__name__}).")
    return WEB_URL
