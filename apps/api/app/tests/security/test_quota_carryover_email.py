"""A deleted account's limits carry to the next account on the same email address.

Account delete kept the day's counters only under the sign-in identity
(``quota_carryover``). Delete an Apple account on x@icloud.com, sign in with Google on the
same address, and the new account started from zero: its snapshot was filed under the
Apple id. The snapshot is now also kept under a one-way code of the address (trimmed and
lower-cased) when a provider owns the address by its domain, Gmail or iCloud (only
then: ``test_quota_carryover_email_owner.py``), and every new account or new link on that
address starts from it. Each counter ends at the larger value, never summed.

Real Postgres and the configured Redis (``real_redis``), through the HTTP sign-in and
delete routes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.db import SessionLocal
from app.models.orm import User
from app.modules.account import quota_carryover
from app.services import quota

from .carry_world import (
    Linked,
    counts,
    delete,
    deleted_account,
    linked_sub,
    sign_in,
    signed_in,
    use,
)

_DELETED = {"usage": 1234, "imggen": 2, "tavily": 4}
_LIVE_TALK_SECONDS = 300
_MORE = {"usage": 5000, "tavily": 1}
# The new account's own use goes on top of what it started from.
_DELETED_THEN_MORE = {"usage": 6234, "imggen": 2, "tavily": 5}
_OTHER = {"apple": "google", "google": "apple"}
# Where each provider owns the address, so its delete files the email key.
_OWNED = {"apple": "icloud.com", "google": "gmail.com"}


def _address(domain: str = "icloud.com") -> str:
    return f"carry-{uuid4().hex[:12]}@{domain}"


def _keys(world: Linked, provider: str, sub: str, email: str) -> tuple[str, str]:
    by_email = quota_carryover.email_carry_key(world.settings, email)
    assert by_email is not None
    return quota_carryover.carry_key(world.settings, provider, sub), by_email


async def _deleted_account(
    world: Linked, provider: str, email: str, used: dict[str, int] = _DELETED
) -> str:
    """An account made with *provider* on *email* uses *used* and is deleted. Its sub."""
    return await deleted_account(world, provider, email, used, live_talk=_LIVE_TALK_SECONDS)


async def _accounts_on(email: str) -> int:
    async with SessionLocal() as session:
        rows = await session.execute(select(User.id).where(User.email == email))
        return len(rows.all())


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", ["apple", "google"])
async def test_quota_carryover_email_starts_the_other_providers_account(
    linked: Linked, deleted: str
) -> None:
    """Delete one provider's account on an address it owns; the other provider's new account
    on the same address starts from its day. Started from zero before the email key."""
    other = _OTHER[deleted]
    email = _address(_OWNED[deleted])
    deleted_sub = await _deleted_account(linked, deleted, email)
    identity_key, email_key = _keys(linked, deleted, deleted_sub, email)
    assert await linked.redis.get(identity_key) == await linked.redis.get(email_key)

    applied = AsyncMock(wraps=quota.apply_carried_usage)
    with patch("app.services.quota.apply_carried_usage", applied):
        other_sub = f"{other}-{uuid4()}"
        fresh, _ = await signed_in(linked, other, other_sub, email)
        assert await counts(linked.redis, fresh) == _DELETED
        assert await quota.live_talk_used_seconds(linked.redis, fresh) == _LIVE_TALK_SECONDS
        # The address's snapshot is used up; the deleted identity's own waits for it.
        assert await linked.redis.get(email_key) is None
        assert await linked.redis.get(identity_key) is not None

        # Applied once: the same sign-in again finds its account and restores nothing.
        again, _ = await signed_in(linked, other, other_sub, email)
        assert again == fresh
        assert applied.await_count == 1

    # The deleted identity then joins this account (its provider owns the address): its
    # snapshot holds the same counts, and raise-only never adds them a second time.
    await use(linked.redis, fresh, _MORE)
    joined, _ = await signed_in(linked, deleted, deleted_sub, email)
    assert joined == fresh
    assert await linked_sub(fresh, deleted) == deleted_sub
    assert await counts(linked.redis, fresh) == _DELETED_THEN_MORE
    assert await quota.live_talk_used_seconds(linked.redis, fresh) == _LIVE_TALK_SECONDS
    assert await linked.redis.get(identity_key) is None


@pytest.mark.asyncio
async def test_quota_carryover_email_ignores_case_and_surrounding_spaces(linked: Linked) -> None:
    """The address is trimmed and lower-cased before it is hashed: the same mailbox typed
    differently by two providers finds the snapshot."""
    local = f"Carry-{uuid4().hex[:12]}"
    await _deleted_account(linked, "google", f"  {local}@GMail.COM ")
    fresh, _ = await signed_in(linked, "apple", f"apple-{uuid4()}", f" {local.lower()}@gmail.com")
    assert await counts(linked.redis, fresh) == _DELETED
    assert await quota.live_talk_used_seconds(linked.redis, fresh) == _LIVE_TALK_SECONDS


@pytest.mark.parametrize(
    "same",
    ["x.y@gmail.com", " x.y@gmail.com", "X.Y@GMAIL.COM\n", "\tx.Y@Gmail.com  "],
)
def test_quota_carryover_email_key_normalises_only_case_and_spaces(same: str) -> None:
    settings = Settings(jwt_secret="carry-secret")
    key = quota_carryover.email_carry_key(settings, "x.y@gmail.com")
    assert key is not None and key.startswith(quota_carryover.CARRY_KEY_PREFIX)
    assert quota_carryover.email_carry_key(settings, same) == key
    # No provider's own rules: Gmail's dots and +tags name other addresses here.
    for other in ("xy@gmail.com", "x.y+tag@gmail.com", "x.y@googlemail.com"):
        assert quota_carryover.email_carry_key(settings, other) != key
    # A one-way code under the server's secret: never the address, and not one another
    # server (another secret) or the identity key could produce.
    assert "gmail" not in key
    assert quota_carryover.email_carry_key(Settings(jwt_secret="other"), same) != key
    assert quota_carryover.carry_key(settings, "email", "x.y@gmail.com") != key


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_quota_carryover_email_key_none_without_an_address(blank: str | None) -> None:
    assert quota_carryover.email_carry_key(Settings(jwt_secret="carry-secret"), blank) is None


@pytest.mark.asyncio
async def test_quota_carryover_account_without_email_keeps_only_its_identity(
    linked: Linked,
) -> None:
    """An account whose stored address is blank (the column is required, so only an empty
    value is possible) stores its identity key and nothing else."""
    email, sub = _address("gmail.com"), f"google-{uuid4()}"
    user_id, token = await signed_in(linked, "google", sub, email)
    await use(linked.redis, user_id, _DELETED)
    async with SessionLocal() as session:
        await session.execute(update(User).where(User.id == user_id).values(email=""))
        await session.commit()

    written: list[str] = []
    real_set = linked.redis.set

    async def recording_set(key: str, *args: Any, **kwargs: Any) -> Any:
        if key.startswith(quota_carryover.CARRY_KEY_PREFIX):
            written.append(key)
        return await real_set(key, *args, **kwargs)

    with patch.object(linked.redis, "set", recording_set):
        await delete(linked, user_id, token)
    assert written == [quota_carryover.carry_key(linked.settings, "google", sub)]
    assert await linked.redis.get(_keys(linked, "google", sub, email)[1]) is None


@contextmanager
def _carry_write_fails(redis: Any, failing: str) -> Iterator[None]:
    """Redis refuses to store *failing* only; every other write works."""
    real_set = redis.set

    async def set_(key: str, *args: Any, **kwargs: Any) -> Any:
        if key == failing:
            raise RedisConnectionError("Error 111 connecting to redis")
        return await real_set(key, *args, **kwargs)

    with patch.object(redis, "set", set_):
        yield


@pytest.mark.asyncio
async def test_quota_carryover_email_key_unsaved_refuses_delete(linked: Linked) -> None:
    """The address's snapshot is stored before anything is deleted, like the identity's:
    Redis refusing it refuses the delete (503 ``unavailable``), the account kept and still
    signed in, and the retry stores both."""
    email, sub = _address(), f"apple-{uuid4()}"
    user_id, token = await signed_in(linked, "apple", sub, email)
    await use(linked.redis, user_id, _DELETED)
    email_key = _keys(linked, "apple", sub, email)[1]

    headers = {"Authorization": f"Bearer {token}"}
    with _carry_write_fails(linked.redis, email_key):
        refused = await linked.client.delete("/auth/me", headers=headers)
    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "unavailable"
    assert await _accounts_on(email) == 1
    assert (await linked.client.get("/auth/me", headers=headers)).status_code == 200
    assert await counts(linked.redis, user_id) == _DELETED

    await delete(linked, user_id, token)
    fresh, _ = await signed_in(linked, "google", f"google-{uuid4()}", email)
    assert await counts(linked.redis, fresh) == _DELETED


@contextmanager
def _restore_fails(redis: Any, step: str) -> Iterator[None]:
    """Redis failing while sign-in reads the snapshots (one MGET) or raises the counters."""

    async def down(*_args: Any, **_kwargs: Any) -> Any:
        raise RedisConnectionError("Error 111 connecting to redis")

    if step == "apply":
        with patch("app.services.quota.apply_carried_usage", down):
            yield
        return
    real_mget = redis.mget

    async def mget(keys: Any, *args: Any) -> Any:
        names = [keys] if isinstance(keys, str) else list(keys)
        if any(name.startswith(quota_carryover.CARRY_KEY_PREFIX) for name in names):
            return await down()
        return await real_mget(keys, *args)

    with patch.object(redis, "mget", mget):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["read", "apply"])
async def test_quota_carryover_email_unrestored_refuses_sign_in_and_creates_nothing(
    linked: Linked, step: str
) -> None:
    """A new account whose address's snapshot cannot be restored is not made: 503
    ``sign_in_unavailable``, no account on the address, both snapshots kept, and the retry
    restores and drops the address's."""
    email = _address()
    deleted_sub = await _deleted_account(linked, "apple", email)
    keys = _keys(linked, "apple", deleted_sub, email)
    kept = [await linked.redis.get(key) for key in keys]

    google_sub = f"google-{uuid4()}"
    with _restore_fails(linked.redis, step):
        refused = await sign_in(linked, "google", google_sub, email)
    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "sign_in_unavailable"
    assert await _accounts_on(email) == 0
    assert [await linked.redis.get(key) for key in keys] == kept

    fresh, _ = await signed_in(linked, "google", google_sub, email)
    assert await counts(linked.redis, fresh) == _DELETED
    assert await linked.redis.get(keys[1]) is None


@pytest.mark.asyncio
async def test_quota_carryover_identity_and_email_snapshots_take_the_larger(
    linked: Linked,
) -> None:
    """A sign-in whose identity and address each have a snapshot from a different deleted
    account (the Google account's address changed in between) starts from the larger of
    each counter, never their sum, and drops both."""
    google_sub = await _deleted_account(linked, "google", _address("gmail.com"), _MORE)
    email = _address()
    apple_sub = await _deleted_account(linked, "apple", email, _DELETED)
    identity_key = quota_carryover.carry_key(linked.settings, "google", google_sub)
    email_key = _keys(linked, "apple", apple_sub, email)[1]

    fresh, _ = await signed_in(linked, "google", google_sub, email)
    assert await counts(linked.redis, fresh) == {"usage": 5000, "imggen": 2, "tavily": 4}
    assert await quota.live_talk_used_seconds(linked.redis, fresh) == _LIVE_TALK_SECONDS
    assert await linked.redis.get(identity_key) is None
    assert await linked.redis.get(email_key) is None
