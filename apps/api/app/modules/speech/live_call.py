"""The OpenAI call behind a live talk session, which the server ends itself.

The phone used to post its WebRTC offer straight to OpenAI with the client secret, and
the server never learned the call: ``/live/end`` charged the time that had passed and
gave the rest back, but nothing ended the call, and the secret carried no session cap.
A modified client could report the end at once and keep talking until OpenAI's own
limit, on minutes it had been refunded.

Now the client secret never leaves the server. The mint keeps it (``keep_client_secret``),
the phone sends its offer here (``connect``), and the server posts it with the secret,
returns OpenAI's answer and keeps the call's id from the answer's Location header. The
server hangs the call up itself (``end_call``): on ``/live/end``, and when the session's
reserved minutes run out, by a delayed ``live_talk_hangup`` job scheduled at connect.
The unused minutes come back only once OpenAI has confirmed the call is over; until
then the session keeps its whole reservation, and the job tries again.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import status
from redis.asyncio import Redis

from app.core import jobs
from app.core.config import Settings
from app.core.redis import get_redis_client
from app.gateways import openai_speech_gateway
from app.modules.speech import live_talk as live_talk_service
from app.modules.speech.gates import SpeechRefusedError
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

HANGUP_JOB = "live_talk_hangup"
# The expiry hang-up runs this long after the reservation ends (the worker moves due
# jobs every few seconds).
_HANGUP_GRACE_SECONDS = 5
# The phone connects right after the mint (it gathers ICE meanwhile): an unused secret
# is dropped after this, or with the session if that is shorter.
_SECRET_TTL_SECONDS = 120
# A held call id outlives the session's reservation by the grace /live/end has to settle.
_CALL_ID_TAIL_SECONDS = 15 * 60


class LiveCallUnconfirmedError(Exception):
    """OpenAI did not confirm the hang-up; the job retries (``core/jobs`` backoff)."""


def _secret_key(user_id: UUID, session_id: str) -> str:
    return f"livetalk_secret:{user_id}:{session_id}"


def _call_key(user_id: UUID, session_id: str) -> str:
    return f"livetalk_call:{user_id}:{session_id}"


def _ended() -> SpeechRefusedError:
    # Its own code: the phone ends the call in its words, never this English.
    return SpeechRefusedError(
        "Realtime session is not active",
        status_code=status.HTTP_403_FORBIDDEN,
        code="live_talk_session_ended",
    )


def _text(raw: Any) -> str:
    return raw.decode() if isinstance(raw, bytes | bytearray) else str(raw)


async def keep_client_secret(
    redis: Redis, user_id: UUID, session_id: str, secret: str, *, reserved_seconds: int
) -> None:
    """Hold a minted session's secret for its one ``connect``."""
    ttl = max(1, min(_SECRET_TTL_SECONDS, reserved_seconds))
    await redis.set(_secret_key(user_id, session_id), secret, ex=ttl)


async def connect(
    redis: Redis, settings: Settings, user_id: UUID, session_id: str, offer_sdp: str
) -> str:
    """Open the session's OpenAI call with the phone's offer; returns OpenAI's answer.

    One connect per session: the secret is taken as it is used. The call's id is kept
    for ``end_call`` and its hang-up is scheduled for when the reservation runs out. A
    session that ended meanwhile (``/live/end`` raced the connect) has its new call hung
    up at once.
    """
    session_id = session_id.strip()
    raw_secret = await redis.getdel(_secret_key(user_id, session_id))
    left = await quota_service.live_talk_seconds_left(redis, user_id, session_id)
    if raw_secret is None or not left:
        raise _ended()
    call = await openai_speech_gateway.create_realtime_call(
        settings, client_secret=_text(raw_secret), offer_sdp=offer_sdp
    )
    if call is None:
        raise SpeechRefusedError(
            "Could not start realtime voice", status_code=status.HTTP_502_BAD_GATEWAY
        )
    # Kept before the checks below, so an end that runs from here on finds the call.
    await redis.set(_call_key(user_id, session_id), call.call_id, ex=left + _CALL_ID_TAIL_SECONDS)
    await schedule_hangup(redis, user_id, session_id, delay_s=left + _HANGUP_GRACE_SECONDS)
    left = await quota_service.live_talk_seconds_left(redis, user_id, session_id)
    if not left or "v=0" not in call.answer_sdp:
        if not await end_call(redis, settings, user_id, session_id):
            await schedule_hangup(redis, user_id, session_id, delay_s=0)
        if not left:
            raise _ended()
        raise SpeechRefusedError(
            "Could not start realtime voice", status_code=status.HTTP_502_BAD_GATEWAY
        )
    return call.answer_sdp


async def end_call(redis: Redis, settings: Settings, user_id: UUID, session_id: str) -> bool:
    """Hang up the session's call. True when nothing of it can still run: no call was
    opened (none can be now), or OpenAI confirmed it is over."""
    session_id = session_id.strip()
    # A connect still to come finds no secret and opens nothing.
    await redis.delete(_secret_key(user_id, session_id))
    raw = await redis.get(_call_key(user_id, session_id))
    if raw is None:
        return True
    outcome = await openai_speech_gateway.hangup_realtime_call(settings, _text(raw))
    if outcome == "failed":
        return False
    await redis.delete(_call_key(user_id, session_id))
    return True


async def schedule_hangup(redis: Redis, user_id: UUID, session_id: str, *, delay_s: float) -> None:
    """Have the worker hang the session's call up (and settle it) after ``delay_s``."""
    await jobs.enqueue_later(
        redis,
        HANGUP_JOB,
        {"user_id": str(user_id), "session_id": session_id},
        delay_s=max(0.0, delay_s),
    )


async def finish_session(redis: Redis, settings: Settings, user_id: UUID, session_id: str) -> bool:
    """End the call and settle the minutes; False while the hang-up is unconfirmed.

    Settling charges the time since the mint (all of it once the reservation has run
    out) and gives the rest back; saving keeps only its short tail. An unconfirmed
    hang-up settles nothing: the session stays charged its whole reservation.
    """
    if not await end_call(redis, settings, user_id, session_id):
        return False
    charged = await quota_service.settle_live_talk_session(redis, user_id, session_id)
    if charged is not None:
        await live_talk_service.close_realtime_session(redis, user_id, session_id)
    return True


async def handle_hangup_job(settings: Settings, payload: dict[str, Any]) -> None:
    """``live_talk_hangup``: at the reservation's end, or after ``/live/end`` could not
    confirm a hang-up. Raises while OpenAI does not confirm, so the queue retries."""
    try:
        user_id = UUID(str(payload.get("user_id")))
    except ValueError:
        logger.warning("live_talk_hangup invalid user_id=%r", payload.get("user_id"))
        return
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return
    if not await finish_session(get_redis_client(), settings, user_id, session_id):
        raise LiveCallUnconfirmedError(session_id)
