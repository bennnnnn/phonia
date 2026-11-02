"""A sign-in identity linked to an existing account by email brings its carried counters.

Account delete keeps the day's counters per sign-in identity (``quota_carryover``), and a
new account for that identity is raised to them. An identity can also come back by joining
an account that already holds its email (``service.login_with_*``, ``email_authority``):
delete an Apple account, sign in with Google on the same address, then with Apple. That
link applied nothing, so the deleted account's day started again from zero.

The deleted account's snapshot here is filed under its identity alone, as a delete made
before the email key was (``quota_carryover``); with the email key, the other provider's
new account already starts from it (``test_quota_carryover_email.py``).

Real Postgres and the configured Redis (``real_redis``), through the HTTP sign-in routes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.modules.account import quota_carryover
from app.services import quota

from .carry_world import Linked, counts, delete, linked_sub, signed_in, use
from .carry_world import sign_in as _sign_in

# The deleted account's day, and the account it comes back to: each counter either side
# used more of, plus counters only one side used.
_DELETED = {"usage": 1234, "imggen": 2, "tavily": 4}
_LIVE_TALK_SECONDS = 300
_SURVIVOR = {"usage": 5000, "tavily": 1}
# Raise-only on each counter (``carryover.apply_carried_usage``): the larger of the two.
_MERGED = {"usage": 5000, "imggen": 2, "tavily": 4}
_EMAILS = {"apple": "icloud.com", "google": "gmail.com"}  # where that provider owns the address


async def _deleted_then_other_account(world: Linked, deleted: str) -> tuple[str, str, UUID]:
    """An account made with *deleted*'s provider uses its day and is deleted; the same
    address then gets an account through the other provider, which uses some of its own.
    Returns the deleted identity's sub, the address, and the surviving account."""
    other = "google" if deleted == "apple" else "apple"
    sub, email = f"{deleted}-{uuid4()}", f"link-{uuid4().hex[:12]}@{_EMAILS[deleted]}"
    first, token = await signed_in(world, deleted, sub, email)
    await use(world.redis, first, _DELETED, live_talk=_LIVE_TALK_SECONDS)
    await delete(world, first, token)
    assert await world.redis.get(quota_carryover.carry_key(world.settings, deleted, sub))
    # Filed under the identity alone, as before the email key.
    by_email = quota_carryover.email_carry_key(world.settings, email)
    assert by_email is not None and await world.redis.delete(by_email) == 1

    survivor, _ = await signed_in(world, other, f"{other}-{uuid4()}", email)
    assert survivor != first
    await use(world.redis, survivor, _SURVIVOR)
    assert await counts(world.redis, survivor) == _SURVIVOR
    return sub, email, survivor


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted", ["apple", "google"])
async def test_quota_carryover_linked_identity_raises_the_account_once(
    linked: Linked, deleted: str
) -> None:
    sub, email, survivor = await _deleted_then_other_account(linked, deleted)
    applied = AsyncMock(wraps=quota.apply_carried_usage)

    with patch("app.services.quota.apply_carried_usage", applied):
        joined, _ = await signed_in(linked, deleted, sub, email)
        assert joined == survivor
        assert await linked_sub(survivor, deleted) == sub
        assert await counts(linked.redis, survivor) == _MERGED
        assert await quota.live_talk_used_seconds(linked.redis, survivor) == _LIVE_TALK_SECONDS
        # Used: the snapshot is gone.
        assert (
            await linked.redis.get(quota_carryover.carry_key(linked.settings, deleted, sub)) is None
        )

        # The next sign-in finds the identity on the account and applies nothing again.
        again, _ = await signed_in(linked, deleted, sub, email)
        assert again == survivor
    assert applied.await_count == 1
    assert await counts(linked.redis, survivor) == _MERGED


@pytest.mark.asyncio
async def test_quota_carryover_unrestored_link_refuses_sign_in_and_links_nothing(
    linked: Linked,
) -> None:
    """A link whose carried counters cannot be applied is not saved, as with a new account:
    503 ``sign_in_unavailable``, the identity not on the account, the snapshot kept, and the
    retry links and restores."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    sub, email, survivor = await _deleted_then_other_account(linked, "apple")
    key = quota_carryover.carry_key(linked.settings, "apple", sub)
    snapshot = await linked.redis.get(key)

    down = AsyncMock(side_effect=RedisConnectionError("Error 111 connecting to redis"))
    with patch("app.services.quota.apply_carried_usage", down):
        refused = await _sign_in(linked, "apple", sub, email)

    assert refused.status_code == 503, refused.text
    assert refused.json()["detail"]["code"] == "sign_in_unavailable"
    assert await linked_sub(survivor, "apple") is None
    assert await linked.redis.get(key) == snapshot
    assert await counts(linked.redis, survivor) == _SURVIVOR

    joined, _ = await signed_in(linked, "apple", sub, email)
    assert joined == survivor
    assert await counts(linked.redis, survivor) == _MERGED
    assert await linked.redis.get(key) is None
