"""The model reader in shadow: it reads a STEM question beside the patterns.

With ``model_reader_shadow_enabled`` on, a share (``model_reader_shadow_rate``) of the turns
the subject read calls maths, physics or chemistry, with no instant reply, start
``model_reader``'s read of the message. Nothing awaits it: the turn's trace line
(``turn_trace``) says ``pending`` while it reads, and it logs its own ``turn_model_read``
line when it finishes, bounded by its calls' own timeouts. It skips at the day's spend cap
(docs/MODEL_READER.md). The read never reaches the reply.
"""

from __future__ import annotations

import asyncio
import logging
import random

from redis.asyncio import Redis

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.modules.chat.turn_trace import current_turn_trace
from app.modules.model_reader.service import read_with_model
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

_SUBJECTS = frozenset({"math", "physics", "chemistry"})


def start_model_read_shadow(
    text: str, settings: Settings, redis: Redis, *, subject: str | None
) -> None:
    """Start the shadow read of ``text`` for the current turn, once; never raises."""
    if not settings.model_reader_shadow_enabled or subject not in _SUBJECTS:
        return
    if random.random() >= settings.model_reader_shadow_rate:  # noqa: S311 - a sample, not a secret
        return
    trace = current_turn_trace()
    if trace is None or trace.emitted or trace.model_read_task is not None:
        return

    async def read() -> None:
        try:
            if await quota_service.global_spend_exceeded(redis, settings):
                logger.info("model read skipped: global spend cap")
                return
        except RedisUnavailableError:
            logger.info("model read skipped: global spend unreadable (Redis down)")
            return
        # Bounded on its own: its calls and the maths read, never longer.
        async with asyncio.timeout(3 * settings.model_reader_timeout_seconds + 2):
            trace.model_read = await read_with_model(text, settings)

    trace.model_read_task = asyncio.create_task(read())
