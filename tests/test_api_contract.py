"""Phase 0 contract guards for the API surface.

The v1 generate endpoint imported the orchestrator package that the purge
deleted. These tests pin the two things that must not break: the module still
imports, and the endpoint answers explicitly instead of crashing.
See `test_purge_guards.py` for the import-level check.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    api_main = importlib.import_module("api.main")
    return TestClient(api_main.app, raise_server_exceptions=False)


def test_api_main_imports_without_purged_modules():
    """`import api.main` must succeed with every purged v1 brick removed."""
    module = importlib.import_module("api.main")
    assert module.app.title == "CycleBeat API"


def test_health_is_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_session_returns_501_not_500(client: TestClient):
    """The endpoint fails explicitly (501), it does not crash on a dead import."""
    response = client.post(
        "/session/generate",
        json={"playlist_url": "https://example.com/playlist/1"},
    )
    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"].lower()


def test_generate_session_still_validates_its_body(client: TestClient):
    """A malformed body is a 422, not a 501 — validation runs before the stub."""
    response = client.post("/session/generate", json={})
    assert response.status_code == 422


def test_demo_session_is_served(client: TestClient):
    """The committed demo session is the fallback while generation is stubbed."""
    response = client.get("/session/demo")
    assert response.status_code == 200
    assert "session" in response.json()
