"""A deleted account's limits are filed under its email only on an address a provider owns.

The email key (``quota_carryover``) let a quota be handed to a stranger: a Google account
can be verified on an address Google does not own (a stale work address, a lapsed domain,
``email_authority``). Its holder signs up with it, uses up the day and the live talk month,
deletes the account, and whoever signs up on that address next started at those counts.
Account delete now files the email key only for an address a provider owns by its domain,
on ``email_authority``'s rules: Google's Gmail, Apple's iCloud, me.com, mac.com and relay.
Those are never given to anyone else, so it is filed whichever provider signed in (an Apple
ID on a Gmail address is common, and deleting it then signing in with Google must not start
a fresh day). A Workspace address (owned through the token's ``hd``, which the row does not
keep) cannot be decided at delete, so it gets no email key. The identity keys are unchanged.

Real Postgres and the configured Redis (``real_redis``), through the HTTP sign-in and
delete routes.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.modules.account import quota_carryover
from app.services import quota

from .carry_world import Linked, counts, delete, deleted_account, signed_in, use

_DELETED = {"usage": 1234, "imggen": 2, "tavily": 4}
_LIVE_TALK_SECONDS = 300


def _address(domain: str) -> str:
    return f"owner-{uuid4().hex[:12]}@{domain}"


def _email_key(world: Linked, email: str) -> str:
    key = quota_carryover.email_carry_key(world.settings, email)
    assert key is not None
    return key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deleted", "domain", "claims", "later"),
    [
        # A Google account on a company domain that is not its Workspace (no ``hd``).
        ("google", "example.org", {}, "google"),
        # An Apple ID on a company address: no provider owns it.
        ("apple", "example.org", {}, "google"),
        # Google owns a Workspace address through the token's ``hd``, which the account
        # row does not keep: the delete cannot tell, so it keeps no email key.
        ("google", "acme-carry.example", {"hd": "acme-carry.example"}, "apple"),
    ],
)
async def test_quota_carryover_email_unowned_address_starts_the_next_sign_up_fresh(
    linked: Linked, deleted: str, domain: str, claims: dict[str, Any], later: str
) -> None:
    """Delete an account on an address no provider owns (or can be shown at delete to own): only the identity key is kept, and a later sign-up on that address with
    another login starts from zero. Before, it started at the deleted account's counts."""
    email = _address(domain)
    deleted_sub = await deleted_account(
        linked, deleted, email, _DELETED, live_talk=_LIVE_TALK_SECONDS, claims=claims
    )
    assert await linked.redis.get(_email_key(linked, email)) is None
    identity_key = quota_carryover.carry_key(linked.settings, deleted, deleted_sub)
    assert await linked.redis.get(identity_key) is not None

    fresh, _ = await signed_in(linked, later, f"{later}-{uuid4()}", email)
    assert await counts(linked.redis, fresh) == {}
    assert await quota.live_talk_used_seconds(linked.redis, fresh) == 0
    # The deleted login itself still carries its own day (its identity key is unchanged).
    again, _ = await signed_in(linked, deleted, deleted_sub, _address("gmail.com"), claims)
    assert await counts(linked.redis, again) == _DELETED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deleted", "domain"),
    [
        ("google", "gmail.com"),
        ("apple", "icloud.com"),
        # The other provider's address: an Apple ID on Gmail, a Google account on iCloud.
        # Deleting it and signing in with the other provider must not start a fresh day.
        ("apple", "gmail.com"),
        ("google", "icloud.com"),
    ],
)
async def test_quota_carryover_email_owned_address_carries_to_a_new_login(
    linked: Linked, deleted: str, domain: str
) -> None:
    """Deleted on a Gmail or iCloud address, whichever provider it signed in with, the
    account files the email key, and a new login on that address starts at its counts."""
    email = _address(domain)
    await deleted_account(linked, deleted, email, _DELETED, live_talk=_LIVE_TALK_SECONDS)
    email_key = _email_key(linked, email)
    assert await linked.redis.get(email_key) is not None

    later = "apple" if deleted == "google" else "google"
    fresh, _ = await signed_in(linked, later, f"{later}-{uuid4()}", email)
    assert await counts(linked.redis, fresh) == _DELETED
    assert await quota.live_talk_used_seconds(linked.redis, fresh) == _LIVE_TALK_SECONDS
    assert await linked.redis.get(email_key) is None


@pytest.mark.asyncio
async def test_quota_carryover_email_both_logins_store_it_when_either_owns(
    linked: Linked,
) -> None:
    """A Google account on an iCloud address that Apple then joins (Apple owns iCloud)
    holds both logins; Apple owning the address is enough to file the email key."""
    email = _address("icloud.com")
    user_id, _ = await signed_in(linked, "google", f"google-{uuid4()}", email)
    joined, token = await signed_in(linked, "apple", f"apple-{uuid4()}", email)
    assert joined == user_id
    await use(linked.redis, user_id, _DELETED, live_talk=_LIVE_TALK_SECONDS)
    await delete(linked, user_id, token)
    assert await linked.redis.get(_email_key(linked, email)) is not None

    fresh, _ = await signed_in(linked, "apple", f"apple-{uuid4()}", email)
    assert await counts(linked.redis, fresh) == _DELETED


@pytest.mark.asyncio
async def test_quota_carryover_email_both_logins_on_a_workspace_address_store_none(
    linked: Linked,
) -> None:
    """An Apple account on a company address that a Workspace Google login (``hd``) then
    joins: Google owned it at that sign-in, but the delete has no token to tell, and Apple
    never owns it, so no email key is filed."""
    domain = "acme-both.example"
    email = _address(domain)
    user_id, _ = await signed_in(linked, "apple", f"apple-{uuid4()}", email)
    joined, token = await signed_in(linked, "google", f"google-{uuid4()}", email, {"hd": domain})
    assert joined == user_id
    await use(linked.redis, user_id, _DELETED)
    await delete(linked, user_id, token)
    assert await linked.redis.get(_email_key(linked, email)) is None


@pytest.mark.parametrize(
    ("email", "owned"),
    [
        ("x@gmail.com", True),
        (" X@GoogleMail.COM ", True),
        ("x@icloud.com", True),
        ("x@me.com", True),
        ("x@mac.com", True),
        ("abc@privaterelay.appleid.com", True),
        ("x@acme.example", False),
        ("x@gmail.com.evil.example", False),
        ("", False),
        (None, False),
        ("not-an-address", False),
    ],
)
def test_quota_carryover_address_owned_by_a_provider(email: str | None, owned: bool) -> None:
    assert quota_carryover.address_owned_by_a_provider(email) is owned
