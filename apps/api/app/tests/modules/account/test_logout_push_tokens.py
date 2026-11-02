"""Signing out stops this account's reminders reaching the device.

Logout revoked tokens only; the device's push row stayed, so the scheduler kept putting the
signed-out account's reminder text on the lock screen. ``/auth/logout`` now forgets the
device's push token, and signing out everywhere forgets every device's.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.orm import PushToken, User
from app.modules.account import lifecycle
from app.modules.account import tokens as tokens_service
from app.repositories import push_tokens, users

_SETTINGS = Settings(jwt_secret="x" * 32)


async def _user(session) -> User:
    return await users.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Signed in",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def _register(session, user: User, device: str) -> str:
    token = f"ExponentPushToken[{uuid4().hex}]"
    await push_tokens.upsert(
        session, user_id=user.id, expo_push_token=token, platform="ios", device_id=device
    )
    return token


async def _tokens(session, user: User) -> set[str]:
    rows = await session.execute(
        select(PushToken.expo_push_token).where(PushToken.user_id == user.id)
    )
    return set(rows.scalars())


async def test_logout_forgets_this_devices_push_token(db_session, fake_redis) -> None:
    user = await _user(db_session)
    phone = await _register(db_session, user, "phone")
    tablet = await _register(db_session, user, "tablet")
    access, refresh = await tokens_service.issue_token_pair(fake_redis, user.id, _SETTINGS)

    await lifecycle.logout(
        db_session,
        fake_redis,
        _SETTINGS,
        access_token=access,
        refresh_token=refresh,
        expo_push_token=phone,
    )

    assert await _tokens(db_session, user) == {tablet}


async def test_an_expired_access_token_still_forgets_it_through_the_refresh_token(
    db_session, fake_redis
) -> None:
    user = await _user(db_session)
    phone = await _register(db_session, user, "phone")
    _access, refresh = await tokens_service.issue_token_pair(fake_redis, user.id, _SETTINGS)

    await lifecycle.logout(
        db_session,
        fake_redis,
        _SETTINGS,
        access_token="expired-or-garbled",
        refresh_token=refresh,
        expo_push_token=phone,
    )

    assert await _tokens(db_session, user) == set()


async def test_a_token_string_alone_never_silences_another_accounts_device(
    db_session, fake_redis
) -> None:
    owner, stranger = await _user(db_session), await _user(db_session)
    owners_phone = await _register(db_session, owner, "phone")
    access, refresh = await tokens_service.issue_token_pair(fake_redis, stranger.id, _SETTINGS)

    await lifecycle.logout(
        db_session,
        fake_redis,
        _SETTINGS,
        access_token=access,
        refresh_token=refresh,
        expo_push_token=owners_phone,
    )

    assert await _tokens(db_session, owner) == {owners_phone}


async def test_signing_out_everywhere_forgets_every_device(db_session, fake_redis) -> None:
    user, other = await _user(db_session), await _user(db_session)
    await _register(db_session, user, "phone")
    await _register(db_session, user, "tablet")
    others = await _register(db_session, other, "phone")
    access, _refresh = await tokens_service.issue_token_pair(fake_redis, user.id, _SETTINGS)

    await lifecycle.logout_everywhere(
        db_session, fake_redis, _SETTINGS, user.id, access_token=access
    )

    assert await _tokens(db_session, user) == set()
    assert await _tokens(db_session, other) == {others}


@pytest.mark.parametrize("with_push_token", [False, True])
async def test_logout_without_a_session_proof_keeps_every_row(
    db_session, fake_redis, with_push_token: bool
) -> None:
    user = await _user(db_session)
    phone = await _register(db_session, user, "phone")

    await lifecycle.logout(
        db_session,
        fake_redis,
        _SETTINGS,
        access_token=None,
        refresh_token="never-issued",
        expo_push_token=phone if with_push_token else None,
    )

    assert await _tokens(db_session, user) == {phone}
