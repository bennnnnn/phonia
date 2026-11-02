"""The per-process user cache that authenticated requests read (core/user_cache.py).

A copy is served only under the generation it was loaded at; a committed write
publishes a new generation in Redis, so every machine drops its copy at once.
"""

import time
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import make_transient_to_detached

from app.core import access_tokens, user_cache
from app.core.cache_generation import bump_generation
from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.models.orm import User


def _user(name: str = "Someone") -> User:
    row = User(id=uuid4(), email="someone@example.com", name=name)
    make_transient_to_detached(row)
    return row


@pytest.fixture(autouse=True)
def _empty_cache():
    user_cache.clear()
    yield
    user_cache.clear()


def test_user_cache_forgets_users_nobody_reads_again(monkeypatch):
    """Every user who ever signed in used to stay cached for the life of the
    process: an entry left only when that user was read again after the TTL."""
    now = [time.monotonic()]
    monkeypatch.setattr(user_cache._user_cache, "clock", lambda: now[0])
    for _ in range(50):
        user_cache.remember_user(_user(), "g0")
    now[0] += user_cache.USER_CACHE_TTL_SECONDS + 1
    latest = _user()
    user_cache.remember_user(latest, "g0")

    assert user_cache.size() == 1
    cached = user_cache.cached_user(latest.id, "g0")
    assert cached is not None
    assert cached.id == latest.id
    user_cache.forget_user(latest.id)
    assert user_cache.cached_user(latest.id, "g0") is None


def test_a_copy_is_served_only_under_the_generation_it_was_loaded_at():
    user = _user()
    user_cache.remember_user(user, "a1")

    assert user_cache.cached_user(user.id, "a1") is not None
    # Another machine saved a change: the generation every request reads moved on.
    assert user_cache.cached_user(user.id, "b2") is None


def test_each_caller_gets_its_own_copy():
    user = _user()
    user_cache.remember_user(user, "a1")

    first = user_cache.cached_user(user.id, "a1")
    second = user_cache.cached_user(user.id, "a1")

    assert first is not None and second is not None
    assert first is not second
    first.name = "Changed by one request"
    assert second.name == "Someone"


async def test_publish_change_drops_the_copy_and_moves_the_generation(user_generation_redis):
    user = _user()
    user_cache.remember_user(user, "g0")

    generation = await user_cache.publish_change(user.id)

    stored = await user_generation_redis.get(user_cache.generation_key(user.id))
    assert generation is not None
    assert stored == generation != "g0"
    assert user_cache.cached_user(user.id, "g0") is None


def _failing_sets(redis, failures: int) -> list[int]:
    """Make ``redis``'s next ``failures`` SETs fail as a Redis outage would; count attempts."""
    attempts: list[int] = []
    set_value = redis.set

    async def flaky(*args, **kwargs):
        attempts.append(1)
        if len(attempts) <= failures:
            raise RedisConnectionError("down")
        return await set_value(*args, **kwargs)

    redis.set = flaky
    return attempts


async def test_publish_change_rides_out_a_redis_blip(user_generation_redis, monkeypatch):
    monkeypatch.setattr(user_cache, "_PUBLISH_PAUSE_SECONDS", 0)
    user = _user()
    attempts = _failing_sets(user_generation_redis, failures=2)

    generation = await user_cache.publish_change(user.id)

    assert len(attempts) == 3
    assert await user_generation_redis.get(user_cache.generation_key(user.id)) == generation


async def test_a_publish_redis_never_takes_fails_the_request(user_generation_redis, monkeypatch):
    """The write is already saved: a 503 makes its retry publish, instead of every other
    machine serving the old row (consent, plan, memory off) for the cache TTL."""
    monkeypatch.setattr(user_cache, "_PUBLISH_PAUSE_SECONDS", 0)
    user = _user()
    user_cache.remember_user(user, "g0")
    attempts = _failing_sets(user_generation_redis, failures=10)

    with pytest.raises(RedisUnavailableError):
        await user_cache.publish_change(user.id)

    assert len(attempts) == 3
    assert user_cache.cached_user(user.id, "g0") is None


async def test_a_lost_generation_key_never_brings_an_old_copy_back(fake_redis) -> None:
    """The key can vanish early (eviction, a flush, a failover, a DEL by hand).

    A reader that finds it missing used to take generation "0", the one a copy
    loaded before the key ever existed was stored under: that copy came back.
    """
    settings = Settings(jwt_secret="x" * 32)
    user = _user(name="On the pro plan")
    token = access_tokens.create_access_token(user.id, settings)
    key = user_cache.generation_key(user.id)

    loaded_under = (await access_tokens.check_access(fake_redis, token, settings)).user_generation
    user_cache.remember_user(user, loaded_under)
    await bump_generation(fake_redis, key)  # a change saved on another machine
    await fake_redis.delete(key)  # then the key is lost

    now = (await access_tokens.check_access(fake_redis, token, settings)).user_generation

    assert now not in (loaded_under, "0")
    assert user_cache.cached_user(user.id, now) is None
