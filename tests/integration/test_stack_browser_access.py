"""The compose front reaches the compose API: right URL in the bundle, CORS open to it."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest
import requests

from tests.integration.stack import TIMEOUT_S


def _web_origins(web_url: str) -> list[str]:
    port = urlsplit(web_url).port
    return [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]


def test_web_serves_a_bundle_pointing_at_the_compose_api(web: str, api: str) -> None:
    index = requests.get(f"{web}/", timeout=TIMEOUT_S)
    assert index.status_code == 200
    scripts = re.findall(r'<script[^>]+src="([^"]+\.js)"', index.text)
    assert scripts, "index.html references the built bundle"

    bundle = "".join(
        requests.get(f"{web}{src}", timeout=TIMEOUT_S).text for src in scripts
    )
    # The compose API port, as the front sees it from the browser.
    expected = f"http://localhost:{urlsplit(api).port}"
    assert expected in bundle
    assert "onrender.com" not in bundle


@pytest.mark.parametrize("which", [0, 1], ids=["localhost", "127.0.0.1"])
def test_cors_preflight_allows_the_web_origin(web: str, api: str, which: int) -> None:
    origin = _web_origins(web)[which]
    response = requests.options(
        f"{api}/v1/sessions/generate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=TIMEOUT_S,
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_refuses_a_foreign_origin(api: str) -> None:
    response = requests.options(
        f"{api}/v1/sessions/generate",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
        timeout=TIMEOUT_S,
    )
    assert "access-control-allow-origin" not in response.headers
