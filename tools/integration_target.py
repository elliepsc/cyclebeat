"""Which URLs the integration suite may target: the local machine, and nothing else.

`tests/integration/` drives a real stack over HTTP and WRITES to it (sessions, feedback). Pointed
at production, it would fill the public demo with test sessions -- or worse, restart things. So
the target is checked against an ALLOW-list before the first request, never a deny-list: a
deny-list of "production-looking" hosts misses the next host nobody thought of.

Pure function, no I/O: `tests/unit/test_integration_target.py` covers it without a stack.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The loopback names a compose stack on this machine answers on. Exact match only:
# `localhost.example.com` or `127.0.0.1.nip.io` are other machines.
ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ALLOWED_SCHEMES = frozenset({"http", "https"})


class NonLocalTargetError(ValueError):
    """The URL does not point at this machine; the suite refuses to run against it."""


def local_base_url(url: str) -> str:
    """Return `url` without its trailing slash if it targets this machine, else raise.

    Rejected: any host outside `ALLOWED_HOSTS` (production, private IPs, any other name),
    a scheme other than http(s), credentials in the URL (`http://localhost@evil.example`
    parses with host `evil.example`, but is refused before that question even arises),
    and a path, query or fragment -- a base URL is scheme, host and port.
    """
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        parts.port  # noqa: B018 -- raises ValueError on a malformed port
    except ValueError as exc:
        raise NonLocalTargetError(f"not a valid URL: {url!r}") from exc

    if parts.scheme not in ALLOWED_SCHEMES:
        raise NonLocalTargetError(f"scheme must be http or https: {url!r}")
    if parts.username is not None or parts.password is not None:
        raise NonLocalTargetError(f"credentials are not allowed in the target URL: {url!r}")
    if host is None or host not in ALLOWED_HOSTS:
        raise NonLocalTargetError(
            f"integration tests only run against {sorted(ALLOWED_HOSTS)}, not {host!r} ({url!r})"
        )
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise NonLocalTargetError(f"expected a base URL (scheme, host, port only): {url!r}")

    return f"{parts.scheme}://{parts.netloc}"
