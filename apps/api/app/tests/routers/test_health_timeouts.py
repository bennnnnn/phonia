"""Readiness answers inside Fly's 5s check timeout even when a dependency stalls.

A stalled (not refusing) Redis used to hold ``/health/ready`` for the full
5s Redis socket timeout. Fly's check timeout is also 5s, so every machine
failed readiness at once and the fleet drained — the opposite of "Redis is
reported but not required".
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import jobs
from app.routers import health
from app.worker_health import create_worker_health_app

_STALL_S = 2.0
_BUDGET_S = 0.05


class _Session:
    def __init__(self, delay: float) -> None:
        self._delay = delay

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        await asyncio.sleep(self._delay)


class _Redis:
    def __init__(self, delay: float) -> None:
        self._delay = delay

    async def ping(self) -> bool:
        await asyncio.sleep(self._delay)
        return True


@pytest.mark.wall_clock
@pytest.mark.parametrize(
    "db_delay, redis_delay, expected_status, expected_body",
    [
        (0.0, 0.0, 200, {"status": "ok", "redis": "ok"}),
        (0.0, _STALL_S, 200, {"status": "ok", "redis": "degraded"}),
        (_STALL_S, 0.0, 503, {"detail": "Dependency check failed"}),
    ],
)
async def test_ready_bounds_each_dependency_check(
    db_delay: float, redis_delay: float, expected_status: int, expected_body: dict[str, str]
) -> None:
    from app.main import app

    with (
        patch.object(health, "SessionLocal", return_value=_Session(db_delay)),
        patch.object(health, "get_redis_client", return_value=_Redis(redis_delay)),
        patch.object(health, "READY_DB_TIMEOUT_SECONDS", _BUDGET_S),
        patch.object(health, "READY_REDIS_TIMEOUT_SECONDS", _BUDGET_S),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            started = time.monotonic()
            response = await client.get("/health/ready")
            elapsed = time.monotonic() - started
    assert response.status_code == expected_status
    assert response.json() == expected_body
    assert elapsed < _STALL_S / 2


@pytest.mark.wall_clock
@pytest.mark.parametrize(
    "redis_delay, expected_status",
    [(0.0, 200), (_STALL_S, 503)],
)
async def test_worker_ready_bounds_redis_ping(redis_delay: float, expected_status: int) -> None:
    import app.worker_health as worker_health

    app = create_worker_health_app()
    with (
        patch.object(jobs, "is_worker_alive", return_value=True),
        patch.object(worker_health.periodic, "started_periodic_unhealthy", return_value=[]),
        patch.object(worker_health, "get_redis_client", return_value=_Redis(redis_delay)),
        patch.object(worker_health, "READY_REDIS_TIMEOUT_SECONDS", _BUDGET_S),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            started = time.monotonic()
            response = await client.get("/health/ready")
            elapsed = time.monotonic() - started
    assert response.status_code == expected_status
    assert elapsed < _STALL_S / 2
