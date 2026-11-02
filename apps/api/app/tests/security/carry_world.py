"""The app on the configured Redis, for the quota carry-over tests that sign in and delete
accounts through the HTTP routes (``test_quota_carryover_link.py``,
``test_quota_carryover_email.py``; the ``linked`` fixture in ``conftest.py``).

What a test makes in Redis is deleted by name after it: the configured Redis may be a
shared development one, so nothing else (the job stream, the per-IP limiter) is touched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import SessionLocal, engine
from app.core.redis import get_redis_client
from app.models.orm import User
from app.modules.account import quota_carryover, signin_limit
from app.modules.account.email_authority import SignInProvider
from app.modules.billing.entitlements import setting_name
from app.services import quota
from app.services.quota import carryover, counters, live_talk

from .conftest import delete_accounts, isolated_settings, reset_process_caches


@dataclass
class Linked:
    client: httpx.AsyncClient
    settings: Settings
    redis: Any
    users: list[UUID]
    made_ids: set[UUID] = field(default_factory=set)
    identities: set[tuple[str, str]] = field(default_factory=set)
    emails: set[str] = field(default_factory=set)
    refresh_tokens: set[str] = field(default_factory=set)


@asynccontextmanager
async def linked_world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Linked]:
    from app.main import create_app

    settings = isolated_settings(monkeypatch, tmp_path)
    # One UTC day and month for the whole test: a run across midnight keeps its counters.
    day, month = quota.utc_today(), quota.utc_month()
    monkeypatch.setattr(counters, "clock", lambda: day)
    monkeypatch.setattr(live_talk, "utc_month", lambda: month)
    monkeypatch.setattr(carryover, "utc_month", lambda: month)
    redis = get_redis_client()
    await engine.dispose(close=False)
    world: Linked | None = None
    try:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            world = Linked(client=client, settings=settings, redis=redis, users=[])
            yield world
    finally:
        if world is not None:
            await delete_accounts(*world.users)
            await _delete_made_keys(world)
        await redis.aclose()
        await engine.dispose(close=False)
        reset_process_caches()


async def _delete_made_keys(world: Linked) -> None:
    made = {f"refresh:{token}" for token in world.refresh_tokens}
    for provider, sub in world.identities:
        made.add(quota_carryover.carry_key(world.settings, provider, sub))
        limited: SignInProvider = "apple" if provider == "apple" else "google"
        made.add(signin_limit.identity_key(world.settings, limited, sub))
    for email in world.emails:
        by_email = quota_carryover.email_carry_key(world.settings, email)
        if by_email is not None:
            made.add(by_email)
    for user_id in world.made_ids:
        made.update([key async for key in world.redis.scan_iter(match=f"*{user_id}*")])
    if made:
        await world.redis.delete(*made)


async def sign_in(
    world: Linked, provider: str, sub: str, email: str, claims: Mapping[str, Any] | None = None
) -> httpx.Response:
    """Sign in through the route with a verified token for *email* (plus *claims*, such as
    Google's ``hd``)."""
    world.identities.add((provider, sub))
    world.emails.add(email)
    payload: dict[str, Any] = {"sub": sub, "email": email, "email_verified": True}
    if provider == "apple":
        payload["email_verified"] = "true"
    payload.update(claims or {})
    verify = f"app.modules.account.service.verify_{provider}_id_token"
    with patch(verify, AsyncMock(return_value=payload)):
        return await world.client.post(
            f"/auth/{provider}", json={"id_token": "token", "nonce": "n"}
        )


async def signed_in(
    world: Linked, provider: str, sub: str, email: str, claims: Mapping[str, Any] | None = None
) -> tuple[UUID, str]:
    response = await sign_in(world, provider, sub, email, claims)
    assert response.status_code == 200, response.text
    body = response.json()
    user_id = UUID(body["user"]["id"])
    world.made_ids.add(user_id)
    world.refresh_tokens.add(str(body["refresh_token"]))
    if user_id not in world.users:
        world.users.append(user_id)
    return user_id, str(body["access_token"])


async def use(redis: Any, user_id: UUID, used: dict[str, int], live_talk: int = 0) -> None:
    """Spend *used* of each daily counter (by prefix) and *live_talk* seconds."""
    allowances: dict[str, Any] = {
        setting_name(spec.allowance, "pro"): 10 for spec in counters.COUNTERS.values()
    }
    caps = Settings(**allowances)
    user = User(id=user_id, plan="pro")
    tokens = used["usage"]
    assert await quota.reserve_usage_up_to(redis, str(user_id), tokens, daily_limit=10**9) == tokens
    for name, spec in counters.COUNTERS.items():
        for _ in range(used.get(spec.prefix, 0)):
            assert await counters.reserve(name, redis, user, caps)
    if live_talk:
        granted = await quota.reserve_live_talk_seconds(
            redis,
            user_id,
            allowance_seconds=3600,
            max_session_seconds=live_talk,
            min_session_seconds=1,
        )
        assert granted == live_talk


async def counts(redis: Any, user_id: UUID) -> dict[str, int]:
    day = quota.utc_today()
    found = {
        prefix: int(await redis.get(counters.daily_key(prefix, user_id, day)) or 0)
        for prefix in ("usage", "imggen", "tavily")
    }
    return {prefix: used for prefix, used in found.items() if used}


async def delete(world: Linked, user_id: UUID, token: str) -> None:
    """Delete the account through ``DELETE /auth/me`` and run its sweep."""
    from app.background.handlers import _handle_storage_sweep

    response = await world.client.delete("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204, response.text
    await _handle_storage_sweep(world.settings, {"user_id": str(user_id)})
    world.users.remove(user_id)


async def deleted_account(
    world: Linked,
    provider: str,
    email: str,
    used: dict[str, int],
    *,
    live_talk: int,
    claims: Mapping[str, Any] | None = None,
) -> str:
    """An account made with *provider* on *email* uses *used* and *live_talk* seconds and is
    deleted. Returns its sub."""
    sub = f"{provider}-{uuid4()}"
    user_id, token = await signed_in(world, provider, sub, email, claims)
    await use(world.redis, user_id, used, live_talk=live_talk)
    await delete(world, user_id, token)
    return sub


async def linked_sub(user_id: UUID, provider: str) -> str | None:
    column = User.apple_sub if provider == "apple" else User.google_sub
    async with SessionLocal() as session:
        value = (await session.execute(select(column).where(User.id == user_id))).scalar()
    return str(value) if value else None
