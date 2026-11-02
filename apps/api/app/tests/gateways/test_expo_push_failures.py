"""What a failed Expo push request tells the cycle: go again next minute, or hold."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.gateways import expo_push_gateway as gateway
from app.gateways.expo_push_gateway import HoldReason, PushHold

_REQUEST = httpx.Request("POST", gateway.EXPO_PUSH_URL)


def _ok(messages: list[dict[str, Any]]) -> httpx.Response:
    data = [{"status": "ok", "id": f"ticket-{m['to']}"} for m in messages]
    return httpx.Response(200, json={"data": data}, request=_REQUEST)


async def _send(post: Any, count: int = 3) -> gateway.PushSendResult:
    client = AsyncMock()
    client.post = AsyncMock(side_effect=post)
    messages = [{"to": f"ExponentPushToken[{i}]"} for i in range(count)]
    with patch("app.gateways.expo_push_gateway.get_pooled_client", return_value=client):
        return await gateway.send_push_messages(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "hold"),
    [
        (httpx.ConnectError("refused"), None),  # never reached Expo: next cycle
        (httpx.ConnectTimeout("slow"), None),
        (httpx.PoolTimeout("busy"), None),
        (httpx.ReadTimeout("sent, no answer"), PushHold(HoldReason.AMBIGUOUS)),
        (httpx.RemoteProtocolError("dropped"), PushHold(HoldReason.AMBIGUOUS)),
    ],
)
async def test_a_request_that_may_have_reached_expo_is_held(
    failure: Exception, hold: PushHold | None
) -> None:
    async def post(*_a: Any, **_kw: Any) -> httpx.Response:
        raise failure

    result = await _send(post)
    assert result.delivered == [False] * 3
    assert result.holds == [hold] * 3


@pytest.mark.asyncio
async def test_an_unreadable_answer_is_held_as_maybe_accepted() -> None:
    async def post(*_a: Any, **_kw: Any) -> httpx.Response:
        return httpx.Response(200, content=b"<html>", request=_REQUEST)

    result = await _send(post)
    assert result.holds == [PushHold(HoldReason.AMBIGUOUS)] * 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "headers", "hold"),
    [
        (429, {"Retry-After": "90"}, PushHold(HoldReason.THROTTLED, 90.0)),
        (429, {}, PushHold(HoldReason.THROTTLED)),
        (503, {"Retry-After": "30"}, PushHold(HoldReason.SERVER, 30.0)),
        (500, {}, PushHold(HoldReason.SERVER)),
        (401, {}, PushHold(HoldReason.SERVER)),
    ],
)
async def test_a_throttled_or_failed_request_is_held(
    status: int, headers: dict[str, str], hold: PushHold
) -> None:
    async def post(*_a: Any, **_kw: Any) -> httpx.Response:
        return httpx.Response(status, headers=headers, request=_REQUEST)

    result = await _send(post)
    assert result.holds == [hold] * 3


@pytest.mark.asyncio
async def test_a_refused_request_is_split_until_the_bad_message_is_alone() -> None:
    """A 400 for the whole request (one bad token, or tokens of two projects) failed the
    same 100 reminders every minute for two days."""
    bad = "ExponentPushToken[2]"
    sizes: list[int] = []

    async def post(_url: str, json: list[dict[str, Any]], headers: Any) -> httpx.Response:
        sizes.append(len(json))
        if any(m["to"] == bad for m in json):
            return httpx.Response(400, json={"errors": [{"code": "BAD"}]}, request=_REQUEST)
        return _ok(json)

    result = await _send(post, count=5)
    assert result.delivered == [True, True, False, True, True]
    assert result.holds == [None, None, PushHold(HoldReason.REJECTED), None, None]
    assert sizes == [5, 2, 3, 1, 2]  # the good halves go whole
    assert [ticket for ticket, _ in result.receipt_tickets] == [
        f"ticket-ExponentPushToken[{i}]" for i in (0, 1, 3, 4)
    ]
