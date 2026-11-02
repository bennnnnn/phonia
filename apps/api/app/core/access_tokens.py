"""App JWT access tokens: create, decode, and the per-request revocation check.

Every authenticated request verifies its token here (``app.core.deps``). The
account module issues, rotates and revokes sessions, and writes the revocation
keys this module reads. Not Google OAuth. The same round trip reads the user
row's generation, which says whether this process's copy of the row is current
(``core/user_cache``).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core import user_cache
from app.core.cache_generation import ensure_generation
from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError

logger = logging.getLogger(__name__)

REVOKED_PREFIX = "revoked:jti:"
REVOKED_SESSION_PREFIX = "revoked:sid:"
REVOKED_SINCE_PREFIX = "revoked_since:"


def redis_str(value: str | bytes) -> str:
    """Normalize a Redis reply that may be bytes or str (decode_responses varies)."""
    return value.decode() if isinstance(value, bytes) else value


def revoked_key(jti: str) -> str:
    return f"{REVOKED_PREFIX}{jti}"


def revoked_session_key(session_id: str) -> str:
    """One signed-in device (the ``sid`` claim), revoked from another device."""
    return f"{REVOKED_SESSION_PREFIX}{session_id}"


def revoked_since_key(user_id: UUID) -> str:
    return f"{REVOKED_SINCE_PREFIX}{user_id}"


class AccessTokenError(Exception):
    """Raised when an access JWT is missing, malformed, or otherwise invalid."""


def create_access_token(user_id: UUID, settings: Settings, *, session_id: str | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "exp": expire,
        # Keep subsecond precision so a fresh sign-in after session revocation
        # in the same second is newer than the Redis revocation cutoff.
        "iat": now.timestamp(),
        "jti": secrets.token_urlsafe(16),
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AccessTokenError("Invalid access token") from exc


def _revocation_keys(payload: dict[str, Any], user_id: UUID) -> tuple[list[str], str | None]:
    """The keys that revoke this token when set, and its user's revoked-since cutoff key.

    A token without a ``jti``, ``sid`` or ``iat`` claim has nothing of that kind to check.
    """
    markers: list[str] = []
    jti = payload.get("jti")
    if jti:
        markers.append(revoked_key(str(jti)))
    sid = payload.get("sid")
    if isinstance(sid, str) and sid:
        markers.append(revoked_session_key(sid))
    since = revoked_since_key(user_id) if payload.get("iat") is not None else None
    return markers, since


def _issued_before(issued_at: object, revoked_since_raw: str | bytes | None) -> bool:
    """Whether a token issued at ``issued_at`` predates the account's revocation cutoff."""
    if not isinstance(issued_at, int | float) or revoked_since_raw is None:
        return False
    return float(issued_at) <= float(redis_str(revoked_since_raw))


@dataclass(frozen=True)
class AccessCheck:
    """A live token's user, and that user row's current generation (``core/user_cache``)."""

    user_id: UUID
    user_generation: str


async def check_access(redis: Redis, token: str, settings: Settings) -> AccessCheck:
    """The token's user once no revocation names it, with the user row's generation.

    Every revocation key (this token, its signed-in device, the user's cutoff)
    and the generation are read in one MGET: this runs before every
    authenticated request and every chat frame, so it is one Redis round trip.
    A user whose generation key is missing (never set, expired or lost) gets a
    fresh one first, one more round trip (``ensure_generation``).
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise AuthenticationError("Invalid access token") from exc
    try:
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AuthenticationError("Invalid access token") from exc
    markers, since = _revocation_keys(payload, user_id)
    generation_key = user_cache.generation_key(user_id)
    keys = [*markers, generation_key, *([since] if since else [])]
    try:
        values = await redis.mget(keys)
        if any(values[: len(markers)]):
            raise AuthenticationError("Token revoked")
        if _issued_before(payload.get("iat"), values[-1] if since else None):
            raise AuthenticationError("Token revoked")
        generation = values[len(markers)]
        if generation is None:
            generation = await ensure_generation(redis, generation_key)
    except RedisError as exc:
        # Fail closed: without Redis we cannot check jti / revoked_since.
        # Surface as 503 (not 401) so clients retry instead of forcing re-login.
        logger.warning("Access token revocation check failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
    return AccessCheck(user_id=user_id, user_generation=redis_str(generation))


async def verify_access_token(redis: Redis, token: str, settings: Settings) -> UUID:
    """The token's user once no revocation names it (``check_access`` without the row)."""
    return (await check_access(redis, token, settings)).user_id
