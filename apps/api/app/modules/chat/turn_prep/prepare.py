"""Prepare a new chat turn: attachments, the user's row, the prompt, then its images.

When the caller has already read the user, chat, turn mode, message count and
history, the user's row is saved beside the prompt build and the stream awaits it
before the model is asked (``await_user_message_persist``). Otherwise the save goes
first and reads them.
"""

import asyncio
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.ids import uuid7
from app.exceptions import ChatNotFoundError
from app.models.orm import Attachment, Chat, User
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing.route import last_user_turn
from app.modules.chat.model_routing.thinking import thinking_level
from app.modules.chat.stream_status import StreamStatusFn
from app.modules.chat.turn_prep.attachments import _process_attachments
from app.modules.chat.turn_prep.context import (
    StreamContext,
    TurnPromptBundle,
    build_stream_prompt_context,
    stream_context_from_bundle,
)
from app.modules.chat.turn_prep.mode import _TurnMode
from app.modules.chat.turn_prep.persist import (
    UserTurn,
    image_model,
    persist_user_turn,
    turn_model,
)
from app.modules.chat.turn_prep.request import TurnRequest
from app.modules.chat.turn_prep.vision import inject_turn_images
from app.modules.chat.turn_timing import TurnTimingTracker
from app.modules.turn_reading.lesson_flow import active_lesson_step
from app.services.prompt_safety import messages_have_attachment_marker

logger = logging.getLogger(__name__)


async def prepare_chat_turn(
    *,
    user_id: UUID,
    chat_id: UUID,
    content: str,
    model_alias: str | None,
    settings: Settings,
    redis: Redis,
    reserved_tokens: int,
    attachment_ids: list[UUID] | None = None,
    attachment_rows: list[Attachment] | None = None,
    client_timezone: str | None = None,
    client_location: str | None = None,
    client_latitude: float | None = None,
    client_longitude: float | None = None,
    on_status: StreamStatusFn | None = None,
    user: User | None = None,
    timing: TurnTimingTracker | None = None,
    chat: Chat | None = None,
    turn_mode: _TurnMode | None = None,
    prior_count: int | None = None,
    recent_messages: list[Any] | None = None,
    resolved_model: str | None = None,
    on_user_saved: Callable[[], None] | None = None,
    unhealthy: frozenset[str] | None = None,
    half_open: frozenset[str] = frozenset(),
) -> StreamContext:
    """``on_user_saved`` runs once the user's row has committed (an error after
    that point must not offer to resend the message). ``unhealthy`` and
    ``half_open`` are the model health the load read (None: read it again for
    the backups)."""
    attachments = await _process_attachments(
        user_id=user_id,
        user=user,
        content=content,
        attachment_ids=attachment_ids,
        settings=settings,
        redis=redis,
        on_status=on_status,
        rows=attachment_rows,
    )
    if attachments.resolved_attachment_ids is not None:
        attachment_ids = attachments.resolved_attachment_ids
    content = attachments.content
    turn = UserTurn(
        user_id=user_id,
        chat_id=chat_id,
        message_id=uuid7(),
        content=content,
        stored_content=attachments.user_content,
        attachment_ids=attachment_ids,
        has_image_attachment=attachments.has_image_attachment,
        model_alias=model_alias,
        recent_messages=recent_messages,
        lesson_active=active_lesson_step(recent_messages) is not None,
        user=attachments.user,
        chat=chat,
        model=resolved_model,
        prior_count=prior_count,
        turn_mode=turn_mode,
        unhealthy=unhealthy,
    )
    history = await _history_or_saved(turn, settings, timing, on_user_saved)
    if turn.user is None or turn.model is None:
        raise ChatNotFoundError("User not found.")
    request = TurnRequest(
        user_id=user_id,
        chat_id=chat_id,
        content=content,
        model=turn.model,
        client_timezone=client_timezone,
        client_location=client_location,
        client_latitude=client_latitude,
        client_longitude=client_longitude,
        has_image_attachment=attachments.has_image_attachment,
        image_math_extract=attachments.image_math_extract,
        on_status=on_status,
        user=turn.user,
        chat=turn.chat,
        timing=timing,
        force_rich_context=attachments.has_document_attachment,
        turn_mode=turn.turn_mode,
        probe_attachment_rag=_probe_attachment_rag(turn, history, settings),
        recent_messages=history,
        prior_count=turn.prior_count if history is not None else None,
        current_user_message_id=turn.message_id,
        unhealthy_models=unhealthy,
        half_open_models=half_open,
    )
    persist: asyncio.Task[None] | None = None
    if history is None:
        bundle = await build_stream_prompt_context(request, settings, redis)
    else:
        bundle, persist = await _build_beside_persist(request, turn, settings, redis, on_user_saved)
    if await inject_turn_images(
        bundle.prompt_messages, attachments, caption=content, settings=settings, user=turn.user
    ):
        _route_to_vision(turn, turn.user, turn.model, bundle, settings)
    return _stream_context(
        bundle,
        turn,
        settings,
        reserved_tokens=reserved_tokens,
        timing=timing,
        persist=persist,
    )


async def _history_or_saved(
    turn: UserTurn,
    settings: Settings,
    timing: TurnTimingTracker | None,
    on_user_saved: Callable[[], None] | None,
) -> list[Any] | None:
    """The history the prompt is built from beside the user's save, or None after saving.

    When the caller read everything the save would, the model is settled and the
    pending row closes the history; otherwise the save goes first and reads them.
    """
    if (
        turn.user is not None
        and turn.chat is not None
        and turn.turn_mode is not None
        and turn.prior_count is not None
        and turn.recent_messages is not None
    ):
        turn.model = turn_model(turn, turn.user, settings)
        pending = SimpleNamespace(id=turn.message_id, role="user", content=turn.stored_content)
        return [*turn.recent_messages, pending]
    await _persist_and_report(turn, settings, timing, on_user_saved)
    return None


def _route_to_vision(
    turn: UserTurn, user: User, model: str, bundle: TurnPromptBundle, settings: Settings
) -> None:
    """An earlier photo went back in: the model and its backups must read it."""
    turn.model = image_model(turn, user, settings, model)
    bundle.fallback_models = plan_service.chat_fallback_models(
        user, settings, turn.model, unhealthy=turn.unhealthy or frozenset(), needs_vision=True
    )


def _probe_attachment_rag(turn: UserTurn, history: list[Any] | None, settings: Settings) -> bool:
    """Whether the prompt build looks for attachment excerpts.

    Always with files on this turn. Beside the save, the build sees the caller's
    window, so it looks when that window shows a file marker or older messages fall
    outside it; after the save, any earlier message is reason to look.
    """
    if turn.attachment_ids:
        return True
    prior_count = turn.prior_count or 0
    if history is None:
        return prior_count > 0
    return messages_have_attachment_marker(history) or prior_count >= settings.recent_message_window


async def _persist_and_report(
    turn: UserTurn,
    settings: Settings,
    timing: TurnTimingTracker | None,
    on_saved: Callable[[], None] | None,
) -> None:
    await persist_user_turn(turn, settings, timing)
    if on_saved is not None:
        on_saved()


async def _build_beside_persist(
    request: TurnRequest,
    turn: UserTurn,
    settings: Settings,
    redis: Redis,
    on_saved: Callable[[], None] | None,
) -> tuple[TurnPromptBundle, asyncio.Task[None]]:
    """Build the prompt while the user's row saves; the stream awaits the save
    before the model is asked (``stream_and_finalize``).

    A failed or cancelled build still waits for the save, so what the user sent is kept.
    """
    persist = asyncio.create_task(_persist_and_report(turn, settings, request.timing, on_saved))
    try:
        bundle = await build_stream_prompt_context(request, settings, redis)
    except BaseException:
        try:
            await persist
        except Exception:
            logger.exception(
                "User message persist failed after prompt error chat_id=%s", turn.chat_id
            )
        raise
    return bundle, persist


def _first_reply(recent: list[Any] | None, prior_count: int) -> bool:
    """No reply in the chat yet: this turn's names it (the ``topic`` job).

    A first message stopped before any text saves no reply and queues no title,
    so the reply after it is the chat's first. Older rows than the window hold
    are taken to include one.
    """
    if prior_count == 0:
        return True
    if recent is None or len(recent) < prior_count:
        return False
    return not any(getattr(message, "role", None) == "assistant" for message in recent)


def _stream_context(
    bundle: TurnPromptBundle,
    turn: UserTurn,
    settings: Settings,
    *,
    reserved_tokens: int,
    timing: TurnTimingTracker | None,
    persist: asyncio.Task[None] | None,
) -> StreamContext:
    user, model, prior_count = turn.user, turn.model, turn.prior_count
    if user is None or turn.chat is None or model is None or prior_count is None:
        raise ChatNotFoundError("Turn context incomplete.")
    prior_user, prior_model = last_user_turn(turn.recent_messages)
    return stream_context_from_bundle(
        bundle,
        user_id=turn.user_id,
        chat_id=turn.chat_id,
        model=model,
        user_message_content=turn.content,
        reserved_tokens=reserved_tokens,
        user=user,
        prior_count=prior_count,
        timing=timing,
        user_message_persist=persist,
        run_title=_first_reply(turn.recent_messages, prior_count),
        # The user's own pick runs whatever its health; Auto's claims its probe.
        model_named=plan_service.is_explicit_pick(turn.model_alias) and model == turn.model_alias,
        thinking=thinking_level(
            turn.content,
            prior_user=prior_user,
            prior_model=prior_model,
            lesson_active=turn.lesson_active,
            settings=settings,
        ),
    )
