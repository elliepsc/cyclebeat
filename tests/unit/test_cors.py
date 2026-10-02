"""CORS: the configured frontend origin is allowed, any other is not (phase 5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import CORS_ORIGINS_ENV, create_app

ALLOWED = "https://cyclebeat-web.example.test"
OTHER = "https://evil.example.test"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(CORS_ORIGINS_ENV, f"{ALLOWED}/, http://localhost:5173")
    return TestClient(create_app())


def test_allowed_origin_passes(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": ALLOWED})
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_other_origin_is_refused(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_of_allowed_origin_passes(client: TestClient) -> None:
    response = client.options(
        "/v1/sessions/generate",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_preflight_of_other_origin_is_refused(client: TestClient) -> None:
    response = client.options(
        "/v1/sessions/generate",
        headers={"Origin": OTHER, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_default_is_the_vite_dev_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CORS_ORIGINS_ENV, raising=False)
    client = TestClient(create_app())
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in client.get(
        "/health", headers={"Origin": OTHER}
    ).headers


def test_wildcard_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CORS_ORIGINS_ENV, "*")
    with pytest.raises(ValueError):
        create_app()


def test_empty_variable_allows_no_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CORS_ORIGINS_ENV, "")
    client = TestClient(create_app())
    for origin in ("http://localhost:5173", ALLOWED):
        response = client.get("/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in response.headers
