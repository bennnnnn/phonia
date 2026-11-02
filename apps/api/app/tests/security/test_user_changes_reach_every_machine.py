"""A change to a user row reaches every machine's cached copy, or the request says it did not.

Each machine keeps the user rows it read and checks them against the user's
generation in Redis on every request (``core/user_cache``). Here the world's one
fake Redis is shared by the app and the user cache, so the publish, the token
check's read and the cached copy are the real path. "Another machine" is a write
straight to the row plus what that machine's publish would leave in Redis.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, update

from app.core import user_cache
from app.core.cache_generation import bump_generation
from app.core.db import SessionLocal
from app.models.orm import User

from .conftest import World


async def _set_plan_elsewhere(user_id: UUID, plan: str) -> None:
    """Another machine (or a hand-run SQL edit) changes the row; this process is not told."""
    async with SessionLocal() as session:
        await session.execute(update(User).where(User.id == user_id).values(plan=plan))
        await session.commit()


async def _plan_served(world: World) -> str:
    response = await world.client.get("/auth/me", headers=world.a.headers)
    assert response.status_code == 200, response.text
    return str(response.json()["plan"])


async def test_another_machines_change_applies_to_this_machines_next_request(
    world: World,
) -> None:
    assert await _plan_served(world) == "free"  # now cached here
    await _set_plan_elsewhere(world.a.id, "pro")
    assert await _plan_served(world) == "free"  # the copy, until a generation says otherwise

    await bump_generation(world.redis, user_cache.generation_key(world.a.id))

    assert await _plan_served(world) == "pro"


async def test_a_hand_edit_reaches_every_machine_after_del_of_the_generation(
    world: World,
) -> None:
    """The runbook for a SQL edit to ``users`` (docs/PRODUCTION.md): DEL usergen:<id>."""
    assert await _plan_served(world) == "free"
    await _set_plan_elsewhere(world.a.id, "pro")

    await world.redis.delete(user_cache.generation_key(world.a.id))

    assert await _plan_served(world) == "pro"


async def test_a_change_redis_cannot_publish_answers_503_and_its_retry_publishes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(user_cache, "_PUBLISH_PAUSE_SECONDS", 0)
    assert await _plan_served(world) == "free"
    before = await world.redis.get(user_cache.generation_key(world.a.id))
    real_bump = bump_generation

    async def redis_down(*_args: object, **_kwargs: object) -> str:
        raise RedisConnectionError("down")

    monkeypatch.setattr(user_cache, "bump_generation", redis_down)
    refused = await world.client.patch(
        "/auth/me", json={"memory_enabled": False}, headers=world.a.headers
    )

    assert refused.status_code == 503
    assert refused.headers.get("Retry-After") == "5"
    async with SessionLocal() as session:
        saved = await session.execute(select(User.memory_enabled).where(User.id == world.a.id))
        assert saved.scalar_one() is False  # saved, though not yet published

    monkeypatch.setattr(user_cache, "bump_generation", real_bump)
    retried = await world.client.patch(
        "/auth/me", json={"memory_enabled": False}, headers=world.a.headers
    )

    assert retried.status_code == 200
    assert await world.redis.get(user_cache.generation_key(world.a.id)) != before
