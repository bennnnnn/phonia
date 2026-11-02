"""Redis keys for a user's memory blocks, and dropping them when memory changes.

Every block is tied to the memory generation read before its facts were: the
query blocks fold it into their key, and the question-free blocks
(``memblock:{user}``, ``:w``, ``:x``) store it in front of the text. A memory
write that commits after a turn read its facts bumps the generation, so the
block that turn stores afterwards is never served, even though its SET came
after the write's invalidation.
"""

import hashlib
import logging
from uuid import UUID

from redis.asyncio import Redis

from app.core.cache_generation import bump_generation
from app.core.config import Settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


def memory_query_cache_key(user_id: UUID, generation: bytes | str | None, query_text: str) -> str:
    digest = hashlib.sha256(query_text.strip().lower().encode()).hexdigest()[:32]
    if generation is None:
        gen_tag = "0"
    elif isinstance(generation, bytes):
        gen_tag = generation.decode()
    else:
        gen_tag = generation
    return f"memquery:{user_id}:{gen_tag}:{digest}"


def memory_query_scoped_key(
    user_id: UUID,
    generation: bytes | str | None,
    query_text: str,
    *,
    exclude_sensitive: bool,
    with_profile: bool = False,
) -> str:
    sens = "x" if exclude_sensitive else "a"
    profile = "p" if with_profile else ""
    return f"{memory_query_cache_key(user_id, generation, query_text)}:{sens}{profile}"


def memory_block_key(user_id: UUID) -> str:
    return f"memblock:{user_id}"


def memory_generation_key(user_id: UUID) -> str:
    return f"memgen:{user_id}"


async def write_query_block_cache(cache_key: str, block: str, settings: Settings) -> None:
    try:
        await get_redis_client().set(
            cache_key,
            block,
            ex=max(30, settings.memory_query_cache_ttl),
        )
    except Exception:
        logger.debug("Memory query cache write failed", exc_info=True)


def _generation_tag(generation: bytes | str | None) -> str:
    if generation is None:
        return "0"
    return generation.decode() if isinstance(generation, bytes) else generation


async def read_block_cache(redis: Redis, user_id: UUID, cache_key: str) -> tuple[str | None, str]:
    """The cached block if it was stored under the current generation, and that generation.

    One MGET reads both. The caller stores what it builds under the generation
    returned here, read before its facts, never one read after.
    """
    generation, stored = await redis.mget(memory_generation_key(user_id), cache_key)
    tag = _generation_tag(generation)
    if stored is None:
        return None, tag
    raw = stored.decode() if isinstance(stored, bytes) else str(stored)
    stored_tag, sep, block = raw.partition("\n")
    # An entry written before blocks carried their generation has none: a miss.
    if not sep or stored_tag != tag:
        return None, tag
    return block, tag


async def write_block_cache(
    redis: Redis, cache_key: str, generation_tag: str, block: str, ttl_seconds: int
) -> None:
    await redis.set(cache_key, f"{generation_tag}\n{block}", ex=ttl_seconds)


_INVALIDATE_ATTEMPTS = 2


async def invalidate_memory_block(user_id: UUID) -> None:
    """Bump the query generation and drop every scoped block-cache key.

    Tried twice: a failure leaves a "forget X" injectable until the blocks
    expire (``memory_cache_ttl``), so it is logged at warning, not hidden.
    """
    block_key = memory_block_key(user_id)
    for attempt in range(1, _INVALIDATE_ATTEMPTS + 1):
        try:
            redis = get_redis_client()
            await bump_generation(redis, memory_generation_key(user_id))
            await redis.delete(
                block_key,
                f"{block_key}:x",
                f"{block_key}:w",
                f"{block_key}:wx",
            )
            return
        except Exception as exc:
            if attempt == _INVALIDATE_ATTEMPTS:
                logger.warning(
                    "Memory cache invalidation failed for user_id=%s; cached blocks "
                    "may be served until they expire: %r",
                    user_id,
                    exc,
                )
