"""Guard a scan read-back: per-user limits, payload limits, the vision spend cap.

Math, physics and chemistry each read a cropped photo back for the student to
confirm. They run the same checks before their reader and record the same
spend after it, so a subject adds a reader here, not a copy of the guard.
Every read also shares one deadline (``scan_read_deadline_seconds``), which
the reader spreads over its own steps.

The per-user checks (reads open at once, the hourly rate, the day's chat
tokens) run before the body is read: a photo is megabytes in memory, and
several at once from one account pushed a machine toward its memory limit.
A read has no daily count of its own: it takes ``scan_read_tokens`` from the
chat's daily allowance, and once that is spent it is refused as a chat turn is
(``quota_exceeded``).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, status
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.image_signatures import sniff_image_type
from app.core.in_flight import InFlightBusyError, in_flight_slot
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.exceptions import DomainError
from app.models.orm import User
from app.models.schemas.scan import SCAN_MAX_IMAGE_BYTES, SCAN_MAX_REQUEST_BYTES, ScanPhotoIn
from app.services import quota as quota_service

logger = logging.getLogger(__name__)

SCAN_RATE_LIMIT_MESSAGE = "Too many scans in a row. Try again in a few minutes."
SCAN_BUSY_MESSAGE = "Still reading your last photo. Try again in a moment."
SCAN_SPEND_CAP_MESSAGE = "Reading photos is paused for now. Type the problem, or try again later."
# One budget for every subject: the limit is how many photos a student has read
# an hour, so switching subject must not grant a fresh allowance.
SCAN_RATE_LIMIT_KEY = "scan_read_rl"
SCAN_IN_FLIGHT_KEY = "scan_read_inflight"
# The chat's own code for a spent daily allowance: a scan shares that allowance.
QUOTA_EXCEEDED_CODE = "quota_exceeded"
# An open read older than this can no longer be running (the deadline is 20 s,
# plus the upload), so its slot ages out after a crash.
_IN_FLIGHT_TTL_MARGIN_SECONDS = 40
# What the readers accept (``ScanPhotoIn.content_type``). HEIC is not among them:
# the phone sends JPEG, and the readers are not sent HEIC.
_SCAN_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class ScanRefusedError(DomainError):
    """A photo read refused before the reader runs; the phone keys its words on the code."""


@dataclass(frozen=True, slots=True)
class ScanPhoto:
    content_type: str
    data: bytes


def _too_large() -> ScanRefusedError:
    return ScanRefusedError(
        "Image too large", status_code=status.HTTP_413_CONTENT_TOO_LARGE, code="image_too_large"
    )


async def scan_photo(request: Request) -> ScanPhoto:
    """The decoded photo. 413 when it is too large, 400 when it is not a photo."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > SCAN_MAX_REQUEST_BYTES:
        raise _too_large()
    raw = await request.body()
    if len(raw) > SCAN_MAX_REQUEST_BYTES:
        raise _too_large()
    try:
        payload = ScanPhotoIn.model_validate(json.loads(raw))
        data = base64.b64decode(payload.image_base64, validate=True)
    except (ValueError, ValidationError, binascii.Error) as exc:
        raise ScanRefusedError(
            "Invalid image payload", status_code=status.HTTP_400_BAD_REQUEST, code="invalid_image"
        ) from exc
    if not data:
        raise ScanRefusedError(
            "Empty image", status_code=status.HTTP_400_BAD_REQUEST, code="invalid_image"
        )
    if len(data) > SCAN_MAX_IMAGE_BYTES:
        raise _too_large()
    # Forwarded, never decoded here: check it is a photo before a paid reader sees it.
    # The bytes name the type; a mislabelled photo is sent as what it is.
    detected = sniff_image_type(data)
    if detected not in _SCAN_IMAGE_TYPES:
        raise ScanRefusedError(
            "Not a photo", status_code=status.HTTP_400_BAD_REQUEST, code="invalid_image"
        )
    return ScanPhoto(content_type=detected, data=data)


async def _check_hourly_rate(redis: Redis, user: User, settings: Settings) -> None:
    limit = settings.scan_read_rate_limit_per_hour
    if limit > 0 and not await allow_request_unless_down(
        redis, f"{SCAN_RATE_LIMIT_KEY}:{user.id}", limit=limit, window_seconds=3600
    ):
        raise ScanRefusedError(
            SCAN_RATE_LIMIT_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="scan_rate_limited",
        )


async def _reserve_tokens(redis: Redis, user: User, settings: Settings) -> int:
    """Take the read's tokens from the day's chat allowance, or what is left of it (as a
    chat turn near the limit does); refused as a chat turn is once none is left."""
    reserved = await quota_service.reserve_usage_up_to(
        redis,
        str(user.id),
        settings.scan_read_tokens,
        daily_limit=quota_service.daily_limit_for_user(user, settings),
    )
    if reserved <= 0:
        raise ScanRefusedError(
            quota_service.quota_exceeded_message(user),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code=QUOTA_EXCEEDED_CODE,
        )
    return reserved


async def _checked_photo(request: Request, redis: Redis, settings: Settings) -> ScanPhoto:
    photo = await scan_photo(request)
    if await quota_service.global_spend_exceeded(redis, settings):
        raise ScanRefusedError(
            SCAN_SPEND_CAP_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="scan_spend_cap",
        )
    return photo


async def read_scan[T](
    request: Request,
    *,
    user: User,
    settings: Settings,
    subject: str,
    read: Callable[[ScanPhoto, float], Awaitable[T]],
) -> T | None:
    """``read(photo, seconds_left)`` once every guard passes; None when it failed.

    ``seconds_left`` is what remains of the deadline for the reader to share
    among its steps; the read is cut off when the deadline passes. A failed or
    late read is logged, never a 500: the scanner then offers to send the
    photo itself. The spend is recorded either way, because the provider was
    called, and the read's tokens stay charged; a refusal before the reader
    gives them back.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.scan_read_deadline_seconds
    redis = get_redis_client()
    try:
        async with in_flight_slot(
            redis,
            f"{SCAN_IN_FLIGHT_KEY}:{user.id}",
            limit=settings.scan_read_max_in_flight,
            ttl_seconds=int(settings.scan_read_deadline_seconds) + _IN_FLIGHT_TTL_MARGIN_SECONDS,
        ):
            await _check_hourly_rate(redis, user, settings)
            reserved = await _reserve_tokens(redis, user, settings)
            try:
                photo = await _checked_photo(request, redis, settings)
            except BaseException:
                await quota_service.refund_usage(redis, str(user.id), reserved)
                raise
            return await _run_reader(read, photo, subject, settings, redis, deadline)
    except InFlightBusyError:
        raise ScanRefusedError(
            SCAN_BUSY_MESSAGE, status_code=status.HTTP_429_TOO_MANY_REQUESTS, code="scan_busy"
        ) from None


async def _run_reader[T](
    read: Callable[[ScanPhoto, float], Awaitable[T]],
    photo: ScanPhoto,
    subject: str,
    settings: Settings,
    redis: Redis,
    deadline: float,
) -> T | None:
    loop = asyncio.get_running_loop()
    try:
        async with asyncio.timeout_at(deadline):
            return await read(photo, max(0.0, deadline - loop.time()))
    except TimeoutError:
        logger.warning("%s scan read ran past %ss", subject, settings.scan_read_deadline_seconds)
        return None
    except Exception:
        logger.warning("%s scan read failed", subject, exc_info=True)
        return None
    finally:
        try:
            await quota_service.record_global_spend(redis, quota_service.MATH_SCAN_READ_SPEND_USD)
        except Exception:
            logger.exception("record_global_spend failed after a %s scan read", subject)
