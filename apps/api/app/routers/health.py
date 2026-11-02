import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.aio import gather_or_cancel
from app.core.db import SessionLocal
from app.core.redis import get_redis_client
from app.core.unavailable import unavailable_response

router = APIRouter()

# Fly's check timeout is 5s (fly.toml). Each probe answers well inside it, so a
# stalled dependency reports as down or degraded instead of timing the whole
# check out. A stalled Redis used to hold this endpoint for the 5s Redis socket
# timeout, failing readiness on every machine at once.
READY_DB_TIMEOUT_SECONDS = 3.0
READY_REDIS_TIMEOUT_SECONDS = 1.0
# How long one process keeps the answer of /health/dependencies, which every phone asks.
DEPENDENCY_CHECK_TTL_SECONDS = 5.0


async def database_answers() -> bool:
    """Postgres answers ``SELECT 1`` within its limit. The error is never shown."""
    try:
        async with asyncio.timeout(READY_DB_TIMEOUT_SECONDS):
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def redis_answers() -> bool:
    """Redis answers PING within its limit. The error is never shown."""
    try:
        async with asyncio.timeout(READY_REDIS_TIMEOUT_SECONDS):
            await get_redis_client().ping()
    except Exception:
        return False
    return True


async def both_answer() -> bool:
    database, redis = await gather_or_cancel(database_answers(), redis_answers())
    return database and redis


class DependencyCheck:
    """Whether the API's dependencies answer, probed at most once per ``ttl_seconds``.

    Each phone asks on launch, on each return and while its banner shows: a probe per
    request would take a pooled database connection per phone, most of all while the
    database struggles. A caller inside the window gets the last answer, and callers
    while a probe is out wait for that one. The answer is this process's alone.
    """

    def __init__(
        self,
        probe: Callable[[], Awaitable[bool]],
        *,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._ttl = ttl_seconds
        # A test sets its own clock here, never ``time.monotonic`` for the whole process.
        self._clock = clock
        self._answer: tuple[float, bool] | None = None
        self._running: asyncio.Task[bool] | None = None

    async def answers(self) -> bool:
        if self._answer is not None and self._clock() - self._answer[0] < self._ttl:
            return self._answer[1]
        if self._running is None:
            self._running = asyncio.create_task(self._run())
        # A caller that hangs up does not cancel the probe the others wait for.
        return await asyncio.shield(self._running)

    async def _run(self) -> bool:
        try:
            answer = await self._probe()
            self._answer = (self._clock(), answer)
            return answer
        finally:
            self._running = None


DEPENDENCY_CHECK = DependencyCheck(both_answer, ttl_seconds=DEPENDENCY_CHECK_TTL_SECONDS)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness — process is up. Do not couple this to Redis or Postgres."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict[str, str]:
    """Readiness — Postgres can take traffic.

    Redis is reported but not required. A Redis blip must not drain the Fly
    fleet; chat/quota already fail closed per request.
    """
    if not await database_answers():
        # Don't leak the underlying exception text (it may include connection
        # strings or internal details) — just signal not ready.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency check failed",
        )
    return {"status": "ok", "redis": "ok" if await redis_answers() else "degraded"}


@router.get("/health/dependencies")
async def dependencies() -> JSONResponse:
    """Postgres and Redis both answer: what the phone's connection check reads.

    /health answers 200 while either is down and every read fails, so the phone found the
    API "online" through an outage. Fly's checks read /health and /health/ready, not this:
    a Redis blip still drains no Machine. Down, it answers as every outage does (the code
    ``unavailable``, core/unavailable.py).
    """
    headers = {"Cache-Control": "no-store"}
    if await DEPENDENCY_CHECK.answers():
        return JSONResponse({"status": "ok"}, headers=headers)
    response = unavailable_response()
    response.headers.update(headers)
    return response
