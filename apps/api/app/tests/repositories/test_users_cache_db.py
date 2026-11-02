"""A user change reaches the user caches only once it commits, and then on every machine.

``users.update(commit=False)`` used to cache the new values at flush. When the
caller's commit then failed and rolled back, this process served the unsaved
profile to every request for up to the cache TTL. A committed change now
publishes a new generation (core/user_cache), so every machine drops its copy;
a publish Redis refuses fails the request, so the change is never silently lost.
"""

from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from app.core import user_cache
from app.exceptions import RedisUnavailableError
from app.models.orm import User
from app.repositories import users


async def _user(session) -> User:
    return await users.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Before",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def _generation(redis, user_id) -> str | None:
    return await redis.get(user_cache.generation_key(user_id))


@pytest.fixture(autouse=True)
def _empty_cache():
    user_cache.clear()
    yield
    user_cache.clear()


async def test_an_uncommitted_change_publishes_nothing(db_session, user_generation_redis):
    user = await _user(db_session)
    user_cache.remember_user(user, "g0")

    await users.update(db_session, user, commit=False, name="After")

    # Dropped here, published by the caller only after its own commit.
    assert user_cache.cached_user(user.id, "g0") is None
    assert await _generation(user_generation_redis, user.id) is None


async def test_a_rolled_back_change_is_never_served_from_the_cache(
    db_session, user_generation_redis
):
    user = await _user(db_session)
    user_id = user.id  # the rollback expires the row; reading it again would load it
    user_cache.remember_user(user, "g0")

    await users.update(db_session, user, commit=False, name="Unsaved")
    await db_session.rollback()

    assert user_cache.cached_user(user_id, "g0") is None
    assert await _generation(user_generation_redis, user_id) is None


async def test_a_committed_update_is_kept_under_its_new_generation(
    db_session, user_generation_redis
):
    user = await _user(db_session)
    user_cache.remember_user(user, "g0")

    await users.update(db_session, user, name="Saved")

    generation = await _generation(user_generation_redis, user.id)
    assert generation is not None
    # Another machine (or this one) holding the old generation reads the row again.
    assert user_cache.cached_user(user.id, "g0") is None
    cached = user_cache.cached_user(user.id, generation)
    assert cached is not None
    assert cached.name == "Saved"


async def test_a_committed_update_redis_cannot_publish_is_saved_and_fails_the_request(
    db_session, user_generation_redis, monkeypatch
):
    """A consent withdrawal during a Redis outage: 503, and the change is in the row."""
    monkeypatch.setattr(user_cache, "_PUBLISH_PAUSE_SECONDS", 0)
    user = await _user(db_session)

    async def down(*_args, **_kwargs):
        raise RedisConnectionError("down")

    user_generation_redis.set = down

    with pytest.raises(RedisUnavailableError):
        await users.update(db_session, user, name="Saved anyway")

    saved = (await db_session.execute(select(User.name).where(User.id == user.id))).scalar_one()
    assert saved == "Saved anyway"
