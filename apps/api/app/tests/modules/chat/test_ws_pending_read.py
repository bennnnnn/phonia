"""A turn that ends first leaves its frame read running; the socket's next read takes it.

A server may lose the frame it was handing a read that is then cancelled, and
Starlette's test client does. The stopped turn of ``test_ws`` used to cancel its read
as its producer finished; a message landing in that instant was never answered, and
the socket sat until its idle timeout (CI, 2026-11-01).
"""

import asyncio
import gc
import json
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

import anyio
import pytest
from fastapi import WebSocket

import app.modules.chat.ws_turn as ws_turn
from app.modules.chat.client_message import ClientMessageClaim
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.ws_limits import receive_frame

_EMPTY = {"type": "message", "content": ""}


class _TestClientSocket:
    """Receives as Starlette's test client does: through an anyio memory stream, where a
    frame handed to a waiting read is gone if that read is cancelled before it resumes."""

    def __init__(self) -> None:
        self.sender, self.receiver = anyio.create_memory_object_stream[str](8)
        self.sent: list[dict[str, Any]] = []
        self.reads: list[asyncio.Task[Any]] = []

    async def receive_json(self) -> Any:
        task = asyncio.current_task()
        assert task is not None
        self.reads.append(task)
        return json.loads(await self.receiver.receive())

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    @property
    def ws(self) -> WebSocket:
        return cast(WebSocket, self)

    def deliver(self, frame: dict[str, Any]) -> None:
        """``frame`` handed to the read already waiting for one, as the client sends it."""
        assert self.receiver.statistics().tasks_waiting_receive == 1, "no read is waiting"
        self.sender.send_nowait(json.dumps(frame))


class _AsyncioDeliveringAtTurnEnd:
    """``asyncio`` for ``ws_turn``, but its ``wait`` hands the socket a frame at the one
    instant the race needs: the turn's producer has finished and the read still waits."""

    def __init__(self, deliver: Callable[[], Any]) -> None:
        self._deliver = deliver
        self.delivered = False

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)

    async def wait(self, tasks: Any, **kwargs: Any) -> Any:
        done, pending = await asyncio.wait(tasks, **kwargs)
        if pending and not self.delivered:
            self.delivered = True
            self._deliver()
        return done, pending


async def _one_token() -> AsyncIterator[str]:
    yield "Hi"


@pytest.mark.asyncio
async def test_a_frame_sent_as_the_turn_ends_is_read_next(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = _TestClientSocket()
    stand_in = _AsyncioDeliveringAtTurnEnd(lambda: socket.deliver(_EMPTY))
    monkeypatch.setattr(ws_turn, "asyncio", stand_in)

    left = await asyncio.wait_for(
        ws_turn.stream_over_ws(socket.ws, _one_token(), asyncio.Event(), TurnOutcome()),
        timeout=2,
    )

    assert stand_in.delivered
    assert [frame["type"] for frame in socket.sent][-1] == "done"
    # The turn's read was handed on, not cancelled, so the frame is the socket's next.
    assert isinstance(left, asyncio.Task) and not left.cancelled()
    assert await receive_frame(socket.ws, 1, left) == _EMPTY


@pytest.mark.asyncio
async def test_a_frame_answered_during_the_turn_leaves_the_next_read_in_order() -> None:
    socket = _TestClientSocket()
    # Before ``stream_end`` a second message is refused as busy; the turn then reads on.
    socket.sender.send_nowait(json.dumps({"type": "message", "content": "too soon"}))

    async def slow_reply() -> AsyncIterator[str]:
        yield "Hi"
        await asyncio.sleep(0.05)

    left = await asyncio.wait_for(
        ws_turn.stream_over_ws(socket.ws, slow_reply(), asyncio.Event(), TurnOutcome()),
        timeout=2,
    )
    types = [frame["type"] for frame in socket.sent]
    assert types.index("error") < types.index("done")
    assert isinstance(left, asyncio.Task) and not left.done()
    socket.sender.send_nowait(json.dumps(_EMPTY))
    assert await receive_frame(socket.ws, 1, left) == _EMPTY


@pytest.mark.asyncio
async def test_an_idle_read_is_cancelled_and_says_timeout() -> None:
    socket = _TestClientSocket()
    read = asyncio.create_task(socket.receive_json())
    with pytest.raises(TimeoutError):
        await receive_frame(socket.ws, 0.05, read)
    assert read.cancelled()


@pytest.mark.asyncio
async def test_a_read_given_up_by_its_caller_does_not_outlive_it() -> None:
    socket = _TestClientSocket()
    read = asyncio.create_task(socket.receive_json())
    waiting = asyncio.create_task(receive_frame(socket.ws, 0, read))
    await asyncio.sleep(0.01)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await asyncio.sleep(0)
    assert read.cancelled()


class _SlowClaim(ClientMessageClaim):
    """A claim whose settling waits until the test cancels the turn's handler."""

    def __init__(self) -> None:
        super().__init__()
        self.settling = asyncio.Event()

    async def settle(self, outcome: TurnOutcome) -> None:
        self.settling.set()
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_a_handler_cancelled_while_settling_leaves_no_read_running() -> None:
    loop = asyncio.get_running_loop()
    unhandled: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    socket = _TestClientSocket()
    claim = _SlowClaim()
    handler = asyncio.create_task(
        ws_turn.stream_over_ws(socket.ws, _one_token(), asyncio.Event(), TurnOutcome(), claim=claim)
    )
    await asyncio.wait_for(claim.settling.wait(), timeout=2)
    # The turn ended first, so its read was handed on; then a shutdown cancels the handler.
    assert socket.reads and not socket.reads[-1].done()
    handler.cancel()
    with pytest.raises(asyncio.CancelledError):
        await handler
    await asyncio.sleep(0)
    assert all(read.cancelled() for read in socket.reads)
    # A read left running would fail later with an exception nobody retrieves.
    socket.reads.clear()
    gc.collect()
    await asyncio.sleep(0)
    loop.set_exception_handler(None)
    assert unhandled == []
