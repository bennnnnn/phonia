from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.core.deps import get_redis, get_settings_dep
from app.tests.fakes import fake_session


@pytest.mark.asyncio
async def test_get_settings_dep_returns_settings():
    settings = Settings(jwt_secret="super-secret-key-that-is-at-least-32-chars!!")
    with patch("app.core.deps.get_settings", return_value=settings):
        assert await get_settings_dep() is settings


@pytest.mark.asyncio
async def test_get_redis_returns_client():
    client = AsyncMock()
    with patch("app.core.deps.get_redis_client", return_value=client):
        assert await get_redis() is client


async def _current_user(fake_redis, token: str, settings: Settings, load: AsyncMock):
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.deps import get_current_user

    session = fake_session()
    session.merge = AsyncMock(side_effect=lambda row, load=False: row)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with patch("app.core.deps.users_repo.get_by_id", load):
        return await get_current_user(credentials, settings, fake_redis, session)


@pytest.mark.asyncio
async def test_get_current_user_rereads_a_row_another_machine_changed(fake_redis):
    """The copy kept here is used until a write anywhere publishes a new generation."""
    from uuid import uuid4

    from app.core import user_cache
    from app.core.access_tokens import create_access_token
    from app.core.cache_generation import bump_generation
    from app.models.orm import User

    settings = Settings(jwt_secret="x" * 32)
    user_id = uuid4()
    token = create_access_token(user_id, settings)
    before = User(id=user_id, email="a@example.com", plan="free")
    after = User(id=user_id, email="a@example.com", plan="pro")
    user_cache.forget_user(user_id)
    try:
        load = AsyncMock(return_value=before)
        assert (await _current_user(fake_redis, token, settings, load)).plan == "free"
        assert (await _current_user(fake_redis, token, settings, load)).plan == "free"
        assert load.await_count == 1

        # The RevenueCat webhook upgraded the user on another machine.
        await bump_generation(fake_redis, user_cache.generation_key(user_id))
        load = AsyncMock(return_value=after)

        assert (await _current_user(fake_redis, token, settings, load)).plan == "pro"
        assert load.await_count == 1
    finally:
        user_cache.forget_user(user_id)
