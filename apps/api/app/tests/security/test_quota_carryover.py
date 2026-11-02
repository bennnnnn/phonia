"""Deleting an account and signing up again with the same login keeps today's limits.

Quota counters are keyed by user id, so a new account would start every daily
cap (and this month's live talk minutes) from zero. Account delete keeps one
snapshot keyed by an HMAC of the Google/Apple identity and, on an address a provider
owns (Gmail, iCloud), one keyed by an HMAC of the account's email; the new account for the
same identity or address picks them up at sign-up (the address alone:
``test_quota_carryover_email.py``, ownership: ``test_quota_carryover_email_owner.py``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.orm import User
from app.modules.billing.entitlements import setting_name
from app.services import quota
from app.services.quota import carryover, counters

from .conftest import World, delete_accounts

# Every per-user daily counter, named independently of the code under test.
DAILY_PREFIXES = ("usage", "imgup", "docup", "speech", "tts", "tavily", "imggen", "imgsearch")


def _pro_caps(cap: int) -> Settings:
    caps: dict[str, Any] = {
        setting_name(spec.allowance, "pro"): cap for spec in counters.COUNTERS.values()
    }
    return Settings(**caps)


async def _google_sub(user_id: UUID) -> str:
    async with SessionLocal() as session:
        sub = (await session.execute(select(User.google_sub).where(User.id == user_id))).scalar()
    assert sub
    return str(sub)


async def _on_gmail(user_id: UUID) -> str:
    """Move the Google account to a Gmail address, which Google owns, so its delete files
    the email key too (``World`` accounts are on example.com, which no provider owns).
    Returns the address."""
    email = f"carry-{uuid4().hex[:12]}@gmail.com"
    async with SessionLocal() as session:
        await session.execute(update(User).where(User.id == user_id).values(email=email))
        await session.commit()
    return email


async def _sign_in_google(world: World, *, sub: str, email: str) -> UUID:
    payload = {"sub": sub, "email": email, "name": "Again", "email_verified": True}
    with patch(
        "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
    ):
        response = await world.client.post("/auth/google", json={"id_token": "token"})
    assert response.status_code == 200, response.text
    return UUID(response.json()["user"]["id"])


async def _use_quota(redis: Any, user_id: UUID) -> None:
    """What a busy day leaves: tokens, uploads, voice, searches, images, live talk."""
    assert await quota.reserve_usage_up_to(redis, str(user_id), 1234, daily_limit=10**9) == 1234
    user, caps = User(id=user_id, plan="pro"), _pro_caps(10)
    for _ in range(2):
        assert await counters.reserve("image_upload", redis, user, caps)
    for _ in range(3):
        assert await counters.reserve("document_upload", redis, user, caps)
    for _ in range(3):
        assert await counters.reserve("speech_transcription", redis, user, caps)
    assert await counters.reserve("speech_tts", redis, user, caps)
    for _ in range(4):
        assert await counters.reserve("tavily_search", redis, user, caps)
    assert await counters.reserve("image_generation", redis, user, caps)
    for _ in range(2):
        assert await counters.reserve("image_search", redis, user, caps)
    granted = await quota.reserve_live_talk_seconds(
        redis,
        user_id,
        allowance_seconds=3600,
        max_session_seconds=300,
        min_session_seconds=1,
    )
    assert granted == 300


_USED = {
    "usage": 1234,
    "imgup": 2,
    "docup": 3,
    "speech": 3,
    "tts": 1,
    "tavily": 4,
    "imggen": 1,
    "imgsearch": 2,
}


async def _daily_counts(redis: Any, user_id: UUID, day: Any = None) -> dict[str, int]:
    day = day or quota.utc_today()
    return {
        prefix: int(await redis.get(counters.daily_key(prefix, user_id, day)) or 0)
        for prefix in DAILY_PREFIXES
    }


async def _delete_and_sweep(world: World, user_id: UUID, headers: dict[str, str]) -> None:
    from app.background.handlers import _handle_storage_sweep

    response = await world.client.delete("/auth/me", headers=headers)
    assert response.status_code == 204
    await _handle_storage_sweep(world.settings, {"user_id": str(user_id)})


async def _all_redis_text(redis: Any) -> str:
    """Every key name and every string, hash and stream value, as one blob."""
    parts: list[str] = []
    async for key in redis.scan_iter(match="*"):
        parts.append(key)
        kind = await redis.type(key)
        if kind == "string":
            parts.append(str(await redis.get(key)))
        elif kind == "hash":
            parts.append(json.dumps(await redis.hgetall(key)))
        elif kind == "stream":
            parts.append(json.dumps(await redis.xrange(key)))
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_quota_carryover_same_google_sub_keeps_todays_counts(world: World) -> None:
    redis, a = world.redis, world.a
    sub, email = await _google_sub(a.id), await _on_gmail(a.id)
    await _use_quota(redis, a.id)

    await _delete_and_sweep(world, a.id, a.headers)
    new_id = await _sign_in_google(world, sub=sub, email=email)
    try:
        assert new_id != a.id
        assert await _daily_counts(redis, new_id) == _USED
        assert await quota.live_talk_used_seconds(redis, new_id) == 300
        # The carried counts are enforced: one image generation was today's cap.
        new_user = User(id=new_id, plan="pro")
        assert not await counters.reserve("image_generation", redis, new_user, _pro_caps(1))
        # The raise-only DB heal (the new account has no usage rows) keeps them.
        await quota.heal_usage_drift(redis, str(new_id), 10)
        assert await quota.get_daily_usage(redis, str(new_id)) == 1234
        # Used once: neither the identity's snapshot nor the address's is left to carry
        # into a third account.
        assert [key async for key in redis.scan_iter(match="quota_carry:*")] == []
    finally:
        await delete_accounts(new_id)


@pytest.mark.asyncio
async def test_quota_carryover_same_apple_sub_keeps_todays_counts(world: World) -> None:
    redis, a = world.redis, world.a
    apple_sub = f"apple-{uuid4()}"
    async with SessionLocal() as session:
        row = await session.get(User, a.id)
        assert row is not None
        row.apple_sub = apple_sub
        await session.commit()
    await _use_quota(redis, a.id)

    await _delete_and_sweep(world, a.id, a.headers)
    payload = {"sub": apple_sub, "email": f"again-{uuid4()}@example.com", "email_verified": "true"}
    with patch(
        "app.modules.account.service.verify_apple_id_token", AsyncMock(return_value=payload)
    ):
        response = await world.client.post("/auth/apple", json={"id_token": "t", "nonce": "n"})
    assert response.status_code == 200, response.text
    new_id = UUID(response.json()["user"]["id"])
    try:
        assert await _daily_counts(redis, new_id) == _USED
        assert await quota.live_talk_used_seconds(redis, new_id) == 300
    finally:
        await delete_accounts(new_id)


@pytest.mark.asyncio
async def test_quota_carryover_different_sub_starts_fresh(world: World) -> None:
    redis, a = world.redis, world.a
    await _use_quota(redis, a.id)

    await _delete_and_sweep(world, a.id, a.headers)
    new_id = await _sign_in_google(
        world, sub=f"other-{uuid4()}", email=f"other-{uuid4()}@example.com"
    )
    try:
        assert await _daily_counts(redis, new_id) == dict.fromkeys(DAILY_PREFIXES, 0)
        assert await quota.live_talk_used_seconds(redis, new_id) == 0
    finally:
        await delete_accounts(new_id)


@pytest.mark.asyncio
async def test_quota_carryover_next_day_starts_fresh(world: World) -> None:
    redis, a = world.redis, world.a
    sub = await _google_sub(a.id)
    await _use_quota(redis, a.id)
    month = quota.utc_month()
    await _delete_and_sweep(world, a.id, a.headers)

    tomorrow = quota.utc_today() + timedelta(days=1)
    with (
        patch("app.services.quota.carryover.utc_today", return_value=tomorrow),
        patch("app.services.quota.carryover.utc_month", return_value=month),
    ):
        new_id = await _sign_in_google(world, sub=sub, email=f"again-{uuid4()}@example.com")
    try:
        assert await _daily_counts(redis, new_id, tomorrow) == dict.fromkeys(DAILY_PREFIXES, 0)
        # Still the same month: live talk minutes are monthly, so they carry.
        assert await quota.live_talk_used_seconds(redis, new_id, month=month) == 300
    finally:
        await delete_accounts(new_id)


@pytest.mark.asyncio
async def test_quota_carryover_next_month_starts_live_talk_fresh(world: World) -> None:
    redis, a = world.redis, world.a
    sub = await _google_sub(a.id)
    await _use_quota(redis, a.id)
    await _delete_and_sweep(world, a.id, a.headers)

    with (
        patch(
            "app.services.quota.carryover.utc_today",
            return_value=quota.utc_today() + timedelta(days=40),
        ),
        patch("app.services.quota.carryover.utc_month", return_value="2999-01"),
    ):
        new_id = await _sign_in_google(world, sub=sub, email=f"again-{uuid4()}@example.com")
    try:
        assert await quota.live_talk_used_seconds(redis, new_id, month="2999-01") == 0
    finally:
        await delete_accounts(new_id)


@pytest.mark.asyncio
async def test_quota_carryover_snapshot_holds_no_raw_sub(world: World) -> None:
    from app.modules.account import quota_carryover

    redis, a = world.redis, world.a
    sub, email = await _google_sub(a.id), await _on_gmail(a.id)
    await _use_quota(redis, a.id)
    await _delete_and_sweep(world, a.id, a.headers)

    keys = {key async for key in redis.scan_iter(match="quota_carry:*")}
    assert keys == {
        quota_carryover.carry_key(world.settings, "google", sub),
        quota_carryover.email_carry_key(world.settings, email),
    }
    everything = await _all_redis_text(redis)
    assert sub not in everything
    # The address is only ever a one-way code, in any case.
    assert email.lower() not in everything.lower()
    month_left = (quota.next_month_start() - datetime.now(UTC)).total_seconds()
    for key in keys:
        # Counts only: the same snapshot under each key.
        assert set(json.loads(await redis.get(key))) == {
            "day",
            "month",
            "daily",
            "live_talk_seconds",
        }
        assert str(a.id) not in await redis.get(key)
        assert month_left - 60 <= await redis.ttl(key) <= 35 * 24 * 60 * 60


def _carry_down(redis: Any, step: str) -> Any:
    """Redis failing at one step of the carry-over only: reading the account's counters
    (one MGET of them all) or storing the snapshot. Sign-in checks and sessions still work."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    def fails(key: str) -> bool:
        return key.startswith("usage:" if step == "read" else "quota_carry:")

    async def down(*_args: Any, **_kwargs: Any) -> Any:
        raise RedisConnectionError("Error 111 connecting to redis")

    if step == "read":
        real_mget = redis.mget

        async def mget(keys: Any, *args: Any) -> Any:
            names = [keys] if isinstance(keys, str) else list(keys)
            if any(fails(name) for name in names):
                return await down()
            return await real_mget(keys, *args)

        return patch.object(redis, "mget", mget)
    real_set = redis.set

    async def set_(key: str, *args: Any, **kwargs: Any) -> Any:
        if fails(key):
            return await down()
        return await real_set(key, *args, **kwargs)

    return patch.object(redis, "set", set_)


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["read", "write"])
async def test_quota_carryover_unsaved_refuses_delete_and_keeps_the_account(
    world: World, step: str
) -> None:
    """A delete whose counters cannot be carried is refused, before anything is undone.

    It was best-effort: a delete while Redis failed lost the day's counters, and the same
    sign-in started a new account from zero (the abuse the carry-over exists to stop).
    Refused with the shared 503 ``unavailable``, the account, its sessions and its counters
    stay as they were, so the retry the phone asks for deletes it and carries them.
    """
    redis, a = world.redis, world.a
    sub = await _google_sub(a.id)
    await _use_quota(redis, a.id)

    with _carry_down(redis, step):
        refused = await world.client.delete("/auth/me", headers=a.headers)

    assert refused.status_code == 503
    assert refused.json() == {
        "detail": {
            "code": "unavailable",
            "message": "Service temporarily unavailable. Please retry shortly.",
        }
    }
    assert refused.headers["retry-after"] == "5"
    async with SessionLocal() as session:
        assert await session.get(User, a.id) is not None
    # Still signed in: the retry needs no new sign-in.
    assert (await world.client.get("/auth/me", headers=a.headers)).status_code == 200
    assert await _daily_counts(redis, a.id) == _USED

    await _delete_and_sweep(world, a.id, a.headers)
    again = await _sign_in_google(world, sub=sub, email=f"again-{uuid4()}@example.com")
    try:
        assert await _daily_counts(redis, again) == _USED
    finally:
        await delete_accounts(again)


def test_quota_carryover_names_every_daily_counter() -> None:
    """A daily cap added to the quota package must be carried too."""
    import importlib
    import inspect
    import pkgutil
    import re

    sources = "".join(
        inspect.getsource(importlib.import_module(f"app.services.quota.{module.name}"))
        for module in pkgutil.iter_modules(quota.__path__)
    )
    used = set(re.findall(r'daily_key\(\s*"([a-z:]+)"', sources))
    used |= {spec.prefix for spec in counters.COUNTERS.values()}
    assert used - {"usage:heal"} <= set(carryover.DAILY_COUNTER_PREFIXES)
    assert set(carryover.DAILY_COUNTER_PREFIXES) == set(DAILY_PREFIXES)


def _restore_down(redis: Any, step: str) -> Any:
    """Redis failing at one step of the sign-in restore only: reading the snapshots (one
    MGET), raising the new account's counters, or dropping the used snapshots."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def down(*_args: Any, **_kwargs: Any) -> Any:
        raise RedisConnectionError("Error 111 connecting to redis")

    if step == "apply":
        return patch("app.services.quota.apply_carried_usage", down)
    name = "mget" if step == "read" else "delete"
    real = getattr(redis, name)

    async def call(*keys: Any, **kwargs: Any) -> Any:
        names = [name for key in keys for name in ([key] if isinstance(key, str) else key)]
        if any(str(name).startswith("quota_carry:") for name in names):
            return await down()
        return await real(*keys, **kwargs)

    return patch.object(redis, name, call)


async def _accounts_for_sub(sub: str) -> int:
    async with SessionLocal() as session:
        rows = await session.execute(select(User.id).where(User.google_sub == sub))
        return len(rows.all())


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["read", "apply"])
async def test_quota_carryover_unrestored_refuses_sign_in_and_creates_no_account(
    world: World, step: str
) -> None:
    """A new account whose carried counters cannot be restored is not made.

    The restore was best-effort: Redis failing at exactly that step signed the new account
    in with every daily cap at zero, and the next sign-in found the account and never
    restored (the delete-and-recreate reset the carry-over exists to stop). Now sign-in
    answers the shared 503 ``sign_in_unavailable`` with no account made, the snapshot
    kept, and the retry restores it.
    """
    redis, a = world.redis, world.a
    sub, email = await _google_sub(a.id), await _on_gmail(a.id)
    await _use_quota(redis, a.id)
    await _delete_and_sweep(world, a.id, a.headers)
    snapshots = await _carry_snapshots(redis)
    assert len(snapshots) == 2  # the identity's and the address's

    payload = {"sub": sub, "email": email, "email_verified": True}
    with (
        patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ),
        _restore_down(redis, step),
    ):
        refused = await world.client.post("/auth/google", json={"id_token": "token"})

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "sign_in_unavailable"
    assert await _accounts_for_sub(sub) == 0
    assert await _carry_snapshots(redis) == snapshots

    again = await _sign_in_google(world, sub=sub, email=str(payload["email"]))
    try:
        assert await _daily_counts(redis, again) == _USED
        assert await quota.live_talk_used_seconds(redis, again) == 300
        assert [key async for key in redis.scan_iter(match="quota_carry:*")] == []
    finally:
        await delete_accounts(again)


@pytest.mark.asyncio
async def test_quota_carryover_snapshot_left_after_restore_still_signs_in(world: World) -> None:
    """Dropping the used snapshot comes after the account commits, best effort: the
    counters are already raised, and a leftover snapshot only raises, never lowers."""
    redis, a = world.redis, world.a
    sub = await _google_sub(a.id)
    await _use_quota(redis, a.id)
    await _delete_and_sweep(world, a.id, a.headers)

    with _restore_down(redis, "drop"):
        again = await _sign_in_google(world, sub=sub, email=f"again-{uuid4()}@example.com")
    try:
        assert await _daily_counts(redis, again) == _USED
        assert await _accounts_for_sub(sub) == 1
    finally:
        await delete_accounts(again)


async def _carry_snapshots(redis: Any) -> dict[str, str]:
    return {key: await redis.get(key) async for key in redis.scan_iter(match="quota_carry:*")}
