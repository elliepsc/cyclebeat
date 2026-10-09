"""tools/deploy.py: hook URL handling, deploy polling, smoke test. No network, no real sleep."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from tools import deploy
from tools.deploy import DeployError, Response

SHA = "a" * 40
SECRET_KEY = "s3cr3t-hook-key"
HOOK = f"https://api.render.com/deploy/srv-abc?key={SECRET_KEY}"
WEB = "https://cyclebeat-web.onrender.com"
API = "https://cyclebeat-api.onrender.com"


def reply(status: int = 200, body: Any = None, **headers: str) -> Response:
    return Response(status, {k.replace("_", "-"): v for k, v in headers.items()}, body)


class Clock:
    """A fake clock: `sleep` advances it, so timeouts are reached without waiting."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


# ── with_ref ──────────────────────────────────────────────────────────────────────────────


def test_with_ref_keeps_the_existing_key() -> None:
    url = deploy.with_ref(HOOK, SHA)
    assert url == f"https://api.render.com/deploy/srv-abc?key={SECRET_KEY}&ref={SHA}"
    assert parse_qsl(urlsplit(url).query) == [("key", SECRET_KEY), ("ref", SHA)]


def test_with_ref_on_a_url_without_a_query() -> None:
    assert deploy.with_ref("https://h.test/deploy/srv-abc", SHA) == (
        f"https://h.test/deploy/srv-abc?ref={SHA}"
    )


def test_with_ref_replaces_an_existing_ref() -> None:
    url = deploy.with_ref("https://h.test/d?key=k&ref=old&x=1", SHA)
    assert url == f"https://h.test/d?key=k&x=1&ref={SHA}"


def test_with_ref_does_not_rewrite_the_key_bytes() -> None:
    key = "a%2Bb%3Dc+d=="
    assert deploy.with_ref(f"https://h.test/d?key={key}", SHA) == (
        f"https://h.test/d?key={key}&ref={SHA}"
    )


# ── trigger ───────────────────────────────────────────────────────────────────────────────


def test_trigger_posts_the_hook_with_ref_and_reads_the_nested_id() -> None:
    calls: list[tuple[str, str]] = []

    def http(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        calls.append((method, url))
        return reply(200, {"deploy": {"id": "dep-123"}})

    assert deploy.trigger(http, "api", HOOK, SHA) == "dep-123"
    assert calls == [("POST", f"{HOOK}&ref={SHA}")]


@pytest.mark.parametrize("body", [{"id": "dep-1"}, {"deploy": {}}, {"deploy": "x"}, "ok", None])
def test_trigger_fails_without_deploy_id(body: Any) -> None:
    with pytest.raises(DeployError, match="no deploy.id"):
        deploy.trigger(lambda *a: reply(200, body), "web", HOOK, SHA)


def test_trigger_fails_on_http_error_without_leaking_the_url() -> None:
    with pytest.raises(DeployError, match="HTTP 404") as err:
        deploy.trigger(lambda *a: reply(404, "nope"), "api", HOOK, SHA)
    assert SECRET_KEY not in str(err.value)


def test_trigger_network_error_keeps_the_url_out_of_the_message() -> None:
    def http(*args: Any) -> Response:
        raise OSError("network error (URLError)")

    with pytest.raises(DeployError, match="unreachable") as err:
        deploy.trigger(http, "api", HOOK, SHA)
    assert SECRET_KEY not in str(err.value)


# ── wait_live ─────────────────────────────────────────────────────────────────────────────


def deploy_status(status: str, commit: str = SHA) -> Response:
    return reply(200, {"id": "dep-1", "status": status, "commit": {"id": commit}})


def scripted(statuses: list[Response]) -> Callable[..., Response]:
    queue = list(statuses)

    def http(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        assert headers["Authorization"] == "Bearer key"
        assert url == "https://api.render.com/v1/services/srv-1/deploys/dep-1"
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return http


def run_wait(http: Callable[..., Response], clock: Clock, **kw: Any) -> list[str]:
    lines: list[str] = []
    deploy.wait_live(
        http,
        "key",
        {"api": ("srv-1", "dep-1")},
        SHA,
        sleep=clock.sleep,
        clock=clock,
        log=lines.append,
        **kw,
    )
    return lines


def test_wait_live_follows_the_statuses_until_live_on_the_right_commit() -> None:
    clock = Clock()
    http = scripted(
        [deploy_status("created"), deploy_status("build_in_progress"), deploy_status("live")]
    )
    lines = run_wait(http, clock)
    assert [line.split(" is ")[1] for line in lines] == ["created", "build_in_progress", "live"]
    assert clock.now == 2 * deploy.POLL_INTERVAL_S


def test_wait_live_fails_when_live_on_another_commit() -> None:
    with pytest.raises(DeployError, match="live on commit " + "b" * 40):
        run_wait(scripted([deploy_status("live", commit="b" * 40)]), Clock())


@pytest.mark.parametrize("status", sorted(deploy.FAILED_STATUSES))
def test_wait_live_fails_on_every_failed_status(status: str) -> None:
    with pytest.raises(DeployError, match=status):
        run_wait(scripted([deploy_status("build_in_progress"), deploy_status(status)]), Clock())


def test_wait_live_gives_up_after_the_timeout_without_real_waiting() -> None:
    clock = Clock()
    with pytest.raises(DeployError, match="timed out after 1200 s"):
        run_wait(scripted([deploy_status("build_in_progress")]), clock)
    assert clock.now == deploy.DEPLOY_TIMEOUT_S


def test_wait_live_fails_at_once_on_a_rejected_api_key() -> None:
    clock = Clock()
    with pytest.raises(DeployError, match="rejected the API key"):
        run_wait(scripted([reply(401, {})]), clock)
    assert clock.now == 0


def test_wait_live_retries_through_a_transient_error() -> None:
    clock = Clock()
    http = scripted([reply(503, "busy"), deploy_status("live")])
    lines = run_wait(http, clock)
    assert "will retry" in lines[0]
    assert lines[-1].endswith("is live")


def test_wait_live_waits_for_both_services() -> None:
    statuses = {"dep-api": ["build_in_progress", "live"], "dep-web": ["live"]}

    def http(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        deploy_id = url.rsplit("/", 1)[1]
        queue = statuses[deploy_id]
        return deploy_status(queue.pop(0) if len(queue) > 1 else queue[0])

    clock = Clock()
    deploy.wait_live(
        http,
        "key",
        {"api": ("srv-1", "dep-api"), "web": ("srv-2", "dep-web")},
        SHA,
        sleep=clock.sleep,
        clock=clock,
        log=lambda _: None,
    )
    assert clock.now == deploy.POLL_INTERVAL_S


# ── smoke test ────────────────────────────────────────────────────────────────────────────

PLAN = {"session_id": "s1", "segments": [{"order": 0}]}


class Site:
    """A fake production: each endpoint can be broken independently."""

    def __init__(self, **broken: bool) -> None:
        self.broken = broken
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        self.calls.append((method, url))
        if method == "GET" and url == f"{API}/health":
            ok = not self.broken.get("health")
            return reply(200, {"status": "ok" if ok else "degraded"})
        if method == "POST" and url == f"{API}/v1/sessions/generate":
            assert body["source"] == {"type": "demo", "value": ""}
            if self.broken.get("generate"):
                return reply(422, {"reasons": ["empty_catalogue"]})
            segments = [] if self.broken.get("empty") else [{}]
            return reply(200, {"session_id": "s1", "segments": segments})
        if method == "OPTIONS" and url == f"{API}/v1/sessions/generate":
            assert headers["Origin"] == WEB
            origin = "https://other.test" if self.broken.get("cors") else WEB
            return reply(200, None, access_control_allow_origin=origin)
        if method == "GET" and url == WEB:
            return reply(500 if self.broken.get("web") else 200, "<html>")
        raise AssertionError((method, url))


def smoke(site: Callable[..., Response], clock: Clock, **kw: Any) -> list[str]:
    lines: list[str] = []
    deploy.smoke_test(
        site, API + "/", WEB + "/", sleep=clock.sleep, clock=clock, log=lines.append, **kw
    )
    return lines


def test_smoke_passes_on_a_healthy_site() -> None:
    site = Site()
    lines = smoke(site, Clock())
    assert lines == ["smoke health: ok", "smoke generate: ok", "smoke cors: ok", "smoke web: ok"]
    assert [m for m, _ in site.calls] == ["GET", "POST", "OPTIONS", "GET"]


@pytest.mark.parametrize(
    ("broken", "name"),
    [
        ("health", "health"),
        ("generate", "generate"),
        ("empty", "generate"),
        ("cors", "cors"),
        ("web", "web"),
    ],
)
def test_smoke_fails_on_each_broken_check_after_retrying(broken: str, name: str) -> None:
    clock = Clock()
    with pytest.raises(DeployError, match=f"smoke {name} failed"):
        smoke(Site(**{broken: True}), clock)
    assert clock.now == deploy.SMOKE_TIMEOUT_S


def test_smoke_cors_failure_points_at_the_render_yaml_setting() -> None:
    with pytest.raises(DeployError, match="CORS_ALLOW_ORIGINS"):
        smoke(Site(cors=True), Clock())


def test_smoke_retries_while_the_api_wakes_up() -> None:
    healthy = Site()
    attempts = {"n": 0}

    def sleepy(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        if url == f"{API}/health" and attempts["n"] < 3:
            attempts["n"] += 1
            raise OSError("network error (TimeoutError)")
        return healthy(method, url, headers, body)

    lines = smoke(sleepy, Clock())
    assert sum("retrying" in line for line in lines) == 3
    assert lines[-1] == "smoke web: ok"


# ── main ──────────────────────────────────────────────────────────────────────────────────


def test_main_smoke_only_needs_only_the_two_urls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(deploy, "http_request", Site())
    assert deploy.main(["--smoke-only"], {"API_URL": API, "WEB_URL": WEB}) == 0
    assert "smoke ok" in capsys.readouterr().out


def test_main_lists_missing_names_but_never_values(capsys: pytest.CaptureFixture[str]) -> None:
    env = {"GITHUB_SHA": SHA, "RENDER_API_KEY": "the-api-key"}
    assert deploy.main([], env) == 2
    err = capsys.readouterr().err
    assert "RENDER_DEPLOY_HOOK_API" in err
    assert "the-api-key" not in err and SHA not in err


def test_main_rejects_unknown_arguments() -> None:
    assert deploy.main(["--nope"], {}) == 2


def test_main_full_run_never_prints_the_hook_url_or_the_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = Site()

    def http(method: str, url: str, headers: Mapping[str, str], body: Any) -> Response:
        if url.startswith("https://hooks.test/"):
            return reply(200, {"deploy": {"id": "dep-" + url.split("/")[3].split("?")[0]}})
        if url.startswith(deploy.RENDER_API):
            return deploy_status("live")
        return site(method, url, headers, body)

    monkeypatch.setattr(deploy, "http_request", http)
    env = {
        "GITHUB_SHA": SHA,
        "RENDER_API_KEY": "the-api-key",
        "RENDER_DEPLOY_HOOK_API": f"https://hooks.test/api?key={SECRET_KEY}",
        "RENDER_DEPLOY_HOOK_WEB": f"https://hooks.test/web?key={SECRET_KEY}",
        "RENDER_API_SERVICE_ID": "srv-api",
        "RENDER_WEB_SERVICE_ID": "srv-web",
        "API_URL": API,
        "WEB_URL": WEB,
    }
    assert deploy.main([], env) == 0
    out = capsys.readouterr()
    assert "deploy ok" in out.out
    assert SECRET_KEY not in out.out + out.err
    assert "the-api-key" not in out.out + out.err


def test_main_failure_exits_1_without_leaking(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(deploy, "http_request", lambda *a: reply(500, "boom"))
    env = {name: "x" for name in deploy.DEPLOY_ENV} | {
        "RENDER_DEPLOY_HOOK_API": f"https://hooks.test/api?key={SECRET_KEY}"
    }
    assert deploy.main([], env) == 1
    out = capsys.readouterr()
    assert "deploy failed" in out.err and SECRET_KEY not in out.out + out.err
