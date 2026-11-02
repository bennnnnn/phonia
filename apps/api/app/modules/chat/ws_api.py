"""The chat WebSocket: handshake limits, auth, then one frame at a time.

A message or regenerate frame becomes a turn (``ws_turn``); one that arrives
while the last turn saves runs as soon as that turn is done. The socket's own
limits (frames, sockets per user, idle time) are ``ws_limits``. A ping is
answered with a pong, and a message the server already took (its
``client_message_id``) with ``duplicate`` instead of a second turn.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from redis.asyncio import Redis
from starlette.websockets import WebSocketState

from app.core import access_tokens, chat_rate_limit, shutdown, user_cache
from app.core.client_ip import client_ip
from app.core.config import Settings, get_settings
from app.core.log_context import bound_log_ids
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.models.orm import User
from app.models.schemas import ChatMessageRequest
from app.modules.chat import stream_entry, turn_deps
from app.modules.chat.client_message import claim_client_message
from app.modules.chat.stream_events import (
    build_duplicate_event,
    build_pong_event,
    build_reasoning_event,
    build_status_event,
    error_payload_for_exception,
    rate_limited_connect_payload,
    rate_limited_payload,
    restarting_payload,
    turn_error_payload,
)
from app.modules.chat.stream_status import StreamReasoningFn, StreamStatusFn
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.ws_limits import (
    WS_IDLE_CLOSE_CODE,
    WS_TOO_MANY_SOCKETS_CLOSE_CODE,
    FrameBudget,
    close_flooding_socket,
    close_quietly,
    receive_frame,
    safe_send_json,
    user_socket_slot,
)
from app.modules.chat.ws_turn import TURN_FRAME_TYPES, TurnLeft, run_chat_stream

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])

_WS_MSG_WINDOW_SECONDS = 60
_WS_CONNECT_RATE_LIMIT = 30
_WS_HANDSHAKE_RATE_LIMIT = 60  # unauthenticated connects per IP per minute
# Try Again Later: Redis is down. The client backs off; it is no auth failure.
_WS_TRY_AGAIN_LATER_CLOSE_CODE = 1013


async def _ws_rate_limit(redis: Redis, user_id: UUID) -> bool:
    """Per-message throttle for chat actions on an open WebSocket."""
    return await chat_rate_limit.allow_chat_message(redis, user_id)


async def _close_while_down(websocket: WebSocket, frame: dict[str, Any]) -> None:
    """Redis is down: send ``frame`` (code ``unavailable``), then close 1013 Try Again Later.

    The socket's 503. A limit that could not count said "Too many requests" (a limit's
    words) or refused the handshake (1008), and the outage looked like the user's doing.
    """
    await safe_send_json(websocket, frame)
    await close_quietly(websocket, _WS_TRY_AGAIN_LATER_CLOSE_CODE)


async def _ws_connect_rate_limit(redis: Redis, user_id: UUID) -> bool:
    """Limit new WebSocket handshakes per user (separate from per-message limits)."""
    return await allow_request_unless_down(
        redis,
        f"rate:ws:connect:{user_id}",
        limit=_WS_CONNECT_RATE_LIMIT,
        window_seconds=_WS_MSG_WINDOW_SECONDS,
    )


async def _ws_handshake_rate_limit(redis: Redis, websocket: WebSocket) -> bool:
    """Cap unauthenticated connect attempts by client IP before accept().

    Uses the shared `client_ip` resolver so a Fly-proxied
    handshake is keyed on the edge-seen IP (fly-client-ip / XFF), not the
    proxy's — otherwise every connect shares one proxy's bucket.
    """
    settings = get_settings()
    ip = client_ip(websocket, settings)
    return await allow_request_unless_down(
        redis,
        f"rate:ws:handshake:{ip}",
        limit=_WS_HANDSHAKE_RATE_LIMIT,
        window_seconds=_WS_MSG_WINDOW_SECONDS,
    )


def _status_emitters(websocket: WebSocket) -> tuple[StreamStatusFn, StreamReasoningFn]:
    """Shared status/reasoning WS emitters for chargeable chat actions."""

    async def emit_status(
        phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        await safe_send_json(websocket, build_status_event(phase, detail, elapsed_ms=elapsed_ms))

    async def emit_reasoning(chunk: str) -> None:
        await safe_send_json(websocket, build_reasoning_event(chunk))

    return emit_status, emit_reasoning


def _client_geo_kwargs(
    request: ChatMessageRequest,
    *,
    client_timezone: str | None,
) -> dict[str, Any]:
    """Where the phone is for this turn. Its zone is the one the turn's frame names,
    since the phone can change zone while the socket stays open (a flight, Settings);
    a frame without one (an older phone) keeps the zone of the auth frame."""
    return {
        "client_timezone": request.client_timezone or client_timezone,
        "client_location": request.client_location,
        "client_latitude": request.client_latitude,
        "client_longitude": request.client_longitude,
    }


async def _handle_regenerate(
    websocket: WebSocket,
    *,
    redis: Redis,
    settings: Settings,
    user_id: UUID,
    chat_id: UUID,
    payload: dict[str, Any],
    client_timezone: str | None,
    cancel_event: asyncio.Event,
    emit_status: StreamStatusFn,
    emit_reasoning: StreamReasoningFn,
    frame_budget: FrameBudget | None = None,
) -> TurnLeft:
    try:
        request = ChatMessageRequest.model_validate(payload)
    except ValidationError:
        await websocket.send_json({"type": "error", "message": "Invalid regenerate request"})
        return None

    def _regen_stream(outcome: TurnOutcome) -> AsyncIterator[str]:
        return stream_entry.stream_regenerate_response(
            turn_deps.default_deps(),
            redis,
            settings,
            user_id=user_id,
            chat_id=chat_id,
            model_alias=request.model,
            should_cancel=cancel_event.is_set,
            outcome=outcome,
            on_status=emit_status,
            on_reasoning=emit_reasoning,
            **_client_geo_kwargs(request, client_timezone=client_timezone),
        )

    return await run_chat_stream(
        websocket,
        cancel_event=cancel_event,
        stream_factory=_regen_stream,
        chat_id=chat_id,
        frame_budget=frame_budget,
    )


async def _handle_message(
    websocket: WebSocket,
    *,
    redis: Redis,
    settings: Settings,
    user_id: UUID,
    chat_id: UUID,
    payload: dict[str, Any],
    client_timezone: str | None,
    cancel_event: asyncio.Event,
    emit_status: StreamStatusFn,
    emit_reasoning: StreamReasoningFn,
    frame_budget: FrameBudget | None = None,
    access: access_tokens.AccessCheck | None = None,
) -> TurnLeft:
    try:
        request = ChatMessageRequest.model_validate(payload)
    except ValidationError:
        await websocket.send_json(
            turn_error_payload(None, user_message_saved=False, message="Invalid message")
        )
        return None

    # Reject an empty text-only message at the WS layer so the client gets an
    # explicit error frame immediately, rather than the stream raising
    # ChatNotFoundError mid-flight (which the client may not map to a visible
    # error). An empty message with attachments is valid (image-only turn).
    if not request.content.strip() and not request.attachment_ids:
        await websocket.send_json(
            turn_error_payload(None, user_message_saved=False, message="Message cannot be empty.")
        )
        return None

    try:
        claim = await claim_client_message(
            redis, user_id=user_id, chat_id=chat_id, client_message_id=request.client_message_id
        )
    except RedisUnavailableError as exc:
        await safe_send_json(websocket, turn_error_payload(exc, user_message_saved=False))
        return None
    if claim is None:
        # A resend of a message an earlier turn took (its socket died before the
        # phone heard ``start``): the phone follows that turn instead.
        await safe_send_json(websocket, build_duplicate_event())
        return None

    user_generation = access.user_generation if access is not None else None
    user: User | None = (
        user_cache.cached_user(user_id, user_generation) if user_generation is not None else None
    )

    def _message_stream(outcome: TurnOutcome) -> AsyncIterator[str]:
        # A Stop waits for the message's row (``TurnOutcome.hold_stops``).
        outcome.hold_stops()
        return stream_entry.stream_chat_response(
            turn_deps.default_deps(),
            redis,
            settings,
            user_id=user_id,
            chat_id=chat_id,
            content=request.content,
            model_alias=request.model,
            attachment_ids=request.attachment_ids,
            should_cancel=cancel_event.is_set,
            outcome=outcome,
            on_status=emit_status,
            on_reasoning=emit_reasoning,
            user=user,
            user_generation=user_generation,
            **_client_geo_kwargs(request, client_timezone=client_timezone),
        )

    return await run_chat_stream(
        websocket,
        cancel_event=cancel_event,
        stream_factory=_message_stream,
        chat_id=chat_id,
        frame_budget=frame_budget,
        claim=claim,
    )


@dataclass
class _ChatSocket:
    """One authenticated chat socket and what its turns share."""

    websocket: WebSocket
    redis: Redis
    settings: Settings
    chat_id: UUID
    user_id: UUID
    token: str
    client_timezone: str | None
    cancel_event: asyncio.Event
    frame_budget: FrameBudget
    # What the last turn left: a turn sent during its save (it runs before the socket is
    # read again), or the read it still had running (it is the socket's next read).
    next_turn: TurnLeft = None


async def _authenticate(
    websocket: WebSocket, redis: Redis, settings: Settings, chat_id: UUID
) -> tuple[UUID, str, str | None] | None:
    """The auth frame's user, token and time zone; None once the socket is refused."""
    try:
        # A socket that connects and never sends the auth frame is dropped.
        auth_message = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=settings.ws_auth_timeout_seconds,
        )
        if not isinstance(auth_message, dict):
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            await websocket.close()
            return None
        token = auth_message.get("token")
        if not isinstance(token, str) or not token.strip():
            await websocket.send_json({"type": "error", "message": "Missing token"})
            await websocket.close()
            return None

        user_id = await access_tokens.verify_access_token(redis, token, settings)
        client_timezone = auth_message.get("client_timezone")
        if client_timezone is not None and not isinstance(client_timezone, str):
            client_timezone = None
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected before authentication chat_id=%s", chat_id)
        return None
    except TimeoutError:
        await safe_send_json(websocket, {"type": "error", "message": "Auth timeout"})
        await websocket.close()
        return None
    except RedisUnavailableError as exc:
        await _close_while_down(websocket, error_payload_for_exception(exc))
        return None
    except (AuthenticationError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
        await safe_send_json(websocket, {"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return None
    return user_id, token, client_timezone


@router.websocket("/ws/chats/{chat_id}")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: UUID,
) -> None:
    settings = get_settings()
    redis = get_redis_client()
    # Fail closed: a Redis outage refuses the connect, saying so.
    try:
        handshake_allowed = await _ws_handshake_rate_limit(redis, websocket)
    except RedisUnavailableError as exc:
        # Accepted only to say why: a handshake refused before accept reaches the
        # client as a bare failure, with no frame and no close code.
        await websocket.accept()
        await _close_while_down(websocket, error_payload_for_exception(exc))
        return
    if not handshake_allowed:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    auth = await _authenticate(websocket, redis, settings, chat_id)
    if auth is None:
        return
    user_id, token, client_timezone = auth

    try:
        allowed = await _ws_connect_rate_limit(redis, user_id)
    except RedisUnavailableError as exc:
        await _close_while_down(websocket, error_payload_for_exception(exc))
        return
    if not allowed:
        await websocket.send_json(rate_limited_connect_payload())
        await websocket.close()
        return

    with (
        bound_log_ids(user_id=user_id),
        user_socket_slot(user_id, settings.ws_max_sockets_per_user) as admitted,
    ):
        if not admitted:
            logger.warning("Chat socket cap reached user_id=%s chat_id=%s", user_id, chat_id)
            await close_quietly(websocket, WS_TOO_MANY_SOCKETS_CLOSE_CODE)
            return
        await _serve_frames(
            _ChatSocket(
                websocket=websocket,
                redis=redis,
                settings=settings,
                chat_id=chat_id,
                user_id=user_id,
                token=token,
                client_timezone=client_timezone,
                cancel_event=asyncio.Event(),
                frame_budget=FrameBudget(),
            )
        )


async def _serve_frames(conn: _ChatSocket) -> None:
    """Read frames until the client leaves, floods, or sits idle between turns."""
    websocket, chat_id = conn.websocket, conn.chat_id
    try:
        while True:
            held, conn.next_turn = conn.next_turn, None
            if isinstance(held, dict):
                # Counted against the frame budget when it arrived.
                if not await _dispatch(conn, held):
                    return
                continue
            try:
                payload = await receive_frame(
                    websocket, conn.settings.ws_idle_timeout_seconds, held
                )
            except TimeoutError:
                logger.info("Idle WebSocket closed chat_id=%s", chat_id)
                await close_quietly(websocket, WS_IDLE_CLOSE_CODE)
                return
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected chat_id=%s", chat_id)
                return
            except RuntimeError as exc:
                # Disconnect already consumed by the stream loop (New chat
                # closes the socket while tokens are still being generated),
                # or a send to a client that vanished without a close frame
                # already marked the socket closed.
                if (
                    "disconnect" in str(exc).lower()
                    or websocket.application_state == WebSocketState.DISCONNECTED
                ):
                    logger.info("WebSocket disconnected chat_id=%s", chat_id)
                    return
                raise
            except (json.JSONDecodeError, KeyError, TypeError):
                # Bad JSON, binary frames (no "text"), or other non-text payloads.
                if not conn.frame_budget.allow():
                    await close_flooding_socket(websocket)
                    return
                await safe_send_json(websocket, {"type": "error", "message": "Invalid JSON"})
                continue

            if not conn.frame_budget.allow():
                logger.warning("WebSocket frame flood; closing chat_id=%s", chat_id)
                await close_flooding_socket(websocket)
                return

            if not isinstance(payload, dict):
                await safe_send_json(websocket, {"type": "error", "message": "Invalid message"})
                continue
            if not await _dispatch(conn, payload):
                return
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected chat_id=%s", chat_id)


async def _dispatch(conn: _ChatSocket, payload: dict[str, Any]) -> bool:
    """Act on one frame between turns; False once the socket is closed."""
    websocket = conn.websocket
    msg_type = payload.get("type")
    if msg_type == "cancel":
        conn.cancel_event.set()
        return True
    if msg_type == "ping":
        # Counted by the frame budget like any frame; the phone pings on connect
        # and when a send goes unanswered, never to keep an idle socket open.
        await safe_send_json(websocket, build_pong_event())
        return True
    if msg_type not in TURN_FRAME_TYPES:
        return True
    if shutdown.stopping():
        # A turn begun now would be stopped before its first token.
        await safe_send_json(
            websocket,
            restarting_payload(user_message_saved=False),
        )
        return True
    # Re-check access on every chargeable frame so logout / account
    # delete / refresh-reuse revoke (purge_user_sessions) actually
    # closes open sockets — handshake-only verify would leave them live.
    # The same read says whether this process's copy of the user is current.
    try:
        access = await access_tokens.check_access(conn.redis, conn.token, conn.settings)
        allowed = await _ws_rate_limit(conn.redis, conn.user_id)
    except RedisUnavailableError as exc:
        # The frame was not taken: the phone offers it again (Retry) once Redis is back.
        await _close_while_down(websocket, turn_error_payload(exc, user_message_saved=False))
        return False
    except AuthenticationError:
        await safe_send_json(websocket, {"type": "error", "message": "Unauthorized"})
        await websocket.close(code=1008)
        return False
    if not allowed:
        # Coded: a Regenerate over the limit showed the English (no message waits as Retry).
        await websocket.send_json(rate_limited_payload())
        return True

    handle: Callable[..., Awaitable[TurnLeft]] = (
        _handle_regenerate if msg_type == "regenerate" else partial(_handle_message, access=access)
    )
    emit_status, emit_reasoning = _status_emitters(websocket)
    conn.next_turn = await handle(
        websocket,
        redis=conn.redis,
        settings=conn.settings,
        user_id=conn.user_id,
        chat_id=conn.chat_id,
        payload=payload,
        client_timezone=conn.client_timezone,
        cancel_event=conn.cancel_event,
        emit_status=emit_status,
        emit_reasoning=emit_reasoning,
        frame_budget=conn.frame_budget,
    )
    return True
