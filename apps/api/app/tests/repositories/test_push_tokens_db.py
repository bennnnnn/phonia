"""Push-token registration against Postgres: one statement per registration, the
cross-account rule, and the per-account cap."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text

from app.exceptions import PushTokenBindError
from app.models.orm import PushToken, User
from app.repositories import push_tokens as repo
from app.repositories import users


async def _user(session) -> User:
    return await users.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Owner",
        avatar_url=None,
        google_sub=str(uuid4()),
    )


async def _rows(session, token: str) -> list[PushToken]:
    result = await session.execute(select(PushToken).where(PushToken.expo_push_token == token))
    return list(result.scalars().all())


def _token() -> str:
    return f"ExponentPushToken[{uuid4().hex}]"


async def test_a_second_registration_of_the_same_token_updates_one_row(db_session):
    user = await _user(db_session)
    token = _token()
    await repo.upsert(
        db_session, user_id=user.id, expo_push_token=token, platform="ios", device_id="d1"
    )
    row = await repo.upsert(
        db_session,
        user_id=user.id,
        expo_push_token=token,
        platform="android",
        device_id=None,  # a missing device id keeps the stored one
        android_channels="tone",
    )
    rows = await _rows(db_session, token)
    assert len(rows) == 1
    assert (row.platform, row.device_id, row.android_channels) == ("android", "d1", "tone")


async def test_two_registrations_at_once_store_one_row(db_session):
    """Two registrations of one token at once (an app start and a permission grant) both
    read no row and both inserted; the second failed with a 500 on
    uq_push_tokens_expo_token. Each is now one INSERT ... ON CONFLICT. Two real
    transactions, committed, then removed."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.db import engine

    await engine.dispose(close=False)
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = await _user(setup)
    token = _token()

    async def register(device: str) -> PushToken:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await repo.upsert(
                session, user_id=user.id, expo_push_token=token, platform="ios", device_id=device
            )

    try:
        rows = await asyncio.gather(register("d1"), register("d1"))
        assert rows[0].id == rows[1].id
        async with AsyncSession(engine) as check:
            assert len(await _rows(check, token)) == 1
    finally:
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user.id))  # tokens cascade
            await cleanup.commit()
        await engine.dispose(close=False)


@pytest.mark.parametrize(
    ("prior_device", "device", "message"),
    [
        ("device-a", None, "device_id is required"),
        ("device-a", "device-b", "different device"),
        (None, "any-device", "bound to another account"),  # a row from before device ids
    ],
)
async def test_another_accounts_token_stays_without_the_same_install(
    db_session, prior_device, device, message
):
    owner = await _user(db_session)
    other = await _user(db_session)
    token = _token()
    await repo.upsert(
        db_session,
        user_id=owner.id,
        expo_push_token=token,
        platform="ios",
        device_id=prior_device,
    )
    with pytest.raises(PushTokenBindError, match=message):
        await repo.upsert(
            db_session, user_id=other.id, expo_push_token=token, platform="ios", device_id=device
        )
    rows = await _rows(db_session, token)
    assert [row.user_id for row in rows] == [owner.id]


async def test_the_same_install_moves_its_token_to_the_new_account(db_session):
    owner = await _user(db_session)
    other = await _user(db_session)
    token = _token()
    await repo.upsert(
        db_session, user_id=owner.id, expo_push_token=token, platform="ios", device_id="device-a"
    )
    row = await repo.upsert(
        db_session, user_id=other.id, expo_push_token=token, platform="ios", device_id="device-a"
    )
    assert row.user_id == other.id
    assert [r.user_id for r in await _rows(db_session, token)] == [other.id]


async def test_an_account_keeps_its_newest_tokens_up_to_the_cap(db_session):
    user = await _user(db_session)
    tokens = [_token() for _ in range(4)]
    for index, token in enumerate(tokens):
        await repo.upsert(
            db_session,
            user_id=user.id,
            expo_push_token=token,
            platform="ios",
            device_id=f"device-{index}",
            max_per_user=10,
        )
        # Each registration in its own moment: now() is the transaction's start.
        await db_session.execute(
            text(
                "UPDATE push_tokens SET updated_at = now() - make_interval(mins => :m) "
                "WHERE expo_push_token = :t"
            ),
            {"m": 10 - index, "t": token},
        )
    newest = _token()
    await repo.upsert(
        db_session,
        user_id=user.id,
        expo_push_token=newest,
        platform="ios",
        device_id="device-new",
        max_per_user=3,
    )
    kept = {row.expo_push_token for row in await repo.list_for_user(db_session, user.id)}
    assert kept == {newest, tokens[3], tokens[2]}
