"""Pick the first free host port for each Compose service, then run Compose.

Every service keeps its conventional default (8000 API, 8080 Airflow, 9090
Prometheus, 3000 Grafana) because that is the port a reader expects. When another
local stack already holds one, this steps up to the next free one (9090 -> 9091 ->
9092 ...) instead of failing the whole `up` with `port is already allocated`.

Usage:
    python -m tools.compose_ports docker compose --profile pipeline up -d

Anything after the module name is the command to exec, with the CYCLEBEAT_*_PORT
variables injected into its environment. A variable already set by the caller is
honoured as-is and never probed -- pinning a port by hand always wins.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys

# env var -> (conventional default, human label). Order is the display order.
SERVICES: dict[str, tuple[int, str]] = {
    "CYCLEBEAT_API_PORT": (8000, "API (FastAPI)"),
    "CYCLEBEAT_AIRFLOW_PORT": (8080, "Airflow"),
    "CYCLEBEAT_PROMETHEUS_PORT": (9090, "Prometheus"),
    "CYCLEBEAT_GRAFANA_PORT": (3000, "Grafana"),
}

COMPOSE_PROJECT = "cyclebeat"
MAX_PROBE = 20  # give up rather than wander far from the conventional port


def _published_ports() -> tuple[set[int], set[int]]:
    """Host ports published by Docker, split into (ours, everyone else's).

    Ours are tracked separately rather than merged into one "taken" set: a container
    we are about to recreate still holds its port, and counting it as taken would push
    every service one slot up on each restart. Docker is the authority here -- a bind
    probe cannot see a port published on the Windows host from inside WSL.
    """
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set(), set()  # no daemon reachable: fall back to the bind probe alone

    ours: set[int] = set()
    theirs: set[int] = set()
    for line in out.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        mine = f"com.docker.compose.project={COMPOSE_PROJECT}" in row.get("Labels", "")
        for mapping in row.get("Ports", "").split(","):
            mapping = mapping.strip()
            if "->" not in mapping:  # `8000/tcp` is container-side only
                continue
            host = mapping.split("->", 1)[0]  # `0.0.0.0:8000`
            _, _, port = host.rpartition(":")
            if port.isdigit():
                (ours if mine else theirs).add(int(port))
    return ours, theirs


def _bindable(port: int) -> bool:
    """True if nothing local is listening. Catches non-Docker listeners."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # No SO_REUSEADDR: on Windows it lets the bind succeed on a port already
        # in use, which would turn this probe into a coin flip.
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def resolve() -> dict[str, int]:
    ours, theirs = _published_ports()
    chosen: dict[str, int] = {}
    for var, (default, _label) in SERVICES.items():
        pinned = os.environ.get(var)
        if pinned:
            chosen[var] = int(pinned)
            continue
        for candidate in range(default, default + MAX_PROBE):
            if candidate in theirs or candidate in chosen.values():
                continue
            # A port our own stack already publishes is free *for us* -- compose is about
            # to recreate that container on the same port. The bind probe must not veto
            # it, or the whole point of tracking `ours` separately is lost: from WSL the
            # Docker Desktop proxy is a real listener, so binding our own published port
            # fails and every restart walked the service one slot further up
            # (8080 -> 8081 taken -> 8082, which is how this was found).
            if candidate in ours or _bindable(candidate):
                chosen[var] = candidate
                break
        else:
            raise SystemExit(
                f"{var}: no free port in {default}-{default + MAX_PROBE - 1}. "
                f"Free one up, or pin it with {var}=<port>."
            )
    return chosen


def main(argv: list[str]) -> int:
    chosen = resolve()

    width = max(len(label) for _, label in SERVICES.values())
    for var, (default, label) in SERVICES.items():
        port = chosen[var]
        note = "" if port == default else f"  (default {default} was taken)"
        print(f"  {label:<{width}}  http://localhost:{port}{note}")
    print()

    if not argv:
        return 0

    env = {**os.environ, **{var: str(port) for var, port in chosen.items()}}
    return subprocess.run(argv, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
