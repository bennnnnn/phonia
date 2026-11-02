"""``POST /auth/refresh`` twice at once with one token: both answered, one session, no sign-out.

2026-11-02 (dev log): two refreshes reached a restarting API together, one answer was lost to
an app reload, and the app's next refresh 7 s later presented the token that answer had
rotated. The server took it for a stolen token, revoked every session of the account, and
the app signed itself out. Through the whole app here, as the phone sends them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.access_tokens import redis_str
from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_redis, get_settings_dep
from app.main import create_app
from app.modules.account import tokens
from app.tests.api_support import api_user

_SETTINGS = Settings(jwt_secret="test-secret-32-chars-long-enough!!")


@pytest.fixture
async def client(fake_redis) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _SETTINGS
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


async def test_two_refreshes_of_one_token_at_once_keep_one_session(client, fake_redis):
    user = api_user()
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, _SETTINGS)
    both_read = asyncio.Barrier(2)

    async def lookup(*_args):
        await both_read.wait()
        return user

    with patch("app.modules.account.tokens.users_repo.get_by_id", side_effect=lookup):
        first, second = await asyncio.wait_for(
            asyncio.gather(
                client.post("/auth/refresh", json={"refresh_token": refresh}),
                client.post("/auth/refresh", json={"refresh_token": refresh}),
            ),
            timeout=5,
        )
    assert (first.status_code, second.status_code) == (200, 200)
    successor = first.json()["refresh_token"]
    assert second.json()["refresh_token"] == successor
    live = {redis_str(t) for t in await fake_redis.smembers(f"refresh_user:{user.id}")}
    assert live == {successor}
    for answer in (first, second):
        access = answer.json()["access_token"]
        assert await tokens.verify_access_token(fake_redis, access, _SETTINGS) == user.id


async def test_a_retry_of_a_lost_answer_seconds_later_is_answered_again(client, fake_redis):
    user = api_user()
    _, refresh = await tokens.issue_token_pair(fake_redis, user.id, _SETTINGS)
    with patch("app.modules.account.tokens.users_repo.get_by_id", AsyncMock(return_value=user)):
        lost = await client.post("/auth/refresh", json={"refresh_token": refresh})
        retry = await client.post("/auth/refresh", json={"refresh_token": refresh})
        assert (lost.status_code, retry.status_code) == (200, 200)
        assert retry.json()["refresh_token"] == lost.json()["refresh_token"]
        # The account was not taken for stolen: no revocation cutoff, the session lives on.
        assert await fake_redis.get(f"revoked_since:{user.id}") is None
        onward = await client.post(
            "/auth/refresh", json={"refresh_token": retry.json()["refresh_token"]}
        )
    assert onward.status_code == 200
