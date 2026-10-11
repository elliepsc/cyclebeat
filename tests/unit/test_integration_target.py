"""The integration suite's target guard: loopback allow-list, checked before any request."""

from __future__ import annotations

import pytest

from tools.integration_target import NonLocalTargetError, local_base_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:8000", "http://localhost:8000"),
        ("http://127.0.0.1:4173/", "http://127.0.0.1:4173"),
        ("http://[::1]:8000", "http://[::1]:8000"),
    ],
    ids=["localhost", "ipv4-loopback", "ipv6-loopback"],
)
def test_loopback_hosts_are_accepted(url: str, expected: str) -> None:
    assert local_base_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        # The production API and site (README, render.yaml).
        "https://cyclebeat-api.onrender.com",
        "https://cyclebeat-web.onrender.com/",
        # Private addresses: another machine on the network, still not this one.
        "http://10.0.0.1:8000",
        "http://192.168.1.20:8000",
        # Any other name, including ones built to look local.
        "http://example.com:8000",
        "http://api:8000",
        "http://localhost.example.com:8000",
        "http://127.0.0.1.nip.io:8000",
        "http://0.0.0.0:8000",
        # Credentials: the real host is after the `@`.
        "http://localhost@evil.example:8000",
        "http://user:pass@localhost:8000",
        # Not an HTTP base URL.
        "ftp://localhost:8000",
        "localhost:8000",
        "http://localhost:8000/v1",
        "http://localhost:notaport",
        "",
    ],
)
def test_everything_else_is_refused(url: str) -> None:
    with pytest.raises(NonLocalTargetError):
        local_base_url(url)
