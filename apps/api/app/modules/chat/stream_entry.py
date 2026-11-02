"""A chat turn from the transports' side: a new message, or a regenerated reply.

Each turn holds its prepare lock and quota (``turn_resources``), reads what it needs
(``turn_load``), may be answered by a photo or a picture (``turn_intercepts``),
and otherwise streams through ``stream_pipeline``. ``turn_resources`` keeps the
prepare lock alive on its own task, so a Redis blip never cuts a stream or skips
its save. ``deps`` is what a turn uses outside the chat module (``turn_deps``); the
transports pass ``default_deps()``.
"""

import logging
from collections.abc import AsyncIterator, Callable
from uuid import UUID

from redis.asyncio import Redis

from app.core import readings
from app.core.config import Settings
from app.exceptions import ChatNotFoundError
from app.models.orm import Attachment, Chat, User
from app.modules.account import profile as profile_service
from app.modules.attachments.markers import image_attachment_ids_from_text
from app.modules.billing import plan as plan_service
from app.modules.chat.model_routing.thinking import thinking_level
from app.modules.chat.stream_pipeline import stream_and_finalize
from app.modules.chat.stream_status import StreamReasoningFn, StreamStatusFn
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_intercepts import (
    intercept_new_turn,
    intercept_regenerate,
    start_reply_picture,
)
from app.modules.chat.turn_load import (
    NewTurn,
    RegenerateTurn,
    load_new_turn,
    load_regenerate_turn,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import (
    StreamContext,
    TurnRequest,
    await_user_message_persist,
    build_stream_prompt_context,
    count_images,
    load_attachment_rows,
    prepare_chat_turn,
    stream_context_from_bundle,
    vision_reserve_tokens,
)
from app.modules.chat.turn_prep.regenerate_vision import inject_regenerated_image_content
from app.modules.chat.turn_resources import (
    TurnResources,
    top_up_reserve_for_prompt,
    turn_resources,
    wrap_stream_status,
)
from app.modules.chat.turn_timing import TurnTimingTracker
from app.modules.chat.turn_trace import traced_turn

logger = logging.getLogger(__name__)


async def _reserve_new_turn(
    deps: ChatTurnDeps,
    res: TurnResources,
    settings: Settings,
    turn: NewTurn,
    *,
    content: str,
    attachment_ids: list[UUID] | None,
) -> list[Attachment] | None:
    """The soft quota check; a borrowed reservation is already made. Returns the attached
    rows it read to count the images, which the turn then reads its files from."""
    if res.reserved_tokens > 0:
        return None
    rows: list[Attachment] | None = None
    if attachment_ids:
        async with deps.session_factory() as session:
            rows = await load_attachment_rows(session, turn.user.id, attachment_ids)
    vision_extra = vision_reserve_tokens(settings, count_images(rows or []))
    await res.reserve(
        user=turn.user,
        content=content,
        model=turn.model,
        settings=settings,
        daily_limit=turn.daily_limit,
        vision_extra=vision_extra,
        max_output=settings.max_output_tokens,
    )
    return rows


async def _end_new_turn(ctx: StreamContext, chat_id: UUID) -> None:
    """A turn that failed before its reply saved draws nothing; the user's row still lands."""
    if ctx.reply_picture is not None:
        ctx.reply_picture.cancel()
    try:
        await await_user_message_persist(ctx)
    except Exception:
        logger.exception("User message persist failed chat_id=%s", chat_id)


def _regenerate_images(
    turn: RegenerateTurn, settings: Settings, model_alias: str | None
) -> tuple[list[UUID], str]:
    """The photos the message being answered again carries, and the model that reads them.

    Persisted image markers identify the current input on regeneration; unlike a new
    send, this path does not run prepare_chat_turn.
    """
    image_ids = image_attachment_ids_from_text(turn.content) if settings.attachments_enabled else []
    if not image_ids:
        return image_ids, turn.model
    explicit = plan_service.is_explicit_pick(model_alias)
    return image_ids, plan_service.image_turn_model(
        turn.user, settings, turn.model, explicit=explicit
    )


@traced_turn("new")
async def stream_chat_response(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    content: str,
    model_alias: str | None = None,
    attachment_ids: list[UUID] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    outcome: TurnOutcome | None = None,
    client_timezone: str | None = None,
    client_location: str | None = None,
    client_latitude: float | None = None,
    client_longitude: float | None = None,
    on_status: StreamStatusFn | None = None,
    on_reasoning: StreamReasoningFn | None = None,
    user: User | None = None,
    user_generation: str | None = None,
    chat: Chat | None = None,
    skip_usage_seed: bool = False,
    resources: TurnResources | None = None,
) -> AsyncIterator[str]:
    """``user``: the transport's current copy of the user, if any; ``user_generation``: the
    generation it read (``core/user_cache``), under which a row read instead is kept."""
    content = content.strip()
    if not content and not attachment_ids:
        raise ChatNotFoundError("Message cannot be empty.")
    readings.begin_turn()
    timing = TurnTimingTracker()
    timing.mark_phase("turn_start")
    status = wrap_stream_status(timing, on_status)

    async with turn_resources(
        deps, redis, user_id=user_id, chat_id=chat_id, borrowed=resources
    ) as res:
        turn = await load_new_turn(
            deps,
            redis,
            settings,
            timing,
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            model_alias=model_alias,
            user=user,
            user_generation=user_generation,
            chat=chat,
            skip_usage_seed=skip_usage_seed,
        )
        # The user's own switches (web search off) narrow the server's for this turn.
        settings = profile_service.settings_for_user(settings, turn.user)
        misses: set[str] = set()
        if not attachment_ids and await intercept_new_turn(
            deps,
            settings,
            user=turn.user,
            chat_id=chat_id,
            content=content,
            outcome=outcome,
            recent_messages=turn.recent,
            prior_count=turn.prior_count,
            misses=misses,
            on_status=status,
        ):
            await res.refund()
            return
        timing.mark_phase("image_gen")
        rows = await _reserve_new_turn(
            deps, res, settings, turn, content=content, attachment_ids=attachment_ids
        )
        ctx = await prepare_chat_turn(
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            model_alias=model_alias,
            settings=settings,
            redis=redis,
            reserved_tokens=res.reserved_tokens,
            attachment_ids=attachment_ids or [],
            attachment_rows=rows,
            client_timezone=client_timezone,
            client_location=client_location,
            client_latitude=client_latitude,
            client_longitude=client_longitude,
            on_status=status,
            user=turn.user,
            timing=timing,
            chat=turn.chat,
            turn_mode=turn.turn_mode,
            prior_count=turn.prior_count,
            recent_messages=turn.recent,
            resolved_model=turn.model,
            on_user_saved=outcome.mark_user_message_saved if outcome is not None else None,
            unhealthy=turn.unhealthy,
            half_open=turn.half_open,
        )
        ctx.photo_missed = "photo" in misses
        try:
            ctx.reply_picture = start_reply_picture(
                deps, settings, user=turn.user, chat_id=chat_id, content=content
            )
            await top_up_reserve_for_prompt(
                res, settings=settings, ctx=ctx, daily_limit=turn.daily_limit
            )
            async for token in stream_and_finalize(
                deps,
                redis,
                settings,
                ctx,
                should_cancel=should_cancel,
                outcome=outcome,
                on_status=status,
                on_reasoning=on_reasoning,
                resources=res,
            ):
                yield token
        finally:
            await _end_new_turn(ctx, chat_id)


@traced_turn("regenerate")
async def stream_regenerate_response(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    model_alias: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
    outcome: TurnOutcome | None = None,
    client_timezone: str | None = None,
    client_location: str | None = None,
    client_latitude: float | None = None,
    client_longitude: float | None = None,
    on_status: StreamStatusFn | None = None,
    on_reasoning: StreamReasoningFn | None = None,
) -> AsyncIterator[str]:
    readings.begin_turn()
    timing = TurnTimingTracker()
    timing.mark_phase("turn_start")
    status = wrap_stream_status(timing, on_status)
    async with turn_resources(deps, redis, user_id=user_id, chat_id=chat_id) as res:
        turn = await load_regenerate_turn(
            deps, redis, settings, user_id=user_id, chat_id=chat_id, model_alias=model_alias
        )
        if outcome is not None:
            outcome.mark_user_message_saved()  # The message answered again just loaded.
        settings = profile_service.settings_for_user(settings, turn.user)
        misses: set[str] = set()
        if await intercept_regenerate(
            deps,
            settings,
            user=turn.user,
            chat_id=chat_id,
            content=turn.content,
            backup=turn.backup,
            outcome=outcome,
            misses=misses,
            on_status=status,
        ):
            return
        current_image_ids, model = _regenerate_images(turn, settings, model_alias)
        await res.reserve(
            user=turn.user,
            content=turn.content,
            model=model,
            settings=settings,
            max_output=settings.max_output_tokens,
            vision_extra=vision_reserve_tokens(settings, len(current_image_ids)),
        )
        request = TurnRequest(
            user_id=user_id,
            chat_id=chat_id,
            content=turn.content,
            model=model,
            client_timezone=client_timezone,
            client_location=client_location,
            client_latitude=client_latitude,
            client_longitude=client_longitude,
            on_status=status,
            user=turn.user,
            chat=turn.chat,
            timing=timing,
            omit_message_ids=turn.omit_message_ids,
            turn_mode=turn.turn_mode,
            has_image_attachment=bool(current_image_ids),
            recent_messages=turn.recent,
            prior_count=turn.prior_count,
            unhealthy_models=turn.unhealthy,
        )
        bundle = await build_stream_prompt_context(request, settings, redis)
        if current_image_ids:
            await inject_regenerated_image_content(
                bundle.prompt_messages,
                settings=settings,
                user_id=user_id,
                attachment_ids=current_image_ids,
            )
        ctx = stream_context_from_bundle(
            bundle,
            user_id=user_id,
            chat_id=chat_id,
            model=model,
            user_message_content=turn.content,
            reserved_tokens=res.reserved_tokens,
            user=turn.user,
            prior_count=turn.prior_count,
            timing=timing,
            run_title=False,
            skip_memory_jobs=False,
            regenerate_backup=turn.backup,
            # The earlier reply's model (or the user's pick) runs whatever its health.
            model_named=True,
            # Regenerating says the answer was not good enough: one level more.
            thinking=thinking_level(turn.content, regenerate=True, settings=settings),
        )
        ctx.photo_missed = "photo" in misses
        await top_up_reserve_for_prompt(
            res,
            settings=settings,
            ctx=ctx,
            daily_limit=deps.quota.daily_limit_for_user(turn.user, settings),
        )
        ctx.reply_picture = start_reply_picture(
            deps, settings, user=turn.user, chat_id=chat_id, content=turn.content
        )
        try:
            async for token in stream_and_finalize(
                deps,
                redis,
                settings,
                ctx,
                should_cancel=should_cancel,
                outcome=outcome,
                on_status=status,
                on_reasoning=on_reasoning,
                resources=res,
            ):
                yield token
        finally:
            if ctx.reply_picture is not None:
                ctx.reply_picture.cancel()
