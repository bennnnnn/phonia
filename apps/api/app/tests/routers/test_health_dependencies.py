"""/health/dependencies: Postgres and Redis both answer, kept a few seconds per process.

/health is liveness only. With the database or Redis down it answered 200 while every
read failed, so the phone's connection check found the API "online": no "Can't reach
Recall" banner, and the list on screen was never read again when the outage ended.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.unavailable import unavailable_detail
from app.routers import health
from app.routers.health import DependencyCheck

# What a refused connection says: a host, a port, a version. None of it may reach a client.
_INTERNALS = "db.internal.example:5432 (PostgreSQL 16.4) refused"


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


class _Session:
    """A session whose ``SELECT 1`` answers, or fails as a refused connection does."""

    def __init__(self, deps: _Deps) -> None:
        self._deps = deps

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        self._deps.database_probes += 1
        await self._deps.gate.wait()
        if not self._deps.database_up:
            raise ConnectionRefusedError(_INTERNALS)


class _Redis:
    def __init__(self, deps: _Deps) -> None:
        self._deps = deps

    async def ping(self) -> bool:
        self._deps.redis_probes += 1
        if not self._deps.redis_up:
            raise ConnectionRefusedError(_INTERNALS)
        return True


class _Deps:
    def __init__(self) -> None:
        self.database_up = True
        self.redis_up = True
        self.database_probes = 0
        self.redis_probes = 0
        # Cleared, the database holds its answer until the test lets it go.
        self.gate = asyncio.Event()
        self.gate.set()
        self.clock = _Clock()


@pytest.fixture
def deps() -> Iterator[_Deps]:
    """Fake Postgres and Redis, and this process's check started afresh on a test clock."""
    fakes = _Deps()
    check = DependencyCheck(
        health.both_answer, ttl_seconds=health.DEPENDENCY_CHECK_TTL_SECONDS, clock=fakes.clock
    )
    with (
        patch.object(health, "SessionLocal", lambda: _Session(fakes)),
        patch.object(health, "get_redis_client", lambda: _Redis(fakes)),
        patch.object(health, "DEPENDENCY_CHECK", check),
    ):
        yield fakes


def _client() -> AsyncClient:
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.parametrize(
    "database_up, redis_up, expected",
    [(True, True, 200), (False, True, 503), (True, False, 503), (False, False, 503)],
)
async def test_dependencies_answer_503_when_either_is_down_and_liveness_stays_200(
    deps: _Deps, database_up: bool, redis_up: bool, expected: int
) -> None:
    deps.database_up, deps.redis_up = database_up, redis_up
    async with _client() as client:
        checked = await client.get("/health/dependencies")
        live = await client.get("/health")
        ready = await client.get("/health/ready")

    assert checked.status_code == expected
    assert checked.headers["cache-control"] == "no-store"
    if expected == 200:
        assert checked.json() == {"status": "ok"}
        assert "retry-after" not in checked.headers
    else:
        # The shared 503 body, nothing about which dependency or why.
        assert checked.json() == {"detail": unavailable_detail()}
        assert checked.headers["retry-after"] == "5"
        assert "internal" not in checked.text and "5432" not in checked.text
    # Liveness is untouched; Fly's readiness still needs only Postgres.
    assert live.status_code == 200 and live.json() == {"status": "ok"}
    assert ready.status_code == (200 if database_up else 503)
    if database_up:
        assert ready.json() == {"status": "ok", "redis": "ok" if redis_up else "degraded"}


async def test_calls_inside_the_window_share_one_probe(deps: _Deps) -> None:
    async with _client() as client:
        answers = [await client.get("/health/dependencies") for _ in range(20)]
        deps.clock.now += health.DEPENDENCY_CHECK_TTL_SECONDS - 0.1
        answers.append(await client.get("/health/dependencies"))

        assert [r.status_code for r in answers] == [200] * 21
        assert (deps.database_probes, deps.redis_probes) == (1, 1)

        # Past the window: the next call probes again, and sees the outage.
        deps.clock.now += 0.2
        deps.database_up = False
        assert (await client.get("/health/dependencies")).status_code == 503
        assert (deps.database_probes, deps.redis_probes) == (2, 2)


async def _until(condition: Callable[[], bool]) -> None:
    for _ in range(1_000):
        if condition():
            return
        await asyncio.sleep(0)
    raise AssertionError("never happened")


async def test_concurrent_calls_wait_for_the_one_probe_in_flight(deps: _Deps) -> None:
    deps.gate.clear()
    async with _client() as client:
        calls = [asyncio.create_task(client.get("/health/dependencies")) for _ in range(50)]
        await _until(lambda: deps.database_probes == 1)
        deps.gate.set()
        answers = await asyncio.gather(*calls)

    assert [r.status_code for r in answers] == [200] * 50
    assert (deps.database_probes, deps.redis_probes) == (1, 1)


async def test_waiters_share_the_probe_on_its_way() -> None:
    gate = asyncio.Event()
    probes = 0

    async def probe() -> bool:
        nonlocal probes
        probes += 1
        await gate.wait()
        return False

    check = DependencyCheck(probe, ttl_seconds=5.0, clock=_Clock())
    waiting = [asyncio.create_task(check.answers()) for _ in range(50)]
    await _until(lambda: probes == 1)
    assert not any(task.done() for task in waiting)
    gate.set()
    assert await asyncio.gather(*waiting) == [False] * 50
    assert probes == 1


async def test_an_outage_answer_is_kept_for_the_window_too(deps: _Deps) -> None:
    deps.redis_up = False
    async with _client() as client:
        assert (await client.get("/health/dependencies")).status_code == 503
        deps.redis_up = True
        assert (await client.get("/health/dependencies")).status_code == 503
        deps.clock.now += health.DEPENDENCY_CHECK_TTL_SECONDS
        assert (await client.get("/health/dependencies")).status_code == 200
    assert deps.redis_probes == 2


async def test_a_caller_that_hangs_up_leaves_the_probe_to_the_others() -> None:
    gate = asyncio.Event()
    probes = 0

    async def probe() -> bool:
        nonlocal probes
        probes += 1
        await gate.wait()
        return True

    check = DependencyCheck(probe, ttl_seconds=5.0, clock=_Clock())
    first = asyncio.create_task(check.answers())
    second = asyncio.create_task(check.answers())
    await asyncio.sleep(0)
    first.cancel()
    gate.set()
    assert await second is True
    assert await check.answers() is True
    assert probes == 1


@pytest.mark.parametrize("limiter", ["over the limit", "its Redis down"])
async def test_the_rest_rate_limit_never_answers_for_it(deps: _Deps, limiter: str) -> None:
    deps.redis_up = False
    # The limiter would answer any other path: 429 over the limit, 503 with its Redis down.
    allow = (
        AsyncMock(return_value=False)
        if limiter == "over the limit"
        else AsyncMock(side_effect=ConnectionError("redis down"))
    )
    with patch("app.core.rest_rate_limit.allow_request", allow):
        async with _client() as client:
            response = await client.get("/health/dependencies")
            limited = 429 if limiter == "over the limit" else 503
            assert (await client.get("/memories")).status_code == limited
    assert response.status_code == 503
    assert allow.await_count == 1  # /memories only
