from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.consent import get_consented_user
from app.core.db import SessionLocal
from app.core.deps import get_current_user, get_settings_dep
from app.core.rate_limit import allow_request_unless_down
from app.core.redis import get_redis_client
from app.gateways import openai_speech_gateway
from app.models.orm import User
from app.models.schemas import MessageOut
from app.models.schemas.text import UserText
from app.modules.speech import live_talk as live_talk_service
from app.modules.speech.gates import (
    SpeechRefusedError,
    require_plan_feature,
    require_speech_rate,
    require_voice_spend_ok,
)
from app.modules.speech.schemas import SpeechLiveStatusOut
from app.services import quota as quota_service

router = APIRouter(prefix="/speech", tags=["speech"])


class RealtimeSessionIn(BaseModel):
    chat_id: UUID | None = None
    barge_in: bool = False
    tools_enabled: bool = False


class RealtimeSessionOut(BaseModel):
    client_secret: str
    expires_at: int
    call_id: str
    model: str
    # Seconds reserved from this month's live talk minutes; the phone hangs up here.
    max_duration_seconds: int


class RealtimeEndIn(BaseModel):
    call_id: str = Field(min_length=8, max_length=128)


class RealtimePersistIn(BaseModel):
    chat_id: UUID
    call_id: str = Field(min_length=8, max_length=128)
    user_text: UserText = Field(default="", max_length=20_000)
    assistant_text: UserText = Field(default="", max_length=20_000)
    turn_id: UserText | None = Field(default=None, max_length=128)
    return_messages: bool = False


class RealtimeToolIn(BaseModel):
    chat_id: UUID
    call_id: str = Field(min_length=8, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    name: Literal["memory_lookup", "web_search"]
    query: UserText = Field(min_length=1, max_length=500)


def _safety_identifier(user: User) -> str:
    return hashlib.sha256(f"recall:{user.id}".encode()).hexdigest()


def _realtime_instructions(
    history: list[tuple[str, str]] | None,
    *,
    memory_block: str = "",
    custom_instructions: str = "",
    schedule_block: str = "",
) -> str:
    return live_talk_service.build_realtime_instructions(
        history,
        memory_block=memory_block,
        custom_instructions=custom_instructions,
        schedule_block=schedule_block,
    )


async def _load_session_context_or_404(
    chat_id: UUID | None,
    user: User,
    settings: Settings,
) -> live_talk_service.LiveTalkSessionContext:
    loaded = await live_talk_service.load_live_talk_session_context(
        chat_id=chat_id,
        user=user,
        settings=settings,
    )
    if loaded is None:
        raise SpeechRefusedError("Chat not found", status_code=status.HTTP_404_NOT_FOUND)
    return loaded


def _require_live_talk_plan(user: User, settings: Settings) -> None:
    require_plan_feature(user, settings, "live_talk", quota_service.LIVE_TALK_NOT_IN_PLAN_MESSAGE)


async def _reserve_realtime_or_raise(user: User, settings: Settings):
    """Gate a mint and reserve its session length. Returns (redis, seconds)."""
    if not settings.speech_live_talk_enabled or not settings.speech_realtime_voice_enabled:
        raise SpeechRefusedError(
            "Not available", status_code=status.HTTP_404_NOT_FOUND, code="not_available"
        )
    _require_live_talk_plan(user, settings)
    if not settings.openai_api_key.strip():
        # Its own code: the phone says "not set up" only for this, never for an outage's 503.
        raise SpeechRefusedError(
            "Realtime voice is not configured",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="not_configured",
        )

    redis = get_redis_client()
    await require_speech_rate(
        redis,
        settings,
        f"speech_realtime_rl:{user.id}",
        quota_service.LIVE_TALK_RATE_LIMIT_MESSAGE,
    )
    await require_voice_spend_ok(redis, settings)

    reserved = await quota_service.reserve_live_talk_seconds(
        redis,
        user.id,
        allowance_seconds=quota_service.live_talk_allowance_seconds(user, settings),
        max_session_seconds=settings.live_talk_max_session_seconds,
        min_session_seconds=settings.live_talk_min_session_seconds,
    )
    if reserved <= 0:
        raise SpeechRefusedError(
            quota_service.LIVE_TALK_MINUTES_USED_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="live_talk_minutes_used",
        )
    return redis, reserved


@router.post("/live/session", response_model=RealtimeSessionOut)
async def create_realtime_session(
    body: RealtimeSessionIn,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> RealtimeSessionOut:
    """Mint a short-lived key; mobile completes WebRTC directly with OpenAI."""
    ctx = await _load_session_context_or_404(body.chat_id, user, settings)
    redis, reserved = await _reserve_realtime_or_raise(user, settings)

    try:
        result = await openai_speech_gateway.create_realtime_client_secret(
            settings,
            instructions=_realtime_instructions(
                ctx.history,
                memory_block=ctx.memory_block,
                schedule_block=ctx.schedule_block,
                custom_instructions=live_talk_service.voice_custom_instructions(user),
            ),
            safety_identifier=_safety_identifier(user),
            barge_in=body.barge_in,
            tools_enabled=body.tools_enabled,
            voice=user.tts_voice,
        )
    except BaseException:
        await quota_service.release_live_talk_seconds(redis, user.id, seconds=reserved)
        raise
    if result is None:
        await quota_service.release_live_talk_seconds(redis, user.id, seconds=reserved)
        raise SpeechRefusedError(
            "Could not start realtime voice", status_code=status.HTTP_502_BAD_GATEWAY
        )

    session_id = await live_talk_service.issue_realtime_session(
        redis, user.id, body.chat_id, reserved_seconds=reserved
    )
    # Also charges the reserved minutes to the global spend; /live/end settles both.
    await quota_service.record_live_talk_reservation(
        redis, user.id, session_id, reserved_seconds=reserved
    )
    return RealtimeSessionOut(
        client_secret=result.value,
        expires_at=result.expires_at,
        call_id=session_id,
        model=openai_speech_gateway.realtime_model(settings),
        max_duration_seconds=reserved,
    )


@router.post("/live/end", response_model=SpeechLiveStatusOut)
async def end_realtime_session(
    body: RealtimeEndIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
) -> SpeechLiveStatusOut:
    """The phone hung up: charge the time that passed, give back the rest.

    Idempotent. A session that is never reported keeps its full reservation.
    """
    if not settings.speech_live_talk_enabled or not settings.speech_realtime_voice_enabled:
        raise SpeechRefusedError(
            "Not available", status_code=status.HTTP_404_NOT_FOUND, code="not_available"
        )
    redis = get_redis_client()
    charged = await quota_service.settle_live_talk_session(redis, user.id, body.call_id)
    if charged is not None:
        await live_talk_service.close_realtime_session(redis, user.id, body.call_id)
    return await live_talk_service.live_talk_status(redis, user, settings)


async def _take_persist_slot_or_raise(redis: Redis, user: User, call_id: str) -> None:
    """Bound the rows and jobs a session can write: the phone posts the turns."""
    if not await allow_request_unless_down(
        redis,
        f"live_persist_rl:{user.id}",
        limit=quota_service.LIVE_TALK_SAVES_PER_MINUTE,
        window_seconds=60,
    ):
        raise SpeechRefusedError(
            quota_service.LIVE_TALK_RATE_LIMIT_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if not await quota_service.take_live_talk_save(redis, user.id, call_id):
        raise SpeechRefusedError(
            quota_service.LIVE_TALK_SAVES_USED_MESSAGE,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="live_talk_saves_used",
        )


@router.post("/live/persist")
async def persist_realtime_turn(
    body: RealtimePersistIn,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    if not settings.speech_live_talk_enabled or not settings.speech_realtime_voice_enabled:
        raise SpeechRefusedError(
            "Not available", status_code=status.HTTP_404_NOT_FOUND, code="not_available"
        )
    user_text = body.user_text.strip()
    assistant_text = body.assistant_text.strip()
    # Defense in depth: a Realtime assistant message is never a Recall turn
    # unless the mobile client first accepted a real user transcription.
    if not user_text:
        return Response(status_code=204)
    # A plan that ended mid-call stops saving on the next turn.
    _require_live_talk_plan(user, settings)

    redis = get_redis_client()
    await require_voice_spend_ok(redis, settings)
    # The session key lives for the reserved minutes (plus a short tail), so
    # this also ends saving once the session's time is up.
    bound_chat_id = await live_talk_service.realtime_session_bound_chat_id(
        redis, user.id, body.call_id
    )
    if bound_chat_id is None or bound_chat_id != body.chat_id:
        # Its own code: the phone ends the call in its words, never this English.
        raise SpeechRefusedError(
            "Realtime session is not active",
            status_code=status.HTTP_403_FORBIDDEN,
            code="live_talk_session_ended",
        )
    await _take_persist_slot_or_raise(redis, user, body.call_id)

    async with SessionLocal() as session:
        loaded = await live_talk_service.load_live_talk_history(
            session,
            chat_id=body.chat_id,
            user_id=user.id,
        )
    if loaded is None:
        raise SpeechRefusedError("Chat not found", status_code=status.HTTP_404_NOT_FOUND)
    _, untitled = loaded

    if body.turn_id and assistant_text:
        from app.modules.speech.live_talk_tools import search_sources_for_turn

        sources = await search_sources_for_turn(redis, user.id, body.call_id, body.turn_id)
        if sources:
            assistant_text += "\n\n```sources\n" + json.dumps(sources) + "\n```"

    user_message, assistant_message = await live_talk_service.persist_live_talk_turn(
        user=user,
        chat_id=body.chat_id,
        user_text=user_text,
        assistant_text=assistant_text,
        untitled=untitled,
        settings=settings,
        redis=redis,
        enqueue_jobs=True,
    )
    if body.return_messages:
        return JSONResponse(
            {
                "user_message": MessageOut.model_validate(user_message).model_dump(mode="json")
                if user_message
                else None,
                "assistant_message": MessageOut.model_validate(assistant_message).model_dump(
                    mode="json"
                )
                if assistant_message
                else None,
            }
        )
    return Response(status_code=204)


@router.post("/live/tool")
async def execute_realtime_tool(
    body: RealtimeToolIn,
    user: User = Depends(get_consented_user),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    from app.modules.conversation import history as chat_history
    from app.modules.speech.live_talk_tools import execute_tool

    if not settings.speech_live_talk_enabled or not settings.speech_realtime_voice_enabled:
        raise SpeechRefusedError("Not available", status_code=404, code="not_available")
    _require_live_talk_plan(user, settings)
    redis = get_redis_client()
    bound_chat = await redis.get(live_talk_service._realtime_session_key(user.id, body.call_id))
    if isinstance(bound_chat, bytes):
        bound_chat = bound_chat.decode()
    if bound_chat != str(body.chat_id):
        raise SpeechRefusedError("Realtime session is not active for this chat", status_code=403)
    if not await allow_request_unless_down(
        redis, f"live_tools:{user.id}", limit=20, window_seconds=60
    ):
        raise SpeechRefusedError("Voice lookups are temporarily rate limited", status_code=429)
    async with SessionLocal() as session:
        if await chat_history.get_chat(session, body.chat_id, user.id) is None:
            raise SpeechRefusedError("Chat not found", status_code=404)
    return await execute_tool(
        settings,
        redis,
        user=user,
        call_id=body.call_id,
        turn_id=body.turn_id,
        name=body.name,
        query=body.query,
    )
