"""A sign-in tapped under the outside-AI disclosure records the agreement with it.

The phone asked on a separate screen after sign-in (``PATCH /auth/me``). Its sign-in
page now says beside the buttons that continuing agrees, and the tap sends
``ai_data_consent: true`` with the sign-in, so the account agrees before its first
token. A sign-in without the flag (an older phone, the web) leaves the account as it
was, to be asked after sign-in as before.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.orm import User
from app.models.schemas import AuthResponse
from app.modules.account import service as auth_service
from app.repositories import users

_SETTINGS = Settings(
    dev_auth_enabled=True, email_enabled=False, jwt_secret="test-secret-long-enough-32-chars!!"
)


async def _sign_in(
    provider: str, session: AsyncSession, redis: Redis, sub: str, *, ai_data_consent: bool = False
) -> AuthResponse:
    """One real sign-in through the account service; only the provider's token check is faked."""
    email = f"{sub}@icloud.com"
    payload = {"sub": sub, "email": email, "email_verified": "true", "name": "Ada"}
    if provider == "google":
        with patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ):
            return await auth_service.login_with_google(
                session, _SETTINGS, "tok", redis, ai_data_consent=ai_data_consent
            )
    if provider == "apple":
        with patch(
            "app.modules.account.service.verify_apple_id_token", AsyncMock(return_value=payload)
        ):
            return await auth_service.login_with_apple(
                session, _SETTINGS, "tok", redis, ai_data_consent=ai_data_consent
            )
    return await auth_service.login_dev(
        session, _SETTINGS, email=email, name="Ada", redis=redis, ai_data_consent=ai_data_consent
    )


async def _existing(session: AsyncSession, provider: str, sub: str) -> User:
    """The account a later sign-in of ``sub`` finds (dev keys it as ``dev:<email>``)."""
    email = f"{sub}@icloud.com"
    ids = {
        "google": {"google_sub": sub},
        "apple": {"apple_sub": sub},
        "dev": {"google_sub": f"dev:{email}"},
    }[provider]
    return await users.create(
        session,
        email=email,
        name="Ada",
        avatar_url=None,
        google_sub=ids.get("google_sub"),
        apple_sub=ids.get("apple_sub"),
    )


async def _stored_consent(session: AsyncSession, user_id: Any) -> datetime | None:
    row = await session.get(User, user_id, populate_existing=True)
    assert row is not None
    return row.ai_data_consent_at


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "apple", "dev"])
async def test_sign_in_with_the_flag_records_consent_for_a_new_account(
    db_session: AsyncSession, fake_redis: Redis, provider: str
) -> None:
    before = datetime.now(UTC)

    auth = await _sign_in(provider, db_session, fake_redis, str(uuid4()), ai_data_consent=True)

    stored = await _stored_consent(db_session, auth.user.id)
    assert stored is not None and stored >= before
    # The reply carries it, so the phone goes straight to the chat.
    assert auth.user.ai_data_consent_at == stored


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "apple", "dev"])
async def test_sign_in_without_the_flag_leaves_consent_unset(
    db_session: AsyncSession, fake_redis: Redis, provider: str
) -> None:
    auth = await _sign_in(provider, db_session, fake_redis, str(uuid4()))

    assert await _stored_consent(db_session, auth.user.id) is None
    assert auth.user.ai_data_consent_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "apple", "dev"])
async def test_sign_in_with_the_flag_records_consent_for_an_account_without_it(
    db_session: AsyncSession, fake_redis: Redis, provider: str
) -> None:
    """One from before sign-in agreed, or one that withdrew in Data controls."""
    sub = str(uuid4())
    user = await _existing(db_session, provider, sub)

    auth = await _sign_in(provider, db_session, fake_redis, sub, ai_data_consent=True)

    assert auth.user.id == user.id
    assert await _stored_consent(db_session, user.id) is not None


@pytest.mark.asyncio
async def test_sign_in_with_the_flag_keeps_an_earlier_agreements_time(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    sub = str(uuid4())
    user = await _existing(db_session, "google", sub)
    agreed = datetime.now(UTC) - timedelta(days=30)
    await users.update(db_session, user, ai_data_consent_at=agreed)

    await _sign_in("google", db_session, fake_redis, sub, ai_data_consent=True)

    assert await _stored_consent(db_session, user.id) == agreed


# ── HTTP: each sign-in route reads the flag, absent means not agreed ────────────


def _route_kwargs(path: str, body: dict[str, Any], service_fn: str) -> dict[str, Any]:
    """What the route hands the account service for ``body``."""
    from app.core.deps import get_settings_dep
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=True,
        jwt_secret="test-secret-32-chars-long-enough!!",
    )
    login = AsyncMock(side_effect=RuntimeError("stop after the call"))
    with (
        patch(f"app.modules.account.api.auth_service.{service_fn}", login),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        client.post(path, json=body)
    login.assert_awaited_once()
    assert login.await_args is not None
    return dict(login.await_args.kwargs)


_ROUTES = [
    ("/auth/google", {"id_token": "tok"}, "login_with_google"),
    ("/auth/apple", {"id_token": "tok", "nonce": "n"}, "login_with_apple"),
    ("/auth/dev", {"email": "dev@recall.local", "name": "Dev"}, "login_dev"),
]


@pytest.mark.parametrize(("path", "body", "service_fn"), _ROUTES)
@pytest.mark.parametrize(("flag", "agreed"), [({"ai_data_consent": True}, True), ({}, False)])
def test_sign_in_route_passes_the_agreement_on(
    path: str, body: dict[str, Any], service_fn: str, flag: dict[str, bool], agreed: bool
) -> None:
    assert _route_kwargs(path, {**body, **flag}, service_fn)["ai_data_consent"] is agreed
