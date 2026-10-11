"""Sessions live in Postgres, not inside the API container.

Over HTTP alone, a session stored in a SQLite file inside the `api` container would look
exactly like one stored in Postgres. Recreating the container tells them apart: a new
container starts from the image, so only the Postgres row survives. A plain restart would
not: Docker keeps the container's writable layer across a restart, SQLite file included.

Acts on the `cyclebeat-it` compose project only (the one `make test-integration` owns), and
must see the same CYCLEBEAT_*_PORT values the stack was started with -- the Makefile exports
them to both -- or the recreated `api` would come back on another port.
"""

from __future__ import annotations

import subprocess

import requests

from tests.integration.stack import (
    COMPOSE_PROJECT,
    REPO_ROOT,
    TIMEOUT_S,
    generate,
    wait_for_health,
)


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "-p", COMPOSE_PROJECT, "-f", str(REPO_ROOT / "docker-compose.yml"),
         *args],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def test_session_survives_an_api_recreate(api: str) -> None:
    created = generate(api).json()

    # Recreated, not restarted: a restart keeps the container's writable layer, where a
    # SQLite fallback would live, so it would prove nothing. `--no-deps` leaves Postgres up.
    result = _compose("up", "-d", "--no-deps", "--force-recreate", "api")
    assert result.returncode == 0, result.stderr
    wait_for_health(api, deadline_s=120)

    replay = requests.get(f"{api}/v1/sessions/{created['session_id']}", timeout=TIMEOUT_S)
    assert replay.status_code == 200, replay.text
    assert replay.json() == created
