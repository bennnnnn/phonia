"""JWT access + refresh lifecycle with Redis rotation and revocation.

Rotated-out refresh tokens are tombstoned. Reuse revokes the user's refresh
sessions and older access tokens. This strict policy also rejects a retry
when a successful rotation's response was lost.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID, uuid4

import jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_tokens import create_access_token
from app.core.access_tokens import redis_str as _redis_str
from app.core.access_tokens import revoked_key as _revoked_key
from app.core.access_tokens import revoked_session_key as _revoked_session_key
from app.core.access_tokens import revoked_since_key as _revoked_since_key
from app.core.access_tokens import verify_access_token as verify_access_token
from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.models.schemas import UserOut
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

_REFRESH_PREFIX = "refresh:"
_REFRESH_TOMBSTONE_PREFIX = "refresh_used:"
_USER_REFRESH_SET_PREFIX = "refresh_user:"

# How long a rotated-out refresh token is remembered as "already used" —
# long enough to catch a delayed reuse attempt (e.g. an attacker replaying a
# stolen token after the legitimate device already rotated it), short enough
# to bound Redis growth. Independent of the refresh token's own TTL.
_REUSE_DETECTION_WINDOW_SECONDS = 24 * 60 * 60
_MAX_SESSION_TRANSACTION_ATTEMPTS = 3


def _refresh_key(token: str) -> str:
    return f"{_REFRESH_PREFIX}{token}"


def _tombstone_key(token: str) -> str:
    return f"{_REFRESH_TOMBSTONE_PREFIX}{token}"


def _user_refresh_set_key(user_id: UUID) -> str:
    return f"{_USER_REFRESH_SET_PREFIX}{user_id}"


def parse_refresh_record(raw: str | bytes) -> dict[str, Any] | None:
    """The stored session, or None for a record this release never writes.

    Every record has carried ``user_id`` and ``session_id`` since 2026-09-11 and lives
    ``jwt_refresh_expire_days``; anything else is refused, and that device signs in again.
    """
    try:
        data = json.loads(_redis_str(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return None
    try:
        UUID(str(data.get("user_id")))
    except ValueError:
        return None
    return data


def _refresh_payload(
    user_id: UUID,
    session_id: str,
    *,
    created_at: str,
    last_seen_at: str,
    device_label: str | None,
    platform: str | None,
) -> str:
    return json.dumps(
        {
            "user_id": str(user_id),
            "session_id": session_id,
            "created_at": created_at,
            "last_seen_at": last_seen_at,
            "device_label": device_label,
            "platform": platform,
        }
    )


def session_id_from_access_token(token: str, settings: Settings) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    sid = payload.get("sid")
    return str(sid) if isinstance(sid, str) and sid else None


async def issue_token_pair(
    redis: Redis,
    user_id: UUID,
    settings: Settings,
    *,
    device_label: str | None = None,
    platform: str | None = None,
) -> tuple[str, str]:
    session_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    access_token = create_access_token(user_id, settings, session_id=session_id)
    refresh_token = secrets.token_urlsafe(32)
    ttl = settings.jwt_refresh_expire_days * 86_400
    user_set_key = _user_refresh_set_key(user_id)
    payload = _refresh_payload(
        user_id,
        session_id,
        created_at=now,
        last_seen_at=now,
        device_label=device_label,
        platform=platform,
    )
    try:
        await _drop_expired_sessions(redis, user_set_key)
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(_refresh_key(refresh_token), payload, ex=ttl)
            pipe.sadd(user_set_key, refresh_token)
            pipe.expire(user_set_key, ttl)
            await pipe.execute()
    except RedisError as exc:
        logger.warning("Token issue failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
    return access_token, refresh_token


async def _drop_expired_sessions(redis: Redis, user_set_key: str) -> None:
    """Remove set members whose refresh token has expired on its own.

    Logout, revoke and rotation remove their member; a token that just runs
    out its TTL did not, and each sign-in renews the set's TTL, so the set
    grew for as long as the user kept signing in.
    """
    members = [_redis_str(member) for member in await redis.smembers(user_set_key)]
    if not members:
        return
    async with redis.pipeline(transaction=False) as pipe:
        for token in members:
            pipe.exists(_refresh_key(token))
        live = await pipe.execute()
    expired = [token for token, exists in zip(members, live, strict=True) if not exists]
    if expired:
        await redis.srem(user_set_key, *expired)


async def _revoke_all_refresh_tokens(redis: Redis, user_id: UUID, settings: Settings) -> None:
    """Revoke the complete live set atomically, including concurrent rotations."""
    user_set_key = _user_refresh_set_key(user_id)
    async with redis.pipeline(transaction=True) as pipe:
        for _ in range(_MAX_SESSION_TRANSACTION_ATTEMPTS):
            try:
                await pipe.watch(user_set_key)
                live_tokens = await pipe.smembers(user_set_key)
                pipe.multi()
                if live_tokens:
                    pipe.delete(*[_refresh_key(_redis_str(t)) for t in live_tokens])
                pipe.delete(user_set_key)
                pipe.set(
                    _revoked_since_key(user_id),
                    datetime.now(UTC).timestamp(),
                    ex=max(60, settings.jwt_expire_minutes * 60),
                )
                await pipe.execute()
                return
            except WatchError:
                # A new login or rotation changed the live set. Include it in
                # the next snapshot instead of leaving an untracked session.
                continue
    raise RedisUnavailableError()


async def purge_user_sessions(redis: Redis, user_id: UUID, settings: Settings) -> None:
    """Revoke every refresh token + outstanding access token for a user.

    Used on account deletion — without this, a logged-in client keeps a
    working access token after `DELETE /auth/me` and can still hit endpoints
    until the token's own exp (the DB user check is the only remaining gate).

    M1: Redis failures are NOT swallowed — if we can't purge sessions, the
    delete fails (503) so the client knows to retry. Silently succeeding
    leaves live sessions that can call the API until JWT expiry.
    """
    try:
        await _revoke_all_refresh_tokens(redis, user_id, settings)
    except RedisError as exc:
        logger.warning("Session purge failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc


async def _reject_invalid_refresh(redis: Redis, refresh_token: str, settings: Settings) -> NoReturn:
    tombstoned = await redis.get(_tombstone_key(refresh_token))
    if tombstoned is not None:
        user_id = UUID(_redis_str(tombstoned))
        logger.warning(
            "Refresh token reuse detected for user_id=%s — revoking all sessions", user_id
        )
        await _revoke_all_refresh_tokens(redis, user_id, settings)
    raise AuthenticationError("Invalid refresh token")


async def refresh_token_pair(
    redis: Redis,
    refresh_token: str,
    session: AsyncSession,
    settings: Settings,
    *,
    device_label: str | None = None,
    platform: str | None = None,
) -> tuple[str, str, UserOut]:
    try:
        key = _refresh_key(refresh_token)
        user_id_raw = await redis.get(key)
        if user_id_raw is None:
            await _reject_invalid_refresh(redis, refresh_token, settings)
        record = parse_refresh_record(user_id_raw)
        if record is None:
            await revoke_refresh_token(redis, refresh_token)
            raise AuthenticationError("Invalid refresh token")
        user_id = UUID(str(record["user_id"]))

        # Finish fallible DB reads / response validation before consuming the
        # credential. A transient failure must leave it available for retry.
        user = await users_repo.get_by_id(session, user_id)
        if user is None:
            await revoke_refresh_token(redis, refresh_token)
            raise AuthenticationError("User not found")
        user_out = UserOut.model_validate(user)
        session_id = str(record["session_id"])
        created_raw = record.get("created_at")
        created_at = created_raw if isinstance(created_raw, str) else datetime.now(UTC).isoformat()
        now = datetime.now(UTC).isoformat()
        existing_label = (
            record.get("device_label") if isinstance(record.get("device_label"), str) else None
        )
        existing_platform = (
            record.get("platform") if isinstance(record.get("platform"), str) else None
        )
        access_token = create_access_token(user_id, settings, session_id=session_id)
        new_refresh = secrets.token_urlsafe(32)
        ttl = settings.jwt_refresh_expire_days * 86_400
        user_set_key = _user_refresh_set_key(user_id)
        payload = _refresh_payload(
            user_id,
            session_id,
            created_at=created_at,
            last_seen_at=now,
            device_label=device_label or existing_label,
            platform=platform or existing_platform,
        )
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                if await pipe.get(key) != user_id_raw:
                    await _reject_invalid_refresh(redis, refresh_token, settings)
                pipe.multi()
                pipe.delete(key)
                pipe.set(
                    _tombstone_key(refresh_token),
                    str(user_id),
                    ex=_REUSE_DETECTION_WINDOW_SECONDS,
                )
                pipe.srem(user_set_key, refresh_token)
                pipe.set(_refresh_key(new_refresh), payload, ex=ttl)
                pipe.sadd(user_set_key, new_refresh)
                pipe.expire(user_set_key, ttl)
                await pipe.execute()
            except WatchError as exc:
                if await redis.get(key) == user_id_raw:
                    # Redis also reports lost WATCH connections as WatchError.
                    # The credential is still live: let the client retry it.
                    raise RedisUnavailableError() from exc
                # Logout/purge or another refresh won. Never recreate a session
                # that disappeared while the DB lookup or transaction ran.
                await _reject_invalid_refresh(redis, refresh_token, settings)
    except RedisError as exc:
        logger.warning("Refresh token Redis op failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
    return access_token, new_refresh, user_out


async def refresh_token_user(redis: Redis, refresh_token: str) -> UUID | None:
    """The account a live refresh token belongs to, read without using the token up."""
    try:
        raw = await redis.get(_refresh_key(refresh_token))
    except RedisError as exc:
        raise RedisUnavailableError() from exc
    record = parse_refresh_record(raw) if raw is not None else None
    return UUID(str(record["user_id"])) if record is not None else None


async def revoke_access_token(redis: Redis, access_token: str, settings: Settings) -> None:
    try:
        payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = max(1, int(exp - datetime.now(UTC).timestamp()))
    try:
        await redis.set(_revoked_key(str(jti)), "1", ex=ttl)
    except RedisError as exc:
        logger.warning("Access token revoke failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc


async def revoke_refresh_token(redis: Redis, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    try:
        async with redis.pipeline(transaction=True) as pipe:
            for _ in range(_MAX_SESSION_TRANSACTION_ATTEMPTS):
                try:
                    key = _refresh_key(refresh_token)
                    await pipe.watch(key)
                    user_id_raw = await pipe.get(key)
                    pipe.multi()
                    pipe.delete(key)
                    record = parse_refresh_record(user_id_raw) if user_id_raw is not None else None
                    if record is not None:
                        user_id = UUID(str(record["user_id"]))
                        pipe.srem(_user_refresh_set_key(user_id), refresh_token)
                    await pipe.execute()
                    return
                except WatchError:
                    continue
        raise RedisUnavailableError()
    except RedisError as exc:
        logger.warning("Refresh token revoke failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc


class SessionNotFoundError(AuthenticationError):
    """The requested refresh session is not in the live set."""


class CurrentSessionError(AuthenticationError):
    """Caller tried to revoke the session they are currently using."""


async def list_sessions(
    redis: Redis,
    user_id: UUID,
    *,
    current_session_id: str | None,
) -> list[dict[str, Any]]:
    user_set_key = _user_refresh_set_key(user_id)
    try:
        tokens = await redis.smembers(user_set_key)
    except RedisError as exc:
        logger.warning("Session list failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
    refresh_tokens = [_redis_str(raw_token) for raw_token in tokens]
    # One MGET for every session, not a GET each.
    records = (
        await redis.mget([_refresh_key(token) for token in refresh_tokens])
        if refresh_tokens
        else []
    )
    sessions: list[dict[str, Any]] = []
    for refresh_token, raw in zip(refresh_tokens, records, strict=True):
        record = parse_refresh_record(raw) if raw is not None else None
        if record is None:
            continue
        session_id = str(record["session_id"])
        sessions.append(
            {
                "id": session_id,
                "device_label": record.get("device_label")
                if isinstance(record.get("device_label"), str)
                else None,
                "platform": record.get("platform")
                if isinstance(record.get("platform"), str)
                else None,
                "created_at": record.get("created_at")
                if isinstance(record.get("created_at"), str)
                else None,
                "last_seen_at": record.get("last_seen_at")
                if isinstance(record.get("last_seen_at"), str)
                else None,
                "current": bool(current_session_id) and session_id == current_session_id,
                "_refresh_token": refresh_token,
            }
        )
    sessions.sort(key=lambda item: item.get("last_seen_at") or "", reverse=True)
    return sessions


async def revoke_session(
    redis: Redis,
    user_id: UUID,
    session_id: str,
    *,
    current_session_id: str | None,
    settings: Settings,
) -> None:
    """Sign one other device out: its refresh token and its live access token.

    Deleting only the refresh token left that device signed in until its
    access token expired (up to ``jwt_expire_minutes``). Access tokens carry
    the session id (``sid``), so the session is revoked by id for as long as
    any of its access tokens can still be valid.
    """
    if current_session_id and session_id == current_session_id:
        raise CurrentSessionError("Cannot revoke the current session")
    if not await end_session(redis, user_id, session_id, settings=settings):
        raise SessionNotFoundError("Session not found")


async def end_session(redis: Redis, user_id: UUID, session_id: str, *, settings: Settings) -> bool:
    """End one session: its access tokens by id, and its refresh token. Whether it was live.

    Signing out without the refresh token (the phone could not read it) ends this session
    by its access token's id; it used to end every session on every device.
    """
    sessions = await list_sessions(redis, user_id, current_session_id=None)
    match = next((item for item in sessions if item["id"] == session_id), None)
    try:
        await redis.set(
            _revoked_session_key(session_id),
            "1",
            ex=max(60, settings.jwt_expire_minutes * 60),
        )
    except RedisError as exc:
        logger.warning("Session revoke failed; Redis unavailable", exc_info=True)
        raise RedisUnavailableError() from exc
    if match is None:
        return False
    await revoke_refresh_token(redis, str(match["_refresh_token"]))
    return True
