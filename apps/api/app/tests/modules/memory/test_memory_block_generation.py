"""The question-free memory blocks are tied to the generation read before their facts.

``memblock:{user}`` used to be a plain key: a memory write that committed after a
turn read its facts, but before the turn stored the block, invalidated first and
was then overwritten by the stale block, served for ``memory_cache_ttl`` (300 s).
A "forget X" could still be injected for five minutes.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory import cache, get_memory_block, invalidate_memory_block
from app.tests.fakes import fake_session, make_user


def _memory(text: str) -> MagicMock:
    m = MagicMock()
    m.type = "fact"
    m.text = text
    m.confidence = 0.9
    m.status = "active"
    m.sensitivity = "normal"
    m.importance = 0.5
    m.updated_at = 0
    m.last_confirmed_at = None
    return m


def _user() -> MagicMock:
    return make_user(name=None)


async def test_memory_block_write_racing_a_memory_write_is_never_served(fake_redis):
    user = _user()
    session = fake_session()
    settings = Settings(memory_cache_ttl=300)
    loads = 0

    async def load(*_args, **_kwargs):
        nonlocal loads
        loads += 1
        if loads == 1:
            # A memory job commits "forget hiking" while this turn holds the old rows.
            await invalidate_memory_block(user.id)
            return [_memory("Likes hiking")]
        return [_memory("Likes chess")]

    with patch("app.modules.memory.retrieval.load_relevant_memories", side_effect=load):
        first = await get_memory_block(session, user, settings)
        second = await get_memory_block(session, user, settings)

    assert "Likes hiking" in first
    assert "Likes hiking" not in second
    assert "Likes chess" in second


async def test_memory_block_cache_hit_under_the_same_generation(fake_redis):
    user = _user()
    load = AsyncMock(return_value=[_memory("Likes hiking")])
    with patch("app.modules.memory.retrieval.load_relevant_memories", load):
        first = await get_memory_block(fake_session(), user, Settings())
        second = await get_memory_block(fake_session(), user, Settings())

    assert second == first
    load.assert_awaited_once()


@pytest.mark.parametrize(
    "stored",
    [
        "Likes hiking",  # written before blocks carried their generation
        "stale-generation\nLikes hiking",
    ],
)
async def test_read_block_cache_misses_without_the_current_generation(fake_redis, stored):
    user_id = uuid4()
    key = cache.memory_block_key(user_id)
    await fake_redis.set(cache.memory_generation_key(user_id), "current")
    await fake_redis.set(key, stored)

    block, tag = await cache.read_block_cache(fake_redis, user_id, key)

    assert block is None
    assert tag == "current"


async def test_read_block_cache_without_a_generation_key_uses_zero(fake_redis):
    user_id = uuid4()
    key = cache.memory_block_key(user_id)
    await cache.write_block_cache(fake_redis, key, "0", "Line one\nLine two", 60)

    block, tag = await cache.read_block_cache(fake_redis, user_id, key)

    assert (block, tag) == ("Line one\nLine two", "0")


async def test_invalidate_memory_block_retries_once(fake_redis):
    user_id = uuid4()
    key = cache.memory_block_key(user_id)
    await fake_redis.set(key, "0\nold")
    calls = 0

    def flaky_client():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("blip")
        return fake_redis

    with patch("app.modules.memory.cache.get_redis_client", side_effect=flaky_client):
        await invalidate_memory_block(user_id)

    assert calls == 2
    assert await fake_redis.exists(key) == 0
    assert await fake_redis.get(cache.memory_generation_key(user_id)) is not None


async def test_invalidate_memory_block_failure_logs_a_warning(caplog):
    user_id = uuid4()
    with (
        patch(
            "app.modules.memory.cache.get_redis_client",
            side_effect=ConnectionError("redis down"),
        ),
        caplog.at_level(logging.WARNING, logger="app.modules.memory.cache"),
    ):
        await invalidate_memory_block(user_id)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert str(user_id) in warnings[0].getMessage()


async def test_tagged_blocks_never_land_where_the_previous_release_reads(fake_redis):
    """During a rolling deploy the previous release reads ``memblock:{user}`` raw: a
    tagged entry there would put its generation line into that release's prompt."""
    user_id = uuid4()
    key = cache.memory_block_key(user_id)
    await cache.write_block_cache(fake_redis, key, "7", "Likes hiking", 60)

    assert not key.startswith(f"memblock:{user_id}")
    assert await fake_redis.get(f"memblock:{user_id}") is None


async def test_invalidation_drops_the_previous_releases_blocks_too(fake_redis):
    user_id = uuid4()
    legacy = f"memblock:{user_id}"
    for suffix in ("", ":x"):
        await fake_redis.set(f"{legacy}{suffix}", "Likes hiking")
        await fake_redis.set(f"{cache.memory_block_key(user_id)}{suffix}", "0\nLikes hiking")

    with patch("app.modules.memory.cache.get_redis_client", return_value=fake_redis):
        await invalidate_memory_block(user_id)

    assert await fake_redis.keys(f"memblock*{user_id}*") == []
