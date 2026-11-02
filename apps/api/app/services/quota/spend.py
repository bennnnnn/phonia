"""Global UTC-day spend kill-switch: what each call adds, and what the cap stops.

The counter itself is ``core/spend_counter.py``. Chat turns add catalog price
x tokens at finalize, and every other model call (memory, titles, follow-ups,
OCR, embeddings, classifiers) is priced by the gateway that makes it
(``gateways/llm_spend.py``). The prices below are for calls without a token
count: images, photo lookup, scan reads, voice and live talk.
"""

import logging
import math
from datetime import date

from redis.asyncio import Redis

from app.core.spend_counter import (
    MICRO_USD_PER_USD,
    get_global_spend_micro_usd,
    global_spend_exceeded,
    record_global_spend,
    spend_key,
)
from app.services.quota.counters import refund_daily

logger = logging.getLogger(__name__)

__all__ = [
    "IMAGE_GEN_SPEND_USD",
    "IMAGE_SEARCH_SPEND_USD",
    "LIVE_TALK_SPEND_USD_PER_MINUTE",
    "MATH_SCAN_READ_SPEND_USD",
    "STT_SPEND_USD",
    "TTS_SPEND_USD",
    "get_global_spend_micro_usd",
    "global_spend_exceeded",
    "live_talk_spend_usd",
    "record_global_spend",
    "record_voice_spend",
    "release_global_spend",
]

IMAGE_GEN_SPEND_USD = 0.03
# Tavily image search + one SSRF-safe fetch (cheaper than image-gen, still billed).
IMAGE_SEARCH_SPEND_USD = 0.01
# One scan read-back's Mathpix call. A vision read of the page is priced by
# the gateway on top, so this stays the old all-in estimate (conservative).
MATH_SCAN_READ_SPEND_USD = 0.005
STT_SPEND_USD = 0.01
TTS_SPEND_USD = 0.015
# An upper estimate of one minute of gpt-realtime conversation: audio both
# ways plus the context each reply re-reads. Live talk is priced by time, not
# by saved turn: the phone posts the turns, so a count of them is the client's.
LIVE_TALK_SPEND_USD_PER_MINUTE = 0.20


async def release_global_spend(redis: Redis, usd: float, *, day: date) -> None:
    """Give back spend recorded on *day* that never happened, never below 0.

    Rounds down, so a release never exceeds what ``record_global_spend``
    rounded up.
    """
    amount = math.floor(round(usd * MICRO_USD_PER_USD, 6))
    if amount > 0:
        await refund_daily(redis, spend_key(day), amount=amount)


def live_talk_spend_usd(seconds: int) -> float:
    return max(0, seconds) * LIVE_TALK_SPEND_USD_PER_MINUTE / 60


async def record_voice_spend(redis: Redis, usd: float) -> None:
    """Best-effort: voice cost must not fail the user path if Redis is unhappy."""
    try:
        await record_global_spend(redis, usd)
    except Exception:
        logger.exception("record_voice_spend failed")
