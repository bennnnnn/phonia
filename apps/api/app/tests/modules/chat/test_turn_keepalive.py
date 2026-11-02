"""A quiet turn carries keepalives on both transports (code-health audit NET-17).

The phone gives up on a stream after 45 s with nothing; a slow turn (tool calls, a
provider that thinks) sends a keepalive every so often, so only a dead connection
is ever taken for one.
"""

import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.modules.chat.stream_api as stream_api
import app.modules.chat.ws_turn as ws_turn
from app.modules.chat.turn_outcome import TurnOutcome


@pytest.mark.asyncio
async def test_a_quiet_sse_turn_sends_keepalives_between_its_events(monkeypatch):
    monkeypatch.setattr(stream_api, "TURN_KEEPALIVE_SECONDS", 0.02)
    monkeypatch.setattr(stream_api, "_DISCONNECT_POLL_SECONDS", 0.01)
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)

    async def quiet_then_reply(_outcome, _on_status, _on_reasoning, _should_cancel):
        await asyncio.sleep(0.07)
        yield "Hi"

    lines = [
        line
        async for line in stream_api._stream_tokens_sse(
            chat_id=uuid4(), stream_factory=quiet_then_reply, request=request
        )
    ]
    types = [json.loads(line.removeprefix("data: "))["type"] for line in lines]
    first_token = types.index("token")
    assert types[0] == "start"
    assert types[1:first_token].count("keepalive") >= 2
    assert set(types[1:first_token]) == {"keepalive"}
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_a_busy_sse_turn_sends_no_keepalive(monkeypatch):
    monkeypatch.setattr(stream_api, "_DISCONNECT_POLL_SECONDS", 0.01)
    request = AsyncMock()
    request.is_disconnected = AsyncMock(return_value=False)

    async def reply(_outcome, _on_status, _on_reasoning, _should_cancel):
        for part in ("a", "b", "c"):
            yield part

    lines = [
        line
        async for line in stream_api._stream_tokens_sse(
            chat_id=uuid4(), stream_factory=reply, request=request
        )
    ]
    assert not any('"type":"keepalive"' in line for line in lines)


class _RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> dict:
        await asyncio.sleep(10)
        return {"type": "ping"}


@pytest.mark.asyncio
async def test_a_quiet_ws_turn_sends_keepalives_until_it_ends(monkeypatch):
    monkeypatch.setattr(ws_turn, "TURN_KEEPALIVE_SECONDS", 0.02)
    socket = _RecordingSocket()

    async def quiet_then_reply():
        await asyncio.sleep(0.07)
        yield "Hi"

    await asyncio.wait_for(
        ws_turn.stream_over_ws(socket, quiet_then_reply(), asyncio.Event(), TurnOutcome()),
        timeout=2,
    )
    types = [frame["type"] for frame in socket.sent]
    assert types.count("keepalive") >= 2
    assert types[-1] == "done"
    # None after the turn ended.
    sent = len(socket.sent)
    await asyncio.sleep(0.06)
    assert len(socket.sent) == sent
