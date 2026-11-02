"""Redis keys for a user's memory blocks, and dropping them when memory changes."""

import hashlib
import logging
from uuid import UUID

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


async def invalidate_memory_block(user_id: UUID) -> None:
    """Bump the query generation and drop every scoped block-cache key."""
    try:
        redis = get_redis_client()
        await bump_generation(redis, memory_generation_key(user_id))
        block_key = memory_block_key(user_id)
        await redis.delete(
            block_key,
            f"{block_key}:x",
            f"{block_key}:w",
            f"{block_key}:wx",
        )
    except Exception:
        logger.debug("Memory block cache invalidation failed", exc_info=True)
