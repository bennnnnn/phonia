"""Carry today's limits from a deleted account to the next one for the same person.

Quota counters are keyed by user id, so deleting an account and signing in
again with the same Google or Apple login, or with the other provider on the
same email address (a Gmail or iCloud one), would otherwise start
every daily cap, and this month's live talk minutes, from zero.

Account delete stores what the account had used under one Redis key per sign-in
identity, ``quota_carry:<HMAC-SHA256(jwt_secret, "quota-carry:google:<sub>")>``, and
one for the account's email, ``quota_carry:<HMAC-SHA256(jwt_secret,
"quota-carry-email:<address>")>``: never the raw provider subject, never the address,
never the user id (so the account's Redis sweep, which deletes every key naming the
user id, leaves them). Each holds the same counts and expires when the UTC month ends.
The email key closed a gap: delete an Apple account on x@icloud.com, sign in with
Google on the same address, and the new account's day started again from zero, its
snapshot filed only under the Apple id.

The email key is stored only for an address a sign-in provider owns by its domain
(``address_owned_by_a_provider``, on ``email_authority``'s rules): Google's ``@gmail.com``
and ``@googlemail.com``, Apple's iCloud, ``me.com``, ``mac.com`` and its relay. Those
addresses are never given to someone else, so whoever verified one holds it, whichever
provider they signed in with (an Apple ID on a Gmail address is common). Any other
address was only verified by a provider, which does not prove the person still has it
(a stale work address, a lapsed domain): with an email key there, someone could use up
the address's day and live talk month, delete the account, and whoever signs up on it
next would start at those counts. A Google Workspace address is owned by Google only
when the sign-in token's ``hd`` claim names its domain; the account row keeps no token,
so a delete cannot tell, and stores no email key for it. An account with no email, or
with any other address, stores only its identity keys.

The address is trimmed and lower-cased before it is hashed (``normalised_email``) and
nothing else: no provider's own rules (Gmail's dots or ``+tags``), which would merge
addresses that are different mailboxes elsewhere.

When sign-in creates a new user, or links an identity to the existing account that
holds its email (``service._link_identity``), that account's counters are raised to
the identity's snapshot and the email's (each raise-only, so applying both leaves each
counter at the larger of the two, never summed), and every key applied is deleted.

Both sides fail closed. A delete whose counters cannot be stored is refused with
``RedisUnavailableError`` (503 ``unavailable``), before anything is undone, and the phone
asks for a retry. A new account or link whose snapshots cannot be read or applied is
not saved: sign-in answers 503 ``sign_in_unavailable`` and its retry restores. Both were
best-effort, so Redis failing at either step started the same sign-in from zero.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.models.orm import User
from app.modules.account.email_authority import apple_owns_email, google_owns_email
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

CARRY_KEY_PREFIX = "quota_carry:"
# The snapshot only matters until the UTC month ends (live talk is monthly).
_MAX_TTL_SECONDS = 35 * 24 * 60 * 60


def _hashed(settings: Settings, message: str) -> str:
    digest = hmac.new(settings.jwt_secret.encode(), message.encode(), hashlib.sha256)
    return f"{CARRY_KEY_PREFIX}{digest.hexdigest()}"


def carry_key(settings: Settings, provider: str, sub: str) -> str:
    return _hashed(settings, f"quota-carry:{provider}:{sub}")


def normalised_email(email: str | None) -> str:
    """The address as the email key reads it: trimmed and lower-cased, nothing more."""
    return (email or "").strip().lower()


def email_carry_key(settings: Settings, email: str | None) -> str | None:
    """The email's snapshot key, or None for an account without one."""
    address = normalised_email(email)
    return _hashed(settings, f"quota-carry-email:{address}") if address else None


def address_owned_by_a_provider(email: str | None) -> bool:
    """Google or Apple owns ``email`` by its domain (Gmail; iCloud, me.com, mac.com, relay).

    Decided from the address alone, with no token claims: a delete has no sign-in token,
    so a Google Workspace address (owned only when the token's ``hd`` names its domain)
    is not counted, and Apple's relay addresses count by their domain.
    """
    address = email or ""
    no_claims: dict[str, object] = {}
    return google_owns_email(no_claims, address) or apple_owns_email(no_claims, address)


def _identities(user: User) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for provider, sub in (("google", user.google_sub), ("apple", user.apple_sub)):
        if isinstance(sub, str) and sub.strip():
            found.append((provider, sub))
    return found


def _ttl_seconds(now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    left = (quota_service.next_month_start(current) - current).total_seconds()
    return max(1, min(_MAX_TTL_SECONDS, math.ceil(left)))


async def save_on_delete(redis: Redis, settings: Settings, user: User) -> None:
    """Keep the account's used counters for its sign-in identities, and for its email
    when a provider owns the address by its domain (``address_owned_by_a_provider``).

    Raises ``RedisUnavailableError`` when they cannot be read or stored: the delete is
    refused rather than lose them (``lifecycle.delete_account`` calls this first).
    """
    keys = [carry_key(settings, provider, sub) for provider, sub in _identities(user)]
    if address_owned_by_a_provider(user.email):
        by_email = email_carry_key(settings, user.email)
        if by_email is not None:
            keys.append(by_email)
    if not keys:
        return
    try:
        carried = await quota_service.read_carried_usage(redis, user.id)
        if carried.is_empty():
            return
        payload = carried.model_dump_json()
        ttl = _ttl_seconds()
        for key in keys:
            await redis.set(key, payload, ex=ttl)
    except (RedisError, OSError) as exc:
        logger.warning("Quota carry-over save failed user_id=%s", user.id, exc_info=True)
        raise RedisUnavailableError() from exc


async def restore_for_new_account(
    redis: Redis,
    settings: Settings,
    user_id: UUID,
    *,
    provider: str,
    sub: str,
    email: str | None,
) -> list[str]:
    """Raise the counters of an account that just gained this identity (made for it, or
    linked to it by email), not yet committed, to the identity's snapshot and the email's.
    Raise-only: each counter ends at the larger value, so applying both is safe.

    Returns the snapshot keys found, for ``drop_restored`` once the account commits; empty
    when there are none: one MGET, the common case. Raises ``RedisUnavailableError`` when a
    snapshot cannot be read or applied, so sign-in refuses and saves neither account nor
    link (the next sign-in would find the identity and never restore). The snapshots stay
    for the retry.
    """
    keys = [carry_key(settings, provider, sub)]
    by_email = email_carry_key(settings, email)
    if by_email is not None:
        keys.append(by_email)
    found: list[str] = []
    try:
        for key, raw in zip(keys, await redis.mget(keys), strict=True):
            if raw is None:
                continue
            found.append(key)
            try:
                carried = quota_service.CarriedUsage.model_validate_json(raw)
            except ValidationError:
                logger.warning("Quota carry-over snapshot unreadable; dropped")
            else:
                await quota_service.apply_carried_usage(redis, user_id, carried)
    except (RedisError, OSError) as exc:
        logger.warning("Quota carry-over restore failed user_id=%s", user_id, exc_info=True)
        raise RedisUnavailableError() from exc
    return found


async def drop_restored(redis: Redis, keys: Sequence[str]) -> None:
    """Delete the snapshots a committed account took. Best effort, never raises: the
    counters are raised already, and a snapshot left over only raises a later account's
    counters (raise-only, never lowered) until it expires with the month."""
    if not keys:
        return
    try:
        await redis.delete(*keys)
    except Exception:
        logger.warning("Quota carry-over snapshot not dropped; it expires", exc_info=True)
