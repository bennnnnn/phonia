"""What happens to an entry that did not finish: a later attempt, or a wait for its handler."""

import logging
import time
import traceback
from typing import Any

from redis.asyncio import Redis

from app.core.jobs.admin import _move_to_dlq
from app.core.jobs.dedupe import _release_dedupe
from app.core.jobs.delayed import MAX_ATTEMPTS, attempt_of, schedule, schedule_retry

logger = logging.getLogger("app.core.jobs")

# An entry for a type no handler here knows waits this long between looks, and is
# dead-lettered once it has waited this long in all (a deploy finishes well before).
_UNKNOWN_TYPE_RECHECK_S = 600.0
_UNKNOWN_TYPE_MAX_WAIT_S = 86_400.0
_UNKNOWN_SINCE_FIELD = "unknown_since"


async def retry_later(
    redis: Redis, entry_id: str, fields: dict[str, Any], dedupe_key: str | None
) -> None:
    """Give the claim back and schedule the next attempt, or dead-letter the last one."""
    attempt = attempt_of(fields)
    await _release_dedupe(redis, dedupe_key)
    try:
        next_attempt = await schedule_retry(redis, _string_fields(fields))
    except Exception:
        logger.exception("Job id=%s could not be scheduled for retry; moving to DLQ", entry_id)
        next_attempt = None
    if next_attempt is None:
        logger.exception(
            "Job failed after %s attempts id=%s type=%s", attempt, entry_id, fields.get("type")
        )
        await _move_to_dlq(redis, entry_id, fields, traceback.format_exc(limit=8))
        return
    logger.warning(
        "Job failed attempt=%s/%s id=%s type=%s; retrying later",
        attempt,
        MAX_ATTEMPTS,
        entry_id,
        fields.get("type"),
        exc_info=True,
    )


async def hold_unknown_type(
    redis: Redis, entry_id: str, fields: dict[str, Any], dedupe_key: str | None, error: str
) -> None:
    """Keep an entry of a type this worker cannot run for the release that can.

    During a blue-green deploy the old worker reads job types the new release added,
    and after a rollback the restored worker reads every such entry already queued.
    Dead-lettering them lost that work unless someone replayed the queue by hand.
    """
    await _release_dedupe(redis, dedupe_key)
    now = time.time()
    try:
        since = float(fields.get(_UNKNOWN_SINCE_FIELD) or now)
    except (TypeError, ValueError):
        since = now
    if now - since >= _UNKNOWN_TYPE_MAX_WAIT_S:
        logger.error("Job id=%s still has no handler after a day; moving to DLQ", entry_id)
        await _move_to_dlq(redis, entry_id, fields, error)
        return
    logger.warning("Job id=%s has no handler in this worker (%s); holding it", entry_id, error)
    held = {**_string_fields(fields), _UNKNOWN_SINCE_FIELD: str(since)}
    await schedule(redis, held, delay_s=_UNKNOWN_TYPE_RECHECK_S, now=now)


def _string_fields(fields: dict[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in fields.items()}
