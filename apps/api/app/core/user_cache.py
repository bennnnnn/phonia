"""This process's copies of recently loaded users, checked against a generation in Redis.

Every authenticated request and every chat turn needs the user row, and Neon is a
round trip or more away, so the last loaded row stays here. Each request reads the
user's current generation in the same MGET as its token check
(``core/access_tokens.check_access``), and a copy is used only under the generation
it was loaded at.

Whoever commits a write to a user row awaits ``publish_change`` right after, which
stores a new generation: ``users_repo.update`` does for its own commits, a caller
that commits itself does after its commit, and so does the history scan's stamp.
So a plan change from the RevenueCat webhook, a settings, memory or preferences
change, or consent saved on any machine applies to the next request and the next
chat turn on every machine. ``memory_edited_at`` is read only from the row itself
(background jobs), so a hand edit's stamp does not publish.

A publish Redis refuses (after retries) fails the request with 503, though its
write is saved: while Redis is down every request is refused anyway, and the
write's retry (the client's, RevenueCat's redelivery, a job's) publishes again.
Until then, once Redis is back, a copy can lag that write by at most the TTL.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import make_transient_to_detached

from app.core.cache_generation import bump_generation
from app.core.redis import get_redis_client
from app.core.ttl_cache import TtlCache
from app.exceptions import RedisUnavailableError
from app.models.orm import User

logger = logging.getLogger(__name__)

USER_CACHE_TTL_SECONDS = 300.0
# A publish rides out a Redis blip this many times before the request fails, waiting
# a moment more each time. Inside the request, so not the job retry policy (core/jobs).
_PUBLISH_ATTEMPTS = 3
_PUBLISH_PAUSE_SECONDS = 0.1
# Users seen on one process within the TTL; far above normal traffic.
_USER_CACHE_MAX_ENTRIES = 5_000
_GENERATION_PREFIX = "usergen:"
_user_cache: TtlCache[UUID, tuple[User, str]] = TtlCache(
    ttl_seconds=USER_CACHE_TTL_SECONDS,
    max_entries=_USER_CACHE_MAX_ENTRIES,
)


def generation_key(user_id: UUID) -> str:
    return f"{_GENERATION_PREFIX}{user_id}"


def _snapshot(user: User) -> User:
    """Detached copy safe to merge into a later request session."""
    state = sa_inspect(user)
    # In-memory dict only. getattr on an expired column lazy-loads and raises
    # MissingGreenlet from an async session.
    values = {key: state.dict[key] for key in state.mapper.columns.keys() if key in state.dict}
    snap = User(**values)
    make_transient_to_detached(snap)
    return snap


def cached_user(user_id: UUID, generation: str) -> User | None:
    """A private copy of the row loaded under ``generation`` (the current one), or None."""
    hit = _user_cache.get(user_id)
    if hit is None or hit[1] != generation:
        return None
    user = hit[0]
    return _snapshot(user) if isinstance(user, User) else user


def remember_user(user: User, generation: str) -> None:
    """Keep ``user`` as read under ``generation``, read before the row was."""
    cached = _snapshot(user) if isinstance(user, User) else user
    _user_cache.put(user.id, (cached, generation))


async def publish_change(user_id: UUID) -> str:
    """After a committed write to the user's row: drop this copy, give every machine a
    new generation, and return it (a row read from now on may be kept under it).

    Retried; raises ``RedisUnavailableError`` (503) when Redis never takes it.
    """
    forget_user(user_id)
    key = generation_key(user_id)
    for attempt in range(1, _PUBLISH_ATTEMPTS):
        try:
            return await bump_generation(get_redis_client(), key)
        except RedisError:
            logger.warning("User generation bump failed; retrying user_id=%s", user_id)
            await asyncio.sleep(_PUBLISH_PAUSE_SECONDS * attempt)
    try:
        return await bump_generation(get_redis_client(), key)
    except RedisError as exc:
        logger.error(
            "User change saved but not published; other machines keep their copy until "
            "it is repeated or expires user_id=%s",
            user_id,
            exc_info=True,
        )
        raise RedisUnavailableError() from exc


def forget_user(user_id: UUID) -> None:
    _user_cache.pop(user_id)


def clear() -> None:
    """Drop every entry (tests)."""
    _user_cache.clear()


def size() -> int:
    return len(_user_cache)
