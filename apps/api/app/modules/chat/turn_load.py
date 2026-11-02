"""What a turn reads before it runs: the user, the chat, quota, recent history and the model.

The prepare lock is already held. Both loads wait for the previous turn's save
first, so history never misses the reply before this one.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import consent, pool_liveness, user_cache
from app.core.aio import gather_or_cancel
from app.core.config import Settings
from app.exceptions import ChatNotFoundError, ConsentRequiredError
from app.models import model_catalog
from app.models.orm import Chat, User
from app.modules.chat.finalize_registry import wait_for_pending_finalize
from app.modules.chat.model_routing.route import last_user_turn
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_prep import RegenerateBackup
from app.modules.chat.turn_prep.mode import _TurnMode, classify_turn_mode
from app.modules.chat.turn_prep.reading import read_turn_message
from app.modules.chat.turn_settle import seed_usage_from_db
from app.modules.chat.turn_timing import TurnTimingTracker
from app.modules.turn_reading.lesson_flow import active_lesson_step
from app.services import model_health

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewTurn:
    user: User
    chat: Chat
    daily_limit: int
    recent: list[Any]
    prior_count: int
    turn_mode: _TurnMode
    model: str
    # Chat models whose breaker is open and cooling down; routing above skipped them.
    unhealthy: frozenset[str] = frozenset()
    # Open models past their cool-down: tried only by a turn that claims their probe.
    half_open: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RegenerateTurn:
    user: User
    chat: Chat
    model: str
    content: str
    prior_count: int
    turn_mode: _TurnMode
    backup: RegenerateBackup | None
    omit_message_ids: set[UUID] | None
    # The window read once here; the prompt reuses it (``omit_message_ids`` drops the
    # reply being replaced), and the model health read beside it.
    recent: list[Any]
    unhealthy: frozenset[str] = frozenset()


async def _prior_count_for_window(
    recent: list[Any],
    window: int,
    *,
    count_for_chat: Callable[[AsyncSession, UUID], Awaitable[int]],
    session: AsyncSession,
    chat_id: UUID,
) -> int:
    """Exact count only when the recent window is full (older rows may exist)."""
    if len(recent) < window:
        return len(recent)
    raw_count = await count_for_chat(session, chat_id)
    return raw_count if isinstance(raw_count, int) else len(recent)


async def _load_user(
    deps: ChatTurnDeps,
    timing: TurnTimingTracker,
    user_id: UUID,
    user: User | None,
    generation: str | None,
) -> User:
    """The transport's copy of the user, which it read under the account's current
    generation (``core/user_cache``), or the row read again.

    A copy can still trail a change whose generation never reached Redis, so a
    refusal reads the row first; a WebSocket turn keeps the row it read for the
    socket's next turn.
    """
    if user is not None and consent.has_ai_data_consent(user):
        timing.mark_phase("user_ready")
        return user
    loaded = await pool_liveness.run_unit(
        deps.session_factory, lambda session: deps.users.get_by_id(session, user_id)
    )
    if loaded is None:
        raise ChatNotFoundError("User not found.")
    _require_consent(loaded)
    if generation is not None:
        user_cache.remember_user(loaded, generation)
    timing.mark_phase("user_ready")
    return loaded


def _require_consent(user: User) -> None:
    """No turn sends anything to outside AI services before the account agreed.

    Raised before the user message is saved or quota is reserved, so the error
    frame says ``user_message_saved: false`` and the prepare lock is released.
    """
    if not consent.has_ai_data_consent(user):
        raise ConsentRequiredError()


async def _load_chat(
    deps: ChatTurnDeps,
    timing: TurnTimingTracker,
    *,
    chat_id: UUID,
    user_id: UUID,
    chat: Chat | None,
) -> Chat:
    if chat is not None:
        timing.mark_phase("chat_ready")
        return chat
    remembered = deps.chats.peek_recent_chat(chat_id, user_id)
    if remembered is not None:
        timing.mark_phase("chat_ready")
        return remembered
    loaded = await pool_liveness.run_unit(
        deps.session_factory, lambda session: deps.chats.get_by_id(session, chat_id, user_id)
    )
    if loaded is None:
        raise ChatNotFoundError("Chat not found.")
    timing.mark_phase("chat_ready")
    return loaded


async def _needs_usage_seed(
    deps: ChatTurnDeps, redis: Redis, timing: TurnTimingTracker, user_id: UUID, skip: bool
) -> bool:
    if skip:
        timing.mark_phase("quota_probe_ready")
        return False
    try:
        missing = not await deps.quota.has_daily_usage_key(redis, str(user_id))
    except Exception:
        # Unknown counts as missing: the turn re-reads today's total from the DB.
        logger.warning("Daily usage probe failed user_id=%s", user_id, exc_info=True)
        missing = True
    timing.mark_phase("quota_probe_ready")
    return missing


async def _load_account(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    timing: TurnTimingTracker,
    *,
    user_id: UUID,
    chat_id: UUID,
    user: User | None,
    user_generation: str | None,
    chat: Chat | None,
    skip_usage_seed: bool,
) -> tuple[User, int, Chat]:
    # User ownership, chat ownership, and the Redis quota probe are
    # independent. Live simulator timing showed the old user->chat serial DB
    # reads dominating this lane, so overlap them. Each DB read gets its own
    # AsyncSession; SQLAlchemy AsyncSession itself is intentionally not used
    # concurrently.
    loaded_user, loaded_chat, need_usage_seed = await gather_or_cancel(
        _load_user(deps, timing, user_id, user, user_generation),
        _load_chat(deps, timing, chat_id=chat_id, user_id=user_id, chat=chat),
        _needs_usage_seed(deps, redis, timing, user_id, skip_usage_seed),
    )
    if need_usage_seed:
        async with deps.session_factory() as session:
            await seed_usage_from_db(redis, session, user_id)
    timing.mark_phase("quota_seed_ready")
    limit = deps.quota.daily_limit_for_user(loaded_user, settings)
    timing.mark_phase("account_quota_ready")
    return loaded_user, limit, loaded_chat


async def _load_history_after_finalize(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    timing: TurnTimingTracker,
    chat_id: UUID,
) -> tuple[list[Any], int]:
    # History must observe the previous assistant commit, but it does not
    # depend on the current turn's user/chat lookup. Run both lanes
    # concurrently so a remote DB round trip is paid once in wall time, not
    # once for account/chat and again for recent messages.
    await wait_for_pending_finalize(chat_id, redis, require_complete=True)
    timing.mark_phase("previous_finalize_ready")
    window = settings.recent_message_window

    async def read(session: AsyncSession) -> tuple[list[Any], int]:
        recent = await deps.messages.list_recent(session, chat_id, limit=window)
        prior_count = await _prior_count_for_window(
            recent,
            window,
            count_for_chat=deps.messages.count_for_chat,
            session=session,
            chat_id=chat_id,
        )
        return recent, prior_count

    recent, prior_count = await pool_liveness.run_unit(deps.session_factory, read)
    timing.mark_phase("history_ready")
    return recent, prior_count


async def _load_history_and_read(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    timing: TurnTimingTracker,
    chat_id: UUID,
    content: str,
) -> tuple[list[Any], int]:
    """The recent window, then the message read off the loop with the line before it."""
    recent, prior_count = await _load_history_after_finalize(deps, redis, settings, timing, chat_id)
    await read_turn_message(content, recent, settings)
    return recent, prior_count


async def load_new_turn(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    timing: TurnTimingTracker,
    *,
    user_id: UUID,
    chat_id: UUID,
    content: str,
    model_alias: str | None,
    user: User | None,
    chat: Chat | None,
    skip_usage_seed: bool,
    user_generation: str | None = None,
) -> NewTurn:
    # Account/quota and history are independent once the previous turn is
    # committed: one wall-clock round trip for both. Every turn reads the window,
    # greetings too: a "hi" that skipped it was greeted afresh after a "hi" (and
    # after a whole conversation), since the prompt never saw what came before.
    load_account = partial(
        _load_account,
        deps,
        redis,
        settings,
        timing,
        user_id=user_id,
        chat_id=chat_id,
        user=user,
        user_generation=user_generation,
        chat=chat,
        skip_usage_seed=skip_usage_seed,
    )
    (
        (loaded_user, daily_limit, loaded_chat),
        (recent, prior_count),
        health,
    ) = await gather_or_cancel(
        load_account(),
        _load_history_and_read(deps, redis, settings, timing, chat_id, content),
        _model_breakers(redis, settings),
    )
    # Read from the window just loaded: "yes" after a question, or "make it shorter"
    # after a draft, used to read the messages again in a session of its own.
    turn_mode = classify_turn_mode(recent, content)
    prior_user, prior_model = last_user_turn(recent)
    model = deps.model_choice.resolve_user_model_override(
        loaded_user,
        model_alias,
        content,
        settings,
        prior_user=prior_user,
        prior_model=prior_model,
        lesson_active=active_lesson_step(recent) is not None,
        unhealthy=health.cooling,
    )
    timing.mark_phase("user_quota")
    return NewTurn(
        user=loaded_user,
        chat=loaded_chat,
        daily_limit=daily_limit,
        recent=recent,
        prior_count=prior_count,
        turn_mode=turn_mode,
        model=model,
        unhealthy=health.cooling,
        half_open=health.half_open,
    )


async def _model_breakers(redis: Redis, settings: Settings) -> model_health.Breakers:
    """The open breakers among the models a turn may run on, read beside the
    account (the pool needs the user, so every selectable model and the photo
    lanes are read). A half-open model is routed to like a healthy one; the turn
    claims its probe only right before it tries it (``stream_paths``)."""
    aliases = [model.id for model in model_catalog.selectable_models()]
    aliases += [model_catalog.vision_alias(), model_catalog.vision_backup_alias()]
    return await model_health.read_breakers(redis, settings, aliases)


async def load_regenerate_turn(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    *,
    user_id: UUID,
    chat_id: UUID,
    model_alias: str | None,
) -> RegenerateTurn:
    # Last-message reads must see the committed assistant. Overlapping that
    # load with wait_for_pending_finalize can regenerate from a stale last
    # row. New turns gather wait with user/quota instead — prepare reads
    # messages only after both finish.
    await wait_for_pending_finalize(chat_id, redis, require_complete=True)
    (user, chat, recent, prior_count, last_user), health = await gather_or_cancel(
        _read_regenerate_rows(deps, redis, settings, user_id=user_id, chat_id=chat_id),
        _model_breakers(redis, settings),
    )
    last = recent[-1]
    # A regenerate routes the line on its own (``resolve_regenerate_model``): no prior line.
    await read_turn_message(last_user.content, [], settings)
    model = deps.model_choice.resolve_regenerate_model(
        user, model_alias, last_user.content, last.model, settings
    )
    backup: RegenerateBackup | None = None
    omit_message_ids: set[UUID] | None = None
    if last.role == "assistant":
        backup = RegenerateBackup(content=last.content, model=last.model, message_id=last.id)
        omit_message_ids = {last.id}
    return RegenerateTurn(
        user=user,
        chat=chat,
        model=model,
        content=last_user.content,
        prior_count=prior_count,
        # The window still ends with the reply being redone; the line answered the one
        # before it ("yes" to "Want me to set that reminder?").
        turn_mode=classify_turn_mode(
            recent[:-1] if last.role == "assistant" else recent, last_user.content
        ),
        backup=backup,
        omit_message_ids=omit_message_ids,
        recent=recent,
        unhealthy=health.cooling,
    )


async def _read_regenerate_rows(
    deps: ChatTurnDeps, redis: Redis, settings: Settings, *, user_id: UUID, chat_id: UUID
) -> tuple[User, Chat, list[Any], int, Any]:
    """The user, the chat, the recent window and the count, in one session (run again on
    a new connection when its first statement finds the pooled one dead).

    The last message and the last user message come from the window; it used to read
    the messages four to six times. A lost usage counter is re-read in the same session.
    """
    window = settings.recent_message_window

    async def read(session: AsyncSession) -> tuple[User, Chat, list[Any], int, Any]:
        user = await deps.users.get_by_id(session, user_id)
        if user is None:
            raise ChatNotFoundError("User not found.")
        _require_consent(user)
        chat = await deps.chats.get_by_id(session, chat_id, user_id)
        if chat is None:
            raise ChatNotFoundError("Chat not found.")
        recent = await deps.messages.list_recent(session, chat_id, limit=window)
        if not recent:
            raise ChatNotFoundError("No messages to regenerate.")
        last_user = next((m for m in reversed(recent) if m.role == "user"), None)
        if last_user is None:
            # A window of replies only (rare): the user's line is further back.
            last_user = await deps.messages.get_last_user(session, chat_id)
        if last_user is None:
            raise ChatNotFoundError("No user message to regenerate from.")
        prior_count = await _prior_count_for_window(
            recent,
            window,
            count_for_chat=deps.messages.count_for_chat,
            session=session,
            chat_id=chat_id,
        )
        # Last, so a failed read here (logged, not raised) cannot cut the reads above.
        await seed_usage_from_db(redis, session, user_id)
        return user, chat, recent, prior_count, last_user

    return await pool_liveness.run_unit(deps.session_factory, read)
