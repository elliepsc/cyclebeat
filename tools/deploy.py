"""Deploy to Render from CI, then check the result (phase 9, `ci/deploy-job`).

Standard library only (no new dependency). Run by the `deploy` job of the CI workflow after
every test job is green, on `main` only:

    python -m tools.deploy              # trigger both deploy hooks, wait, then smoke-test
    python -m tools.deploy --smoke-only # smoke test only: needs API_URL and WEB_URL, no secret

Render deploys nothing by itself (`autoDeployTrigger: off` in render.yaml). The deploy hook
URL is a secret: it is never printed, and neither is any `urllib` error message, which embeds
the URL. Only status codes and error types reach the log.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from typing import Any
from urllib.parse import urlsplit, urlunsplit

RENDER_API = "https://api.render.com/v1"

POLL_INTERVAL_S = 15
DEPLOY_TIMEOUT_S = 20 * 60
SMOKE_TIMEOUT_S = 5 * 60
SMOKE_RETRY_S = 10
REQUEST_TIMEOUT_S = 90  # a sleeping free instance can take about a minute to answer

# Deploy statuses documented by the Render API (retrieve deploy). A deploy that ends in one
# of these will never become the live one.
FAILED_STATUSES = frozenset(
    {"build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated"}
)

DEPLOY_ENV = (
    "GITHUB_SHA",
    "RENDER_API_KEY",
    "RENDER_DEPLOY_HOOK_API",
    "RENDER_DEPLOY_HOOK_WEB",
    "RENDER_API_SERVICE_ID",
    "RENDER_WEB_SERVICE_ID",
    "API_URL",
    "WEB_URL",
)
SMOKE_ENV = ("API_URL", "WEB_URL")

GENERATE_BODY = {
    "source": {"type": "demo", "value": ""},
    "level": "beginner",
    "goal": "endurance",
    "duration_min": 30,
}


class DeployError(Exception):
    """A deploy or check failed. The message is safe to print (no URL, no secret)."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: Any  # parsed JSON when the body is JSON, else the raw text


# (method, url, headers, json body) -> Response. Raises OSError on a network failure.
Http = Callable[[str, str, Mapping[str, str], Any], Response]


def http_request(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
    """The real HTTP client. Never lets an exception carrying the URL escape."""
    data = None if body is None else json.dumps(body).encode()
    request_headers = dict(headers)
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as reply:
            return _response(reply.status, reply.headers, reply.read())
    except urllib.error.HTTPError as exc:
        return _response(exc.code, exc.headers, exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # `str(exc)` can contain the URL: keep the type only.
        raise OSError(f"network error ({type(exc).__name__})") from None


def _response(status: int, headers: Message, raw: bytes) -> Response:
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed: Any = json.loads(text)
    except ValueError:
        parsed = text
    return Response(status, {k.lower(): v for k, v in headers.items()}, parsed)


def with_ref(hook_url: str, sha: str) -> str:
    """Add `ref=<sha>` to a deploy hook URL, keeping its own query (`?key=...`) intact.

    The query is edited as a raw string. Decoding and re-encoding it would be free to rewrite
    the bytes of the key, and the key is the credential. An existing `ref` is replaced.
    """
    parts = urlsplit(hook_url)
    kept = [p for p in parts.query.split("&") if p and p.split("=", 1)[0] != "ref"]
    kept.append(f"ref={sha}")
    return urlunsplit(parts._replace(query="&".join(kept)))


def trigger(http: Http, name: str, hook_url: str, sha: str) -> str:
    """POST the hook for `sha` and return the new deploy's id (`{"deploy": {"id": ...}}`)."""
    try:
        reply = http("POST", with_ref(hook_url, sha), {}, None)
    except OSError as exc:
        raise DeployError(f"{name}: deploy hook unreachable: {exc}") from None
    if reply.status != 200:
        raise DeployError(f"{name}: deploy hook answered HTTP {reply.status}")
    deploy = reply.body.get("deploy") if isinstance(reply.body, dict) else None
    deploy_id = deploy.get("id") if isinstance(deploy, dict) else None
    if not isinstance(deploy_id, str) or not deploy_id:
        raise DeployError(f"{name}: deploy hook response has no deploy.id")
    return deploy_id


def wait_live(
    http: Http,
    api_key: str,
    deploys: Mapping[str, tuple[str, str]],
    sha: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    timeout_s: float = DEPLOY_TIMEOUT_S,
    interval_s: float = POLL_INTERVAL_S,
    log: Callable[[str], None] = print,
) -> None:
    """Poll every deploy until each is `live` on `sha`. `deploys`: name -> (service, deploy).

    Fails at once on a failed status, or on a deploy that went live with another commit.
    """
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    pending = dict(deploys)
    last: dict[str, str] = {}
    deadline = clock() + timeout_s
    while pending:
        for name, (service_id, deploy_id) in list(pending.items()):
            url = f"{RENDER_API}/services/{service_id}/deploys/{deploy_id}"
            try:
                reply = http("GET", url, headers, None)
            except OSError as exc:
                log(f"{name}: status check failed ({exc}), will retry")
                continue
            if reply.status in (401, 403):
                raise DeployError(f"Render API rejected the API key (HTTP {reply.status})")
            if reply.status != 200 or not isinstance(reply.body, dict):
                log(f"{name}: status check answered HTTP {reply.status}, will retry")
                continue
            status = str(reply.body.get("status"))
            if last.get(name) != status:
                log(f"{name}: deploy {deploy_id} is {status}")
                last[name] = status
            if status in FAILED_STATUSES:
                raise DeployError(f"{name}: deploy {deploy_id} ended as {status}")
            if status == "live":
                commit = (reply.body.get("commit") or {}).get("id")
                if commit != sha:
                    raise DeployError(
                        f"{name}: deploy {deploy_id} is live on commit {commit}, expected {sha}"
                    )
                del pending[name]
        if not pending:
            return
        if clock() >= deadline:
            raise DeployError(
                f"timed out after {int(timeout_s)} s waiting for: {', '.join(sorted(pending))}"
            )
        sleep(interval_s)


def _check(http: Http, name: str, check: Callable[[Http], None]) -> str | None:
    """Run one check. Return None if it passed, else the reason it failed."""
    try:
        check(http)
    except OSError as exc:
        return f"{name}: {exc}"
    except DeployError as exc:
        return str(exc)
    return None


def _check_health(api_url: str) -> Callable[[Http], None]:
    def run(http: Http) -> None:
        reply = http("GET", f"{api_url}/health", {}, None)
        if reply.status != 200 or reply.body != {"status": "ok"}:
            raise DeployError(f"GET /health answered HTTP {reply.status}, not the expected body")

    return run


def _check_generate(api_url: str) -> Callable[[Http], None]:
    def run(http: Http) -> None:
        reply = http("POST", f"{api_url}/v1/sessions/generate", {}, GENERATE_BODY)
        body = reply.body if isinstance(reply.body, dict) else {}
        if reply.status != 200 or not body.get("session_id") or not body.get("segments"):
            raise DeployError(
                f"POST /v1/sessions/generate answered HTTP {reply.status} "
                "(expected 200 with a session_id and segments)"
            )

    return run


def _check_cors(api_url: str, web_url: str) -> Callable[[Http], None]:
    def run(http: Http) -> None:
        headers = {
            "Origin": web_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }
        reply = http("OPTIONS", f"{api_url}/v1/sessions/generate", headers, None)
        allowed = reply.headers.get("access-control-allow-origin")
        if reply.status != 200 or allowed != web_url:
            raise DeployError(
                f"CORS preflight from {web_url} answered HTTP {reply.status} with "
                f"access-control-allow-origin={allowed!r}: check CORS_ALLOW_ORIGINS in render.yaml"
            )

    return run


def _check_web(web_url: str) -> Callable[[Http], None]:
    def run(http: Http) -> None:
        reply = http("GET", web_url, {}, None)
        if reply.status != 200:
            raise DeployError(f"GET {web_url} answered HTTP {reply.status}")

    return run


def smoke_test(
    http: Http,
    api_url: str,
    web_url: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    timeout_s: float = SMOKE_TIMEOUT_S,
    retry_s: float = SMOKE_RETRY_S,
    log: Callable[[str], None] = print,
) -> None:
    """Health, a real session generation, the CORS preflight from the site, and the site.

    Each check is retried until it passes or `timeout_s` runs out: a sleeping API answers
    slowly at first. A session is created by every run (accepted; see the roadmap).
    """
    api_url, web_url = api_url.rstrip("/"), web_url.rstrip("/")
    checks: list[tuple[str, Callable[[Http], None]]] = [
        ("health", _check_health(api_url)),
        ("generate", _check_generate(api_url)),
        ("cors", _check_cors(api_url, web_url)),
        ("web", _check_web(web_url)),
    ]
    deadline = clock() + timeout_s
    for name, check in checks:
        while True:
            failure = _check(http, name, check)
            if failure is None:
                log(f"smoke {name}: ok")
                break
            if clock() >= deadline:
                raise DeployError(f"smoke {name} failed: {failure}")
            log(f"smoke {name}: {failure}, retrying")
            sleep(retry_s)


def missing(names: tuple[str, ...], env: Mapping[str, str]) -> list[str]:
    return [name for name in names if not env.get(name)]


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    smoke_only = "--smoke-only" in args
    unknown = [a for a in args if a != "--smoke-only"]
    if unknown:
        print(f"unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        return 2

    absent = missing(SMOKE_ENV if smoke_only else DEPLOY_ENV, env)
    if absent:
        print(f"missing environment variable(s): {', '.join(absent)}", file=sys.stderr)
        return 2

    try:
        if not smoke_only:
            sha = env["GITHUB_SHA"]
            deploys = {
                name: (
                    env[f"RENDER_{name.upper()}_SERVICE_ID"],
                    trigger(http_request, name, env[f"RENDER_DEPLOY_HOOK_{name.upper()}"], sha),
                )
                for name in ("api", "web")
            }
            for name, (_, deploy_id) in deploys.items():
                print(f"{name}: deploy {deploy_id} triggered for {sha}")
            wait_live(http_request, env["RENDER_API_KEY"], deploys, sha)
        smoke_test(http_request, env["API_URL"], env["WEB_URL"])
    except DeployError as exc:
        print(f"deploy failed: {exc}", file=sys.stderr)
        return 1
    print("deploy ok" if not smoke_only else "smoke ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
