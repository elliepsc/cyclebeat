"""Key workflows (a)-(c): generate a session, replay it, rate it -- over HTTP, on the stack."""

from __future__ import annotations

import requests

from tests.integration.stack import TIMEOUT_S, generate


def test_health(api: str) -> None:
    response = requests.get(f"{api}/health", timeout=TIMEOUT_S)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_demo_session(api: str) -> None:
    """The business check /health cannot make: the baked warehouse is really served.

    A compose config that hid the image's DuckDB answered /health 200 and 422
    `empty_catalogue` here (CLAUDE.md, known pitfalls).
    """
    response = generate(api)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["session_id"]
    assert plan["level"] == "intermediate"
    assert plan["goal"] == "endurance"
    assert plan["verdict"] in {"safe", "review"}
    assert plan["segments"], "a demo session has segments"
    # ADR-007: a session opens on a warmup and closes on a cooldown.
    assert plan["segments"][0]["role"] == "warmup"
    assert plan["segments"][-1]["role"] == "cooldown"


def test_replay_returns_the_stored_session(api: str) -> None:
    created = generate(api).json()
    response = requests.get(f"{api}/v1/sessions/{created['session_id']}", timeout=TIMEOUT_S)
    assert response.status_code == 200
    assert response.json() == created


def test_session_is_listed(api: str) -> None:
    created = generate(api).json()
    response = requests.get(f"{api}/v1/sessions", params={"limit": 200}, timeout=TIMEOUT_S)
    assert response.status_code == 200
    ids = [item["session_id"] for item in response.json()["items"]]
    assert created["session_id"] in ids


def test_feedback_is_recorded(api: str) -> None:
    created = generate(api).json()
    response = requests.post(
        f"{api}/v1/sessions/{created['session_id']}/feedback",
        json={"rating": "up", "note": "integration test"},
        timeout=TIMEOUT_S,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session_id"] == created["session_id"]
    assert body["rating"] == "up"
    assert body["note"] == "integration test"


def test_feedback_on_unknown_session_is_404(api: str) -> None:
    response = requests.post(
        f"{api}/v1/sessions/does-not-exist/feedback",
        json={"rating": "down"},
        timeout=TIMEOUT_S,
    )
    assert response.status_code == 404
