"""A per-user cap on requests open at once, shared by every machine through Redis."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest

from app.core.in_flight import InFlightBusyError, in_flight_slot
from app.exceptions import RedisUnavailableError


@pytest.mark.asyncio
async def test_slots_are_held_for_the_block_and_given_back() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with in_flight_slot(redis, "k", limit=2, ttl_seconds=30):
        async with in_flight_slot(redis, "k", limit=2, ttl_seconds=30):
            with pytest.raises(InFlightBusyError):
                async with in_flight_slot(redis, "k", limit=2, ttl_seconds=30):
                    pass
            assert await redis.zcard("k") == 2
    assert await redis.zcard("k") == 0


@pytest.mark.asyncio
async def test_a_slot_older_than_its_ttl_ages_out() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.zadd("k", {"crashed": time.time() - 120})
    async with in_flight_slot(redis, "k", limit=1, ttl_seconds=30):
        assert await redis.zcard("k") == 1


@pytest.mark.asyncio
async def test_a_limit_of_zero_disables_the_cap() -> None:
    redis = MagicMock()
    async with in_flight_slot(redis, "k", limit=0, ttl_seconds=30):
        pass
    redis.pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_a_redis_outage_fails_closed() -> None:
    redis = MagicMock()
    redis.pipeline.side_effect = ConnectionError("down")
    with pytest.raises(RedisUnavailableError):
        async with in_flight_slot(redis, "k", limit=2, ttl_seconds=30):
            pass
