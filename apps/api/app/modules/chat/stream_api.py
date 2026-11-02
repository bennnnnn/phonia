"""HTTP SSE fallback for chat streaming (WebSocket alternative for web/proxy clients)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing, suppress
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.core import shutdown
from app.core.chat_rate_limit import allow_chat_message
from app.core.config import Settings
from app.core.deps import get_current_user, get_settings_dep
from app.core.log_context import bound_log_ids, new_turn_id
from app.core.redis import get_redis_client
from app.exceptions import RateLimitedError, RedisUnavailableError
from app.models.orm import User
from app.models.schemas import ChatMessageRequest
from app.modules.chat import stream_entry
from app.modules.chat.client_message import UNNAMED, ClientMessageClaim, claim_client_message
from app.modules.chat.finalize_registry import register_inflight_stream
from app.modules.chat.stream_events import (
    EXPECTED_TURN_ERRORS,
    TURN_KEEPALIVE_SECONDS,
    StreamEndEvent,
    await_finalize_commit,
    build_duplicate_event,
    build_keepalive_event,
    build_reasoning_event,
    build_start_event,
    build_status_event,
    build_token_event,
    clear_task_cancellation,
    finish_open_stream,
    persist_finalize_if_pending,
    pop_finalize_tasks,
    restarting_payload,
    settled_turn_event,
    take_related_prompts_event,
    turn_error_payload,
)
from app.modules.chat.stream_status import StreamReasoningFn, StreamStatusFn
from app.modules.chat.turn_deps import default_deps
from app.modules.chat.turn_outcome import TurnOutcome

# What the stream's producer puts for the SSE writer: an event (kind, text, status
# detail, status elapsed ms), or None when done.
_EventQueue = asyncio.Queue[tuple[str, str, str | None, int | None] | None]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats", tags=["chat-stream"])

_DISCONNECT_POLL_SECONDS = 0.5

_TokenStream = Callable[
    [TurnOutcome, StreamStatusFn, StreamReasoningFn, Callable[[], bool]],
    AsyncIterator[str],
]
# A message's claim on its client_message_id; None when an earlier send took it.
_ClaimMessage = Callable[[], Awaitable[ClientMessageClaim | None]]


async def require_chat_rate_limit(user: User = Depends(get_current_user)) -> Redis:
    """Throttle chat actions per user, then hand back the Redis handle.

    The same check guards all three streaming routes (and ws_api.py's own
    per-message limiter); as a dependency it is declared once instead of
    copy-pasted into every new streaming entry point. Redis down raises
    ``RedisUnavailableError``, answered 503 unavailable, not this 429.
    """
    redis = get_redis_client()
    if not await allow_chat_message(redis, user.id):
        # Coded, as the socket's own limit frame is: the English alone read on the phone
        # as "Couldn't reach the server" after a Regenerate over the limit.
        raise RateLimitedError("Too many chat requests. Try again shortly.", retry_after_seconds=60)
    return redis


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def _until_done(producer: asyncio.Task[None]) -> None:
    """Wait for the producer without passing this task's cancellation on to it.

    Starlette cancels a disconnected client's response at every await, and
    ``await producer`` forwarded each of those: a second cancel lands in the
    turn's own cleanup (the user row's save, the partial reply).
    """
    await asyncio.wait({producer})


async def _stream_tokens_sse(
    *,
    chat_id: UUID,
    stream_factory: _TokenStream,
    request: Request,
    cancel_event: asyncio.Event | None = None,
    claim_message: _ClaimMessage | None = None,
    user_id: UUID | None = None,
    queue_factory: Callable[[], _EventQueue] = asyncio.Queue,
) -> AsyncIterator[str]:
    """The turn's events as SSE lines, every log line inside carrying the turn's ids.

    ``queue_factory`` makes the queue the producer fills; a test passes one that holds a
    token, never by replacing ``asyncio.Queue`` for the whole process.
    """
    with bound_log_ids(chat_id=chat_id, user_id=user_id, turn=new_turn_id(), transport="sse"):
        # Closed with this generator: a client gone at ``start`` settles its claim there.
        async with aclosing(
            _turn_sse_lines(
                chat_id=chat_id,
                stream_factory=stream_factory,
                request=request,
                cancel_event=cancel_event,
                claim_message=claim_message,
                queue_factory=queue_factory,
            )
        ) as lines:
            async for line in lines:
                yield line


async def _claim_turn(claim_message: _ClaimMessage | None) -> ClientMessageClaim | str:
    """The turn's claim on its message, or the one SSE line that refuses the turn.

    Claimed once the response is under way, so a request whose client left before it
    began holds no claim; every exit after this settles it.
    """
    if shutdown.stopping():
        # A turn begun now would be stopped before its first token.
        return _sse(restarting_payload(user_message_saved=False))
    try:
        claim = UNNAMED if claim_message is None else await claim_message()
    except RedisUnavailableError as unavailable:
        return _sse(turn_error_payload(unavailable, user_message_saved=False))
    return _sse(build_duplicate_event()) if claim is None else claim


def _queued_event(
    kind: str, text: str, detail: str | None, elapsed_ms: int | None
) -> dict[str, Any]:
    """One event the producer queued, as the SSE payload the client reads."""
    if kind == "status":
        return build_status_event(text, detail, elapsed_ms=elapsed_ms)
    if kind == "reasoning":
        return build_reasoning_event(text)
    return build_token_event(text)


async def _turn_sse_lines(
    *,
    chat_id: UUID,
    stream_factory: _TokenStream,
    request: Request,
    cancel_event: asyncio.Event | None = None,
    claim_message: _ClaimMessage | None = None,
    queue_factory: Callable[[], _EventQueue] = asyncio.Queue,
) -> AsyncGenerator[str]:
    outcome = TurnOutcome()
    event_queue = queue_factory()
    producer_cancelled = False
    cancel_event = cancel_event or asyncio.Event()
    claim = await _claim_turn(claim_message)
    if isinstance(claim, str):
        yield claim
        return
    try:
        yield _sse(build_start_event())
    except GeneratorExit:
        # The client left before the turn began: nothing ran.
        claim.settle_after(None, outcome)
        raise

    async def on_status(
        phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        await event_queue.put(("status", phase, detail, elapsed_ms))

    async def on_reasoning(chunk: str) -> None:
        await event_queue.put(("reasoning", chunk, None, None))

    def should_cancel() -> bool:
        return cancel_event.is_set()

    async def produce_tokens() -> None:
        stream = stream_factory(outcome, on_status, on_reasoning, should_cancel)
        try:
            async for token_text in stream:
                if should_cancel():
                    break
                await event_queue.put(("token", token_text, None, None))
        except asyncio.CancelledError:
            # Cancel often lands in this task, not inside the generator.
            # The generator is then parked at yield and would never save.
            clear_task_cancellation()
            cancel_event.set()
        finally:
            await finish_open_stream(stream)
            with suppress(Exception):
                await event_queue.put(None)

    producer: asyncio.Task[None] | None = None

    def cancel_producer_once() -> None:
        nonlocal producer_cancelled
        if producer_cancelled or producer is None or producer.done():
            return
        producer_cancelled = True
        outcome.stop_when_safe(producer.cancel)

    async def watch_disconnect() -> None:
        """SSE is one-way, so a client's only way to stop generation is
        closing the connection — without this, a closed tab left the LLM
        call running to completion with tokens streamed to nobody, still
        burning quota and provider cost. `cancel_event` is also passed as
        `should_cancel` into the actual stream_entry call, so setting
        it here stops generation at the source, not just this relay.

        Cancel the producer task immediately — checking should_cancel only
        between tokens leaves an idle LiteLLM wait (up to stream timeout)
        running after disconnect.
        """
        try:
            while not cancel_event.is_set():
                if await request.is_disconnected():
                    cancel_event.set()
                    cancel_producer_once()
                    await event_queue.put(None)
                    return
                await asyncio.sleep(_DISCONNECT_POLL_SECONDS)
        except asyncio.CancelledError:
            pass

    def stop() -> None:
        """A client stops by closing the stream; a server shutdown does the same."""
        cancel_event.set()
        cancel_producer_once()

    producer = asyncio.create_task(produce_tokens())
    register_inflight_stream(chat_id, producer, stop=stop)
    disconnect_watcher = asyncio.create_task(watch_disconnect())

    try:
        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), TURN_KEEPALIVE_SECONDS)
            except TimeoutError:
                yield _sse(build_keepalive_event())
                continue
            if item is None:
                break
            yield _sse(_queued_event(*item))

        if cancel_event.is_set():
            # Disconnect already cancelled the producer. A second cancel
            # lands in the partial-reply save and drops the text.
            await _until_done(producer)
            if not shutdown.stopping():
                return
            # The server stopped the turn; the client is still here to be told.
            if outcome.message_id is None:
                yield _sse(restarting_payload(user_message_saved=outcome.user_message_saved))
                return

        await _until_done(producer)
        if producer.cancelled():
            return
        if (exc := producer.exception()) is not None:
            raise exc

        yield _sse(StreamEndEvent.from_outcome(outcome).model_dump())
        commit = await await_finalize_commit(pop_finalize_tasks(outcome))
        yield _sse(settled_turn_event(outcome, commit))
        if commit != "committed":
            return
        related = await take_related_prompts_event(outcome.related_task)
        if related is not None:
            yield _sse(related)
    except Exception as exc:
        if not isinstance(exc, EXPECTED_TURN_ERRORS):
            logger.exception("SSE chat stream failed chat_id=%s", chat_id)
        yield _sse(turn_error_payload(exc, user_message_saved=outcome.user_message_saved))
    finally:
        # The request task is cancelled when the client drops the socket.
        # That pending cancel would abort the partial-reply save on the
        # next await, and a second producer.cancel() does the same.
        clear_task_cancellation()
        cancel_event.set()
        cancel_producer_once()
        # Settled off this task once the producer is done: a disconnected
        # client's response is cancelled again at every await below.
        claim.settle_after(producer, outcome)
        if not producer.done():
            with suppress(asyncio.CancelledError):
                await _until_done(producer)
        # M10: if the SSE transport failed mid-stream (client disconnect,
        # proxy drop) the success-path finalize await above never ran, so
        # the background DB commit that persists the partial assistant
        # message would be orphaned and the user's partial reply lost.
        # Await it here too (bounded) so partial tokens are saved even
        # when the transport breaks. The shield inside await_finalize_commit
        # means this never cancels the commit task on timeout.
        await persist_finalize_if_pending(outcome)
        if not disconnect_watcher.done():
            disconnect_watcher.cancel()
            with suppress(asyncio.CancelledError):
                await disconnect_watcher


def _sse_response(body: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _client_geo(body: ChatMessageRequest) -> dict[str, Any]:
    return {
        "client_timezone": body.client_timezone,
        "client_location": body.client_location,
        "client_latitude": body.client_latitude,
        "client_longitude": body.client_longitude,
    }


@router.post("/{chat_id}/messages/stream")
async def stream_message_sse(
    chat_id: UUID,
    body: ChatMessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(require_chat_rate_limit),
) -> StreamingResponse:
    def message_turn(
        outcome: TurnOutcome,
        on_status: StreamStatusFn,
        on_reasoning: StreamReasoningFn,
        should_cancel: Callable[[], bool],
    ) -> AsyncIterator[str]:
        # A Stop waits for the message's row (``TurnOutcome.hold_stops``).
        outcome.hold_stops()
        return stream_entry.stream_chat_response(
            default_deps(),
            redis,
            settings,
            user_id=user.id,
            chat_id=chat_id,
            content=body.content,
            model_alias=body.model,
            attachment_ids=body.attachment_ids or None,
            should_cancel=should_cancel,
            outcome=outcome,
            on_status=on_status,
            on_reasoning=on_reasoning,
            user=user,
            **_client_geo(body),
        )

    return _sse_response(
        _stream_tokens_sse(
            chat_id=chat_id,
            request=request,
            claim_message=lambda: claim_client_message(
                redis, user_id=user.id, chat_id=chat_id, client_message_id=body.client_message_id
            ),
            user_id=user.id,
            stream_factory=message_turn,
        )
    )


@router.post("/{chat_id}/regenerate/stream")
async def stream_regenerate_sse(
    chat_id: UUID,
    body: ChatMessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(require_chat_rate_limit),
) -> StreamingResponse:
    return _sse_response(
        _stream_tokens_sse(
            chat_id=chat_id,
            request=request,
            user_id=user.id,
            stream_factory=lambda outcome, on_status, on_reasoning, should_cancel: (
                stream_entry.stream_regenerate_response(
                    default_deps(),
                    redis,
                    settings,
                    user_id=user.id,
                    chat_id=chat_id,
                    model_alias=body.model,
                    should_cancel=should_cancel,
                    outcome=outcome,
                    on_status=on_status,
                    on_reasoning=on_reasoning,
                    **_client_geo(body),
                )
            ),
        )
    )
