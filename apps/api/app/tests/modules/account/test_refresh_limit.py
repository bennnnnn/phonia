"""``POST /auth/refresh`` is limited per account, with a looser per-IP backstop.

It was 60 a minute per IP, and the global REST limit (240 a minute per unsigned IP) came
first: behind one carrier NAT address the 61st phone to refresh in a minute was refused.
Every request here comes from the one address TestClient gives, through the whole app.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.core.deps import get_redis, get_settings_dep
from app.main import create_app
from app.models.schemas import UserOut
from app.modules.account import refresh_limit
from app.modules.account import tokens as tokens_service
from app.tests.fakes import redis_mock

_SETTINGS = Settings(jwt_secret="test-secret-32-chars-long-enough!!")


def _user_out(user_id: UUID) -> UserOut:
    return UserOut(
        id=user_id,
        email="phone@recall.local",
        name="Phone",
        avatar_url=None,
        plan="free",
        enabled_models=None,
        memory_enabled=True,
        created_at=datetime(2024, 1, 1),
    )


@pytest.fixture
def client(fake_redis) -> Iterator[TestClient]:
    """The app, with each refresh answered without rotating the token (the limit is the subject)."""

    async def answer(_redis, token, _session, _settings, **_kw):
        user_id = await tokens_service.refresh_token_user(fake_redis, token)
        return "access", "refresh", _user_out(user_id or uuid4())

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _SETTINGS
    app.dependency_overrides[get_redis] = lambda: fake_redis
    with patch.object(tokens_service, "refresh_token_pair", AsyncMock(side_effect=answer)):
        yield TestClient(app)


async def _signed_in(fake_redis, users: int) -> list[str]:
    """One live refresh token for each of ``users`` accounts."""
    return [
        (await tokens_service.issue_token_pair(fake_redis, uuid4(), _SETTINGS))[1]
        for _ in range(users)
    ]


def _refresh(client: TestClient, token: str) -> int:
    response = client.post("/auth/refresh", json={"refresh_token": token})
    if response.status_code == 429:
        assert response.headers["retry-after"] == str(refresh_limit.WINDOW_SECONDS)
        # Coded: the phone fails each request that needs a refresh with it until the wait ends.
        assert response.json()["detail"]["code"] == "rate_limited"
    return response.status_code


async def test_one_accounts_burst_is_limited_and_another_account_is_not(client, fake_redis):
    burst, other = await _signed_in(fake_redis, 2)
    codes = [_refresh(client, burst) for _ in range(refresh_limit.PER_ACCOUNT_LIMIT + 2)]
    assert codes == [200] * refresh_limit.PER_ACCOUNT_LIMIT + [429, 429]
    # The same address, another account: its own budget.
    assert _refresh(client, other) == 200


async def test_a_second_device_shares_its_accounts_budget(client, fake_redis):
    user_id = uuid4()
    phone = (await tokens_service.issue_token_pair(fake_redis, user_id, _SETTINGS))[1]
    tablet = (await tokens_service.issue_token_pair(fake_redis, user_id, _SETTINGS))[1]
    for _ in range(refresh_limit.PER_ACCOUNT_LIMIT):
        assert _refresh(client, phone) == 200
    assert _refresh(client, tablet) == 429


async def test_an_unknown_token_is_limited_under_its_hash(client, fake_redis):
    codes = [_refresh(client, "not-a-session") for _ in range(refresh_limit.PER_ACCOUNT_LIMIT + 1)]
    assert codes == [200] * refresh_limit.PER_ACCOUNT_LIMIT + [429]
    keys = [key async for key in fake_redis.scan_iter("rate:auth:refresh:*")]
    assert "not-a-session" not in "".join(keys)


async def test_many_accounts_behind_one_address_refresh_until_the_backstop(client, fake_redis):
    """Old limit: the 61st phone behind one NAT address was refused (and the 241st by the
    global REST limit). Now every account refreshes until the address's backstop."""
    tokens = await _signed_in(fake_redis, refresh_limit.PER_IP_LIMIT + 1)
    codes = [_refresh(client, token) for token in tokens]
    assert codes == [200] * refresh_limit.PER_IP_LIMIT + [429]


@pytest.mark.parametrize("down", ["backstop", "account"])
def test_a_redis_outage_answers_503_not_a_limit(client, down):
    """It answered 429 + Retry-After 60, read on the phone as a limit: live talk said the
    month's minutes were used up, and requests that needed a refresh failed for up to a
    minute after Redis was back. Still closed: no refresh goes through."""
    broken = redis_mock()
    broken.pipeline.side_effect = RedisConnectionError("down")
    client.app.dependency_overrides[get_redis] = lambda: broken
    with (
        patch.object(refresh_limit, "address_allowed", AsyncMock(return_value=True))
        if down == "account"
        else nullcontext(),
        patch.object(tokens_service, "refresh_token_user", AsyncMock(return_value=None)),
    ):
        response = client.post("/auth/refresh", json={"refresh_token": "a-session"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    tokens_service.refresh_token_pair.assert_not_awaited()


def test_the_backstop_is_looser_than_the_old_per_ip_limit_and_the_global_one() -> None:
    assert refresh_limit.PER_IP_LIMIT > 240 > 60
    assert refresh_limit.PER_ACCOUNT_LIMIT < refresh_limit.PER_IP_LIMIT
