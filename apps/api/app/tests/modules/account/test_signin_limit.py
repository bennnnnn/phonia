"""Google and Apple sign-in are limited per identity, with a looser per-IP backstop.

It was 30 a minute per IP for each provider, and the global REST limit (240 a minute per
unsigned IP) came first: behind one carrier NAT address the 31st person to sign in with
Google in a minute was refused. Every request goes through the whole app; each token
names its own identity, and what sign-in does after the limit (the account, the
session) is faked so the limit is the subject.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import get_redis, get_settings_dep
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.main import create_app
from app.models.schemas import AuthResponse, UserOut
from app.modules.account import quota_carryover, refresh_limit, signin_limit
from app.modules.account import service as auth_service
from app.tests.fakes import fake_session, make_user, redis_mock

_SETTINGS = Settings(jwt_secret="test-secret-32-chars-long-enough!!", dev_auth_enabled=True)
_ADDRESS = "203.0.113.7"
_OTHER_ADDRESS = "198.51.100.9"
_GLOBAL_LIMIT = _SETTINGS.rest_rate_limit_per_minute


def _user_out() -> UserOut:
    return UserOut(
        id=uuid4(),
        email="person@gmail.com",
        name="Person",
        avatar_url=None,
        memory_enabled=True,
        created_at=datetime(2024, 1, 1),
    )


@dataclass
class SignIn:
    """The app, and the calls sign-in made after its limits."""

    app: Any
    verified: list[str]
    accounts_read: AsyncMock
    sessions: AsyncMock

    def client(self, address: str = _ADDRESS) -> TestClient:
        return TestClient(self.app, client=(address, 50000))


@pytest.fixture
def sign_in(fake_redis) -> Iterator[SignIn]:
    """A token ``bad-…`` fails verification; any other is a verified identity of that name."""
    verified: list[str] = []

    async def google(token: str, _settings: Settings) -> dict[str, Any]:
        verified.append(token)
        if token.startswith("bad-"):
            raise AuthenticationError("Invalid Google ID token")
        return {"sub": token, "email": f"{token}@gmail.com", "email_verified": True}

    async def apple(token: str, _settings: Settings, *, nonce: str | None) -> dict[str, Any]:
        verified.append(token)
        return {"sub": token, "email": f"{token}@icloud.com", "email_verified": "true"}

    async def account(_session: Any, sub: str) -> Any:
        return make_user(google_sub=sub, apple_sub=sub, avatar_url=None)

    async def db() -> Any:
        yield fake_session()

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _SETTINGS
    app.dependency_overrides[get_redis] = lambda: fake_redis
    app.dependency_overrides[get_db] = db
    accounts_read = AsyncMock(side_effect=account)
    sessions = AsyncMock(return_value=("access", "refresh"))
    repo = auth_service.users_repo
    with (
        patch.object(auth_service, "verify_google_id_token", AsyncMock(side_effect=google)),
        patch.object(auth_service, "verify_apple_id_token", AsyncMock(side_effect=apple)),
        patch.object(repo, "get_by_google_sub", accounts_read),
        patch.object(repo, "get_by_apple_sub", accounts_read),
        patch.object(repo, "refresh_for_update", AsyncMock()),
        patch.object(repo, "update", AsyncMock(side_effect=lambda _s, user, **_kw: user)),
        patch.object(auth_service.tokens_service, "issue_token_pair", sessions),
        patch.object(auth_service.UserOut, "model_validate", return_value=_user_out()),
        # The global REST limit counts where the test can read it.
        patch("app.core.rest_rate_limit.get_redis_client", return_value=fake_redis),
    ):
        yield SignIn(app, verified, accounts_read, sessions)


def _post(client: TestClient, provider: str, token: str) -> int:
    body = {"id_token": token} if provider == "google" else {"id_token": token, "nonce": "n"}
    response = client.post(f"/auth/{provider}", json=body)
    if response.status_code == 429:
        assert response.headers["retry-after"] == str(signin_limit.WINDOW_SECONDS)
    return response.status_code


def test_many_people_behind_one_address_sign_in_until_the_backstop(sign_in):
    """Old limit: the 31st Google sign-in from one address was refused (the 61st with Apple
    mixed in, and the 241st with only the route fixed: the global REST limit)."""
    client = sign_in.client()
    people = signin_limit.PER_IP_LIMIT + 1
    codes = [_post(client, ("google", "apple")[i % 2], f"person-{i}") for i in range(people)]
    assert codes == [200] * signin_limit.PER_IP_LIMIT + [429]


def test_one_identitys_burst_is_limited_and_another_identity_is_not(sign_in):
    client = sign_in.client()
    burst = [_post(client, "google", "burst") for _ in range(signin_limit.PER_IDENTITY_LIMIT + 2)]
    assert burst == [200] * signin_limit.PER_IDENTITY_LIMIT + [429, 429]
    # The same address, another person; and the same subject at the other provider.
    assert _post(client, "google", "someone-else") == 200
    assert _post(client, "apple", "burst") == 200


def test_one_identity_shares_its_budget_across_addresses(sign_in):
    """Old limit: per address only, so each new address gave the same identity 30 more."""
    home, office = sign_in.client(), sign_in.client(_OTHER_ADDRESS)
    for _ in range(signin_limit.PER_IDENTITY_LIMIT):
        assert _post(home, "google", "traveller") == 200
    assert _post(office, "google", "traveller") == 429
    assert _post(office, "google", "colleague") == 200


def test_a_refused_identity_is_verified_but_reaches_no_account_or_session(sign_in):
    client = sign_in.client()
    for _ in range(signin_limit.PER_IDENTITY_LIMIT + 1):
        _post(client, "apple", "looping-client")
    assert len(sign_in.verified) == signin_limit.PER_IDENTITY_LIMIT + 1
    assert sign_in.accounts_read.await_count == signin_limit.PER_IDENTITY_LIMIT
    assert sign_in.sessions.await_count == signin_limit.PER_IDENTITY_LIMIT


def test_an_address_past_its_backstop_verifies_no_more_tokens(sign_in):
    client = sign_in.client()
    codes = [_post(client, "google", f"bad-{i}") for i in range(signin_limit.PER_IP_LIMIT + 1)]
    assert codes == [401] * signin_limit.PER_IP_LIMIT + [429]
    assert len(sign_in.verified) == signin_limit.PER_IP_LIMIT
    # A valid token from that address waits too; another address does not.
    assert _post(client, "apple", "person") == 429
    assert _post(sign_in.client(_OTHER_ADDRESS), "apple", "person") == 200


async def test_the_global_rest_limit_skips_google_and_apple_but_not_dev_login(sign_in, fake_redis):
    client = sign_in.client()
    _post(client, "google", "person-1")
    _post(client, "apple", "person-2")
    assert await fake_redis.get(f"rest_rl:ip:{_ADDRESS}") is None
    loopback = sign_in.client("127.0.0.1")
    fake = AuthResponse(access_token="a", refresh_token="r", user=_user_out())
    with patch.object(auth_service, "login_dev", AsyncMock(return_value=fake)):
        assert loopback.post("/auth/dev", json={"email": "dev@recall.local"}).status_code == 200
    assert await fake_redis.get("rest_rl:ip:127.0.0.1") == "1"


def test_dev_login_keeps_its_per_address_limit(sign_in):
    """It verifies no token, so it has no identity to key on: a new email is no new budget."""
    client = sign_in.client("127.0.0.1")
    fake = AuthResponse(access_token="a", refresh_token="r", user=_user_out())
    with patch.object(auth_service, "login_dev", AsyncMock(return_value=fake)):
        codes = [
            client.post("/auth/dev", json={"email": f"dev-{i}@recall.local"}).status_code
            for i in range(signin_limit.DEV_PER_IP_LIMIT + 1)
        ]
    assert codes == [200] * signin_limit.DEV_PER_IP_LIMIT + [429]


async def test_no_subject_or_token_reaches_a_redis_key(sign_in, fake_redis):
    _post(sign_in.client(), "google", "subject-1234567890")
    keys = "".join([key async for key in fake_redis.scan_iter("rate:auth:*")])
    assert "rate:auth:signin:google:" in keys
    assert "subject-1234567890" not in keys


async def test_a_redis_outage_refuses_sign_in_and_logs_no_subject(caplog):
    broken = redis_mock()
    broken.pipeline.side_effect = RedisConnectionError("down")
    with caplog.at_level(logging.WARNING), pytest.raises(RedisUnavailableError):
        await signin_limit.require_identity(broken, _SETTINGS, "google", "subject-1234567890")
    assert "failing closed" in caplog.text
    assert "subject-1234567890" not in caplog.text


def _unavailable(response: Any) -> None:
    """Sign-in is down, not limited: retry in a moment."""
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["detail"]["code"] == "sign_in_unavailable"


def _body(provider: str) -> dict[str, str]:
    return {"id_token": "person"} if provider == "google" else {"id_token": "person", "nonce": "n"}


@pytest.mark.parametrize("provider", ["google", "apple"])
@pytest.mark.parametrize("down", ["backstop", "identity"])
def test_a_redis_outage_answers_503_not_too_many_attempts(sign_in, provider, down):
    """It answered 429 "Too many login attempts" + Retry-After 60: the phone told someone
    who had tried once that they had tried too often. Still closed: nothing signs in."""
    broken = redis_mock()
    broken.pipeline.side_effect = RedisConnectionError("down")
    sign_in.app.dependency_overrides[get_redis] = lambda: broken
    backstop_up = AsyncMock(return_value=True)
    with (
        patch.object(signin_limit, "address_allowed", backstop_up)
        if down == "identity"
        else nullcontext()
    ):
        _unavailable(sign_in.client().post(f"/auth/{provider}", json=_body(provider)))
    # A backstop that fails closed verifies nothing; an identity check that does reads no account.
    assert sign_in.verified == ([] if down == "backstop" else ["person"])
    sign_in.accounts_read.assert_not_awaited()
    sign_in.sessions.assert_not_awaited()


@pytest.mark.parametrize("provider", ["google", "apple"])
@pytest.mark.parametrize(
    "outage",
    [
        ConnectionRefusedError("Connect call failed ('127.0.0.1', 5432)"),
        OperationalError("SELECT", {}, Exception("server closed the connection")),
        SQLAlchemyTimeoutError("QueuePool limit reached"),
    ],
    ids=["refused", "dropped", "pool"],
)
def test_a_postgres_outage_answers_503_with_a_code(sign_in, provider, outage):
    """It answered 503 with the English "Service temporarily unavailable" and no code."""
    sign_in.accounts_read.side_effect = outage
    _unavailable(sign_in.client().post(f"/auth/{provider}", json=_body(provider)))
    sign_in.sessions.assert_not_awaited()


def test_a_session_store_outage_answers_503_with_a_code(sign_in):
    sign_in.sessions.side_effect = RedisUnavailableError()
    _unavailable(sign_in.client().post("/auth/google", json=_body("google")))


def test_the_identity_key_is_an_hmac_per_provider_and_secret() -> None:
    other_secret = Settings(jwt_secret="another-secret-32-chars-long-enough!!")
    key = signin_limit.identity_key(_SETTINGS, "google", "1234567890")
    assert "1234567890" not in key
    assert key != signin_limit.identity_key(_SETTINGS, "apple", "1234567890")
    assert key != signin_limit.identity_key(other_secret, "google", "1234567890")
    carry = quota_carryover.carry_key(_SETTINGS, "google", "1234567890")
    assert key.rsplit(":", 1)[1] not in carry


def test_the_limits_are_looser_than_the_old_and_global_ones_and_match_refresh() -> None:
    assert signin_limit.PER_IP_LIMIT > _GLOBAL_LIMIT > 30
    assert signin_limit.PER_IDENTITY_LIMIT < signin_limit.PER_IP_LIMIT
    # With provider keys kept per process a verify is cheap: the address backstop is
    # refresh's (it was half that while each Google verify fetched Google's certs).
    assert signin_limit.PER_IP_LIMIT == refresh_limit.PER_IP_LIMIT == 600
    assert signin_limit.DEV_PER_IP_LIMIT == 30
