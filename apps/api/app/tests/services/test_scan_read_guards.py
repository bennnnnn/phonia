"""A scan read-back's per-user limits run before its body is read, and refund what they took."""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.core.config import Settings
from app.exceptions import RedisUnavailableError
from app.models.schemas.scan import SCAN_MAX_IMAGE_BYTES
from app.services import scan_read
from app.services.quota import counters
from app.tests.fakes import make_user

JPEG = b"\xff\xd8\xff\xe0 fake jpeg"
PNG = b"\x89PNG\r\n\x1a\n fake png"


def _user(plan: str = "free") -> Any:
    return make_user(plan=plan)


def _request(data: bytes = JPEG, content_type: str = "image/jpeg") -> MagicMock:
    body = json.dumps(
        {"image_base64": base64.b64encode(data).decode(), "content_type": content_type}
    ).encode()
    request = MagicMock()
    request.headers = {}
    request.body = AsyncMock(return_value=body)
    return request


async def _read(
    redis: Any,
    user: Any,
    request: MagicMock,
    *,
    reader: AsyncMock | None = None,
    settings: Settings | None = None,
) -> Any:
    with patch.object(scan_read, "get_redis_client", return_value=redis):
        return await scan_read.read_scan(
            request,
            user=user,
            settings=settings or Settings(),
            subject="math",
            read=reader or AsyncMock(return_value="2x = 4"),
        )


def _redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _used_today(redis: Any, user: Any) -> int:
    value = await redis.get(counters.daily_key("scanread", user.id))
    return int(value or 0)


@pytest.mark.parametrize("plan, expected", [("free", 20), ("plus", 200), ("pro", 200)])
def test_scan_reads_have_a_daily_allowance_per_plan(plan: str, expected: int) -> None:
    assert counters.limit("scan_read", _user(plan), Settings()) == expected


@pytest.mark.asyncio
async def test_a_read_that_ran_keeps_its_daily_slot_and_frees_its_open_slot() -> None:
    redis, user = _redis(), _user()
    reader = AsyncMock(side_effect=RuntimeError("provider down"))
    assert await _read(redis, user, _request(), reader=reader) is None
    reader.assert_awaited_once()
    assert await _used_today(redis, user) == 1
    assert await redis.zcard(f"{scan_read.SCAN_IN_FLIGHT_KEY}:{user.id}") == 0


@pytest.mark.asyncio
async def test_at_the_daily_cap_the_body_is_never_read() -> None:
    redis, user = _redis(), _user()
    cap = counters.limit("scan_read", user, Settings())
    await redis.set(counters.daily_key("scanread", user.id), cap, ex=60)
    request = _request()
    reader = AsyncMock()
    with pytest.raises(scan_read.ScanRefusedError) as refused:
        await _read(redis, user, request, reader=reader)
    assert refused.value.status_code == 429
    assert refused.value.code == "daily_limit"
    assert refused.value.fields == {"feature": "scan_read"}
    request.body.assert_not_awaited()
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_too_many_open_reads_is_refused_before_the_body_or_any_count() -> None:
    redis, user = _redis(), _user()
    key = f"{scan_read.SCAN_IN_FLIGHT_KEY}:{user.id}"
    await redis.zadd(key, {"a": time.time(), "b": time.time()})
    request = _request()
    with (
        patch.object(scan_read, "allow_request_unless_down", AsyncMock()) as rate,
        pytest.raises(scan_read.ScanRefusedError) as refused,
    ):
        await _read(redis, user, request)
    assert refused.value.code == "scan_busy"
    assert refused.value.status_code == 429
    request.body.assert_not_awaited()
    rate.assert_not_awaited()
    assert await _used_today(redis, user) == 0
    assert await redis.zcard(key) == 2  # the refused request left no entry behind


@pytest.mark.asyncio
async def test_an_open_read_left_by_a_crash_ages_out() -> None:
    redis, user = _redis(), _user()
    key = f"{scan_read.SCAN_IN_FLIGHT_KEY}:{user.id}"
    stale = time.time() - 600
    await redis.zadd(key, {"a": stale, "b": stale})
    assert await _read(redis, user, _request()) == "2x = 4"


@pytest.mark.asyncio
async def test_over_the_hourly_rate_the_body_is_never_read() -> None:
    redis, user = _redis(), _user()
    request = _request()
    with (
        patch.object(scan_read, "allow_request_unless_down", AsyncMock(return_value=False)),
        pytest.raises(scan_read.ScanRefusedError) as refused,
    ):
        await _read(redis, user, request)
    assert refused.value.code == "scan_rate_limited"
    request.body.assert_not_awaited()
    assert await _used_today(redis, user) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data, code",
    [
        (b"%PDF-1.7 not a photo", "invalid_image"),
        (b"GIF89a not for the reader", "invalid_image"),
        (b"\x00\x00\x00\x18ftypheic heic", "invalid_image"),
        (b"#!/bin/sh\necho hi", "invalid_image"),
        (b"\xff" * (SCAN_MAX_IMAGE_BYTES + 1), "image_too_large"),
    ],
)
async def test_a_refused_photo_gives_its_daily_read_back(data: bytes, code: str) -> None:
    redis, user = _redis(), _user()
    reader = AsyncMock()
    with pytest.raises(scan_read.ScanRefusedError) as refused:
        await _read(redis, user, _request(data), reader=reader)
    assert refused.value.code == code
    reader.assert_not_awaited()
    assert await _used_today(redis, user) == 0


@pytest.mark.asyncio
async def test_the_spend_cap_gives_the_daily_read_back() -> None:
    redis, user = _redis(), _user()
    with (
        patch.object(
            scan_read.quota_service, "global_spend_exceeded", AsyncMock(return_value=True)
        ),
        pytest.raises(scan_read.ScanRefusedError) as refused,
    ):
        await _read(redis, user, _request())
    assert refused.value.code == "scan_spend_cap"
    assert await _used_today(redis, user) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data, claimed, sent",
    [
        (JPEG, "image/jpeg", "image/jpeg"),
        (PNG, "image/png", "image/png"),
        (JPEG, "image/png", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/jpeg", "image/webp"),
    ],
)
async def test_the_reader_gets_the_type_the_bytes_show(
    data: bytes, claimed: str, sent: str
) -> None:
    reader = AsyncMock(return_value="ok")
    await _read(_redis(), _user(), _request(data, claimed), reader=reader)
    assert reader.await_args is not None
    photo = reader.await_args.args[0]
    assert photo.content_type == sent
    assert photo.data == data


@pytest.mark.asyncio
async def test_a_redis_outage_refuses_the_scan_as_unavailable() -> None:
    redis = MagicMock()
    redis.pipeline.side_effect = ConnectionError("down")
    request = _request()
    with pytest.raises(RedisUnavailableError):
        await _read(redis, _user(), request)
    request.body.assert_not_awaited()
