"""One chat turn over an open WebSocket: start, tokens, Stop, stream_end, done.

``ws_api`` reads the socket's frames and hands each message or regenerate here.
The producer runs the turn on its own task while this side keeps reading the
socket for a cancel; both go through the one ``stop`` a server shutdown uses too.
The next turn's frame may arrive once ``stream_end`` is out: it waits for this
turn's ``done`` and runs next, as a new SSE turn waits on the previous save.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect

from app.core.background_tasks import create_background_task
from app.core.log_context import bound_log_ids, new_turn_id
from app.exceptions import (
    ChatBusyError,
    ChatServiceError,
    QuotaExceededError,
)
from app.gateways.litellm_gateway import ModelUnavailableError
from app.modules.chat.client_message import UNNAMED, ClientMessageClaim
from app.modules.chat.finalize_registry import register_inflight_stream
from app.modules.chat.stream_events import (
    EXPECTED_TURN_ERRORS,
    TURN_KEEPALIVE_SECONDS,
    StreamEndEvent,
    await_finalize_commit,
    build_keepalive_event,
    build_pong_event,
    build_start_event,
    build_token_event,
    clear_task_cancellation,
    finish_open_stream,
    persist_finalize_if_pending,
    pop_finalize_tasks,
    settled_turn_event,
    take_related_prompts_event,
    turn_error_payload,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.ws_limits import FrameBudget, close_flooding_socket, safe_send_json

logger = logging.getLogger(__name__)

# A reply is far shorter; a larger count is not a length the client drew.
_MAX_SHOWN_CHARS = 1_000_000
# Frames that start a turn.
TURN_FRAME_TYPES = frozenset({"message", "regenerate"})
# What a turn leaves the socket: the next turn's frame, sent during its save, or the
# frame read it still had running when it ended (the socket's next read takes it).
TurnLeft = dict[str, Any] | asyncio.Task[Any] | None


def client_shown_chars(cancel: dict[str, Any]) -> int | None:
    """How much of the reply the client drew before its user tapped Stop, when it says."""
    shown = cancel.get("shown_chars")
    if isinstance(shown, bool) or not isinstance(shown, int):
        return None
    return shown if 0 <= shown <= _MAX_SHOWN_CHARS else None


async def _run_stream(
    websocket: WebSocket,
    stream: AsyncIterator[str],
    cancel_event: asyncio.Event,
    outcome: TurnOutcome,
    text_complete: asyncio.Event,
) -> None:
    """The turn's tokens, ``stream_end`` once its text is complete, then ``done``."""
    sent_tokens = 0
    try:
        async for token_text in stream:
            if cancel_event.is_set():
                break
            if not await safe_send_json(websocket, build_token_event(token_text)):
                # Client left (New chat / navigate). Keep consuming the
                # model stream so the thread gets a complete reply.
                async for _ in stream:
                    if cancel_event.is_set():
                        break
                break
            sent_tokens += 1
    except asyncio.CancelledError:
        # Task cancel interrupts an in-flight LiteLLM wait; still fall
        # through to stream_end/done so the client gets a clean stop.
        clear_task_cancellation()
        cancel_event.set()
    except Exception as exc:
        if not isinstance(exc, QuotaExceededError | ChatServiceError | ModelUnavailableError):
            logger.exception("Chat stream failed")
        await safe_send_json(
            websocket, turn_error_payload(exc, user_message_saved=outcome.user_message_saved)
        )
        return

    # A stop can leave the generator parked at yield. Resume it so the
    # partial reply is saved before we read the finalize task.
    await finish_open_stream(stream)

    # M12: if the user cancelled before any token was streamed (hard
    # cancel at the very start), skip stream_end + done entirely — an
    # empty done with no content is misleading and the client already
    # dropped the turn locally. SSE already returns early on cancel;
    # this symmetrizes the WS path. Partial tokens (sent_tokens > 0)
    # still get stream_end + done so the client can swap the streamed-*
    # id for the persisted message_id.
    if cancel_event.is_set() and sent_tokens == 0:
        # Still let the finalize task run so any reserved quota is
        # refunded, but don't send events the client doesn't expect.
        finalize_db_task = pop_finalize_tasks(outcome)
        if finalize_db_task is not None:
            with suppress(Exception):
                await await_finalize_commit(finalize_db_task)
        return

    # Set before sending: the client's next message can only answer this frame.
    text_complete.set()
    if not await safe_send_json(websocket, StreamEndEvent.from_outcome(outcome).model_dump()):
        return

    # Await the DB commit before sending `done` so the message_id we hand
    # the client always references a persisted row. The token stream is
    # already flushed (stream_end above), so only the final `done` event
    # waits on the commit — streaming latency is unchanged. If the commit
    # FAILED we send an error instead of a ghost `done` with a fake id.
    # On TIMEOUT we send `done` without `message_id` (persisting: true) so
    # the client keeps the local bubble and refetches instead of trusting
    # a row that may never persist if the shielded task later fails.
    commit = await await_finalize_commit(pop_finalize_tasks(outcome))
    await safe_send_json(websocket, settled_turn_event(outcome, commit))
    if commit == "committed":
        schedule_related_prompts(websocket, outcome)


async def stream_over_ws(
    websocket: WebSocket,
    stream: AsyncIterator[str],
    cancel_event: asyncio.Event,
    outcome: TurnOutcome,
    chat_id: UUID | None = None,
    frame_budget: FrameBudget | None = None,
    claim: ClientMessageClaim = UNNAMED,
) -> TurnLeft:
    """Run one turn; return what it left the socket (``TurnLeft``).

    Once ``stream_end`` is out the reply's text is complete and only its commit
    is left, so a client may send its next message then. That frame is held
    (the socket is not read again) until ``done`` is sent, and the caller runs it
    next. Before ``stream_end`` a second turn is still refused as busy.
    """
    text_complete = asyncio.Event()
    producer = asyncio.create_task(
        _run_stream(websocket, stream, cancel_event, outcome, text_complete)
    )

    async def keep_alive() -> None:
        """A frame every so often until the turn ends: the phone's idle deadline."""
        while True:
            await asyncio.sleep(TURN_KEEPALIVE_SECONDS)
            if producer.done() or not await safe_send_json(websocket, build_keepalive_event()):
                return

    heartbeat = asyncio.create_task(keep_alive())

    def stop() -> None:
        """The user's Stop (a server shutdown runs the same one): it cuts an in-flight
        model wait short, but not the wait for ``done`` that is all ``stream_end`` leaves."""
        cancel_event.set()
        if not text_complete.is_set():
            outcome.stop_when_safe(producer.cancel)

    if chat_id is not None:
        # GET /messages waits on the producer so a New-chat leave can still
        # return the completed assistant. Do not put this in the finalize
        # map — stream_chat_response gather-waits that map as a child Task
        # and would deadlock 10s on itself.
        register_inflight_stream(chat_id, producer, stop=stop)
    next_turn: dict[str, Any] | None = None
    receiver: asyncio.Task[Any] | None = None
    left: asyncio.Task[Any] | None = None
    try:
        while not producer.done():
            receiver = asyncio.create_task(websocket.receive_json())
            done, _pending = await asyncio.wait(
                {producer, receiver},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if receiver in done:
                read, receiver = receiver, None
                try:
                    msg = read.result()
                except WebSocketDisconnect:
                    # Navigate-away: finish the producer (it drains on send
                    # failure). Do not cancel — Stop is the only hard stop.
                    break
                except (json.JSONDecodeError, KeyError, TypeError):
                    # Keep ownership of the active producer when a bad JSON
                    # or binary frame arrives, just as the idle loop does.
                    if frame_budget is not None and not frame_budget.allow():
                        # The producer drains on send failure; the reply is saved.
                        await close_flooding_socket(websocket)
                        break
                    await safe_send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                    continue
                if frame_budget is not None and not frame_budget.allow():
                    await close_flooding_socket(websocket)
                    break
                # Non-dict JSON (array/primitive) must not AttributeError the
                # dispatch loop while the producer is still streaming.
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "cancel":
                    outcome.client_shown_chars = client_shown_chars(msg)
                    stop()
                elif msg.get("type") == "ping":
                    await safe_send_json(websocket, build_pong_event())
                elif msg.get("type") in TURN_FRAME_TYPES and (
                    text_complete.is_set() or producer.done()
                ):
                    # Bounded: the producer only waits out the commit
                    # (DONE_COMMIT_WAIT_SECONDS), and frames after this one
                    # (its own Stop) stay unread until that turn reads them.
                    next_turn = msg
                    break
                else:
                    await safe_send_json(
                        websocket,
                        turn_error_payload(ChatBusyError(), user_message_saved=False),
                    )
        # Stop already cancelled the producer once. Cancelling again
        # aborts the save of the partial reply.
        try:
            await producer
        except asyncio.CancelledError:
            pass
        # The turn ended first: its read is the socket's next, never cancelled (receive_frame).
        left, receiver = receiver, None
    except WebSocketDisconnect:
        if not producer.done():
            try:
                await producer
            except asyncio.CancelledError:
                pass
    finally:
        # A disconnect or shutdown that cancels this handler mid-wait leaves the frame
        # read it just started; it must not outlive the turn.
        if receiver is not None and not receiver.done():
            receiver.cancel()
        heartbeat.cancel()
        try:
            await _settle_turn(producer, claim, outcome)
        except BaseException:
            # Cancelled while settling (a shutdown): the handed-on read has no owner.
            if left is not None:
                left.cancel()
            raise
    return next_turn if next_turn is not None else left


async def _settle_turn(
    producer: asyncio.Task[None], claim: ClientMessageClaim, outcome: TurnOutcome
) -> None:
    """The turn's claim and its reply's save, however the turn ended."""
    # The producer is done unless an error cut the turn's loop short; then the
    # claim is settled once it is.
    if producer.done():
        await claim.settle(outcome)
    else:
        claim.settle_after(producer, outcome)
    # Same as SSE M10: client close must not orphan the DB commit that
    # persists the (partial) assistant row and enqueues the title job.
    await persist_finalize_if_pending(outcome)


async def run_chat_stream(
    websocket: WebSocket,
    *,
    cancel_event: asyncio.Event,
    stream_factory: Callable[[TurnOutcome], AsyncIterator[str]],
    chat_id: UUID | None = None,
    frame_budget: FrameBudget | None = None,
    claim: ClientMessageClaim = UNNAMED,
) -> TurnLeft:
    """One turn: ``start``, then the stream, which settles the message's ``claim``.

    Returns what the turn left the socket (``TurnLeft``).
    """
    cancel_event.clear()
    outcome = TurnOutcome()
    with bound_log_ids(chat_id=chat_id, turn=new_turn_id(), transport="ws"):
        try:
            started = await safe_send_json(websocket, build_start_event())
        except BaseException:
            claim.settle_after(None, outcome)
            raise
        if not started and claim.key is None:
            # A client gone before ``start`` gets no turn.
            return None
        # A named message runs even when its client is gone: the phone may have sent
        # it again meanwhile (and been told ``duplicate``), and it follows this turn
        # by reloading the chat. The claim keeps any other send of it from running.
        try:
            return await stream_over_ws(
                websocket,
                stream_factory(outcome),
                cancel_event,
                outcome,
                chat_id,
                frame_budget,
                claim,
            )
        except Exception as exc:
            if not isinstance(exc, EXPECTED_TURN_ERRORS):
                logger.exception("Unexpected chat stream error")
            await safe_send_json(
                websocket, turn_error_payload(exc, user_message_saved=outcome.user_message_saved)
            )
            return None


def schedule_related_prompts(websocket: WebSocket, outcome: TurnOutcome) -> None:
    """Send follow-up questions after ``done`` without holding the next message."""
    task = outcome.related_task
    if task is None:
        return

    async def _send() -> None:
        event = await take_related_prompts_event(task)
        if event is not None:
            await safe_send_json(websocket, event)

    create_background_task(_send(), name="related_prompts_send")
