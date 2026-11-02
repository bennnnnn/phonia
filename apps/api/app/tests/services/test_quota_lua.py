"""The token reservation's Lua script, run by a real Redis.

fakeredis here has no Lua (lupa is not installed), so every other quota test runs
the WATCH fallback. These run the script production's Redis runs, against the
Redis the suite runs beside (CI's ``redis:7`` service), and skip when none answers
at ``REDIS_URL``. Each test uses its own user id and deletes its key.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.services import quota as quota_service
from app.services.quota.counters import DAILY_TTL
from app.services.quota.tokens import _usage_key

_LIMIT = 100_000


@pytest.fixture
async def server() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await client.ping()
    except (RedisError, OSError) as exc:
        await client.aclose()
        pytest.skip(f"No Redis at REDIS_URL: {exc}")
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def user(server: Redis) -> AsyncIterator[str]:
    user_id = f"lua-test-{uuid4()}"
    yield user_id
    await server.delete(_usage_key(user_id, quota_service.utc_today()))


def _commands(redis: Redis) -> list[str]:
    sent: list[str] = []
    execute = redis.execute_command

    async def recording(*args: Any, **kwargs: Any) -> Any:
        sent.append(str(args[0]).upper())
        return await execute(*args, **kwargs)

    redis.execute_command = recording  # type: ignore[method-assign]
    return sent


@pytest.mark.parametrize(
    "used, wanted, granted",
    [
        (None, 1_000, 1_000),
        (99_000, 2_000, 1_000),  # what is left
        (_LIMIT, 1, 0),
        (_LIMIT + 500, 1_000, 0),  # over (the limit fell with a downgrade): nothing
    ],
)
async def test_the_script_checks_and_takes_in_one_round_trip(
    server: Redis, user: str, used: int | None, wanted: int, granted: int
) -> None:
    key = _usage_key(user, quota_service.utc_today())
    if used is not None:
        await server.set(key, used, ex=60)
    sent = _commands(server)

    got = await quota_service.reserve_usage_up_to(server, user, wanted, daily_limit=_LIMIT)

    assert got == granted
    assert sent == ["EVAL"]
    assert int(await server.get(key) or 0) == (used or 0) + granted
    ttl = await server.ttl(key)
    if used is None:
        assert DAILY_TTL - 5 < ttl <= DAILY_TTL  # a new counter gets the day's TTL
    else:
        assert ttl <= 60  # an existing one keeps its own


async def test_concurrent_turns_split_what_is_left(server: Redis, user: str) -> None:
    key = _usage_key(user, quota_service.utc_today())
    await server.set(key, _LIMIT - 1_000, ex=60)

    taken = await asyncio.gather(
        *(
            quota_service.reserve_usage_up_to(server, user, 70, daily_limit=_LIMIT)
            for _ in range(30)
        )
    )

    assert sum(taken) == 1_000
    assert int(await server.get(key) or 0) == _LIMIT


async def test_a_settle_racing_a_reserve_always_adds_up(server: Redis, user: str) -> None:
    """Turn A held 20k of a full day and used 15k; turn B asks for 10k at the same time.

    Whichever runs first, the day ends at 95k plus what B was given. Taking first and
    giving the excess back let A's clip at the limit land in between: 90k, 5k free.
    """
    key = _usage_key(user, quota_service.utc_today())
    for _ in range(50):
        await server.set(key, _LIMIT, ex=60)

        granted, _ = await asyncio.gather(
            quota_service.reserve_usage_up_to(server, user, 10_000, daily_limit=_LIMIT),
            quota_service.adjust_usage(server, user, 20_000, 15_000, daily_limit=_LIMIT),
        )

        assert granted in (0, 5_000)
        assert int(await server.get(key) or 0) == 95_000 + granted
