"""A deploy must not be an outage that cuts replies.

fly.toml had no kill_timeout (Fly stops a Machine 5s after its signal) and
uvicorn had no --timeout-graceful-shutdown, and the single app Machine was
replaced with the rolling default, which stops it before its replacement is
healthy. Chat turns stop-and-save inside the 30s grace window, which these
numbers promise.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_FLY = tomllib.loads((_REPO / "fly.toml").read_text())
_DOCKERFILE = (_REPO / "apps" / "api" / "Dockerfile").read_text()
GRACEFUL_SECONDS = 30
# Lifespan shutdown after uvicorn's drain: background tasks get up to 10s.
LIFESPAN_DRAIN_SECONDS = 10


def _graceful(command: str) -> int:
    found = re.search(r"--timeout-graceful-shutdown (\d+)", command)
    assert found is not None, f"no --timeout-graceful-shutdown in {command!r}"
    return int(found.group(1))


def test_uvicorn_drains_for_the_promised_window_in_both_launchers() -> None:
    docker_cmd = re.search(r"CMD \[.*uvicorn.*\]", _DOCKERFILE)
    assert docker_cmd is not None
    assert _graceful(_FLY["processes"]["app"]) == GRACEFUL_SECONDS
    assert _graceful(docker_cmd.group(0)) == GRACEFUL_SECONDS


def test_fly_waits_out_the_drain_before_killing() -> None:
    assert int(_FLY["kill_timeout"]) == 45
    assert int(_FLY["kill_timeout"]) > GRACEFUL_SECONDS + LIFESPAN_DRAIN_SECONDS


def test_bluegreen_has_a_health_check_for_every_process_group() -> None:
    """Blue-green waits for the new Machines' checks before moving traffic;
    a group without checks would count as healthy as soon as it started."""
    assert _FLY["deploy"]["strategy"] == "bluegreen"
    assert _FLY["deploy"]["release_command"].endswith("alembic upgrade head")
    groups = set(_FLY["processes"])
    checked = (
        set(_FLY["http_service"]["processes"]) if _FLY["http_service"].get("checks") else set()
    )
    checked |= {check["process"] for check in _FLY.get("checks", [])}
    assert groups <= checked, f"process groups without health checks: {groups - checked}"


def test_fly_checks_the_app_by_liveness_and_postgres_readiness_only() -> None:
    """/health/dependencies (the phone's connection check) answers 503 with Redis down.
    A Fly check on it would take every app Machine out of routing in a Redis blip."""
    paths = sorted(check["path"] for check in _FLY["http_service"]["checks"])
    assert paths == ["/health", "/health/ready"]
