import asyncio
import contextlib
import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.background_tasks import create_background_task
from app.core.config import Settings
from app.exceptions import (
    ChatBusyError,
    QuotaExceededError,
    RedisUnavailableError,
    SpendCapReachedError,
)
from app.models import model_catalog
from app.models.orm import User
from app.modules.chat.context_window import estimate_tokens
from app.modules.chat.stream_status import StreamStatusFn
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_timing import TurnTimingTracker
from app.services.quota import CHAT_SPEND_CAP_MESSAGE, quota_exceeded_message

logger = logging.getLogger(__name__)

# The refresh is the owner's heartbeat: a machine that dies mid-turn leaves the
# lock for at most one TTL (the phone's next send gets ``busy`` until then), so
# it stays short and is refreshed three times a TTL.
CHATPREP_LOCK_TTL_SECONDS = 30
CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS = 10.0


@dataclass
class TurnResources:
    """Prepare-lock and quota ownership for one chat turn.

    ``reserved_tokens`` is held from ``reserve`` until finalize settles it to
    the turn's actual usage (``ctx.reserved_tokens`` carries the same number).
    An exception that leaves ``turn_resources`` refunds it, so a path that
    settles the reservation itself must not let an exception escape after.
    """

    deps: ChatTurnDeps
    redis: Redis
    user_id: UUID
    chat_id: UUID
    lock_key: str
    lock_token: str
    reserved_tokens: int = 0
    _refunded: bool = False

    async def reserve(
        self,
        *,
        user: User,
        content: str,
        model: str,
        settings: Settings,
        daily_limit: int | None = None,
        max_output: int | None = None,
        vision_extra: int = 0,
    ) -> int:
        self.reserved_tokens = await reserve_turn_quota(
            self.deps,
            self.redis,
            user=user,
            content=content,
            model=model,
            settings=settings,
            daily_limit=daily_limit,
            max_output=max_output,
            vision_extra=vision_extra,
        )
        return self.reserved_tokens

    async def refund(self) -> None:
        if self._refunded or self.reserved_tokens <= 0:
            return
        self._refunded = True
        # Marked refunded, it is never tried again: it runs to the end even when a
        # Stop cancels the turn meanwhile.
        refunding = create_background_task(
            self.deps.quota.refund_usage(self.redis, str(self.user_id), self.reserved_tokens),
            name="turn_quota_refund",
        )
        await asyncio.shield(refunding)

    def mark_settled(self) -> None:
        """The turn's finalize now settles the reservation (actual usage, or its
        own refund on failure); an exception escaping later must not refund it too."""
        self._refunded = True


async def acquire_chatprep_lock(deps: ChatTurnDeps, redis: Redis, chat_id: UUID) -> tuple[str, str]:
    """The chat's prepare lock: ``busy`` when another turn holds it, ``unavailable`` when
    Redis cannot say. The client's own error reached the transports, which answered it
    "Something went wrong", so the phone took an outage for a failed reply."""
    lock_key = f"chatprep:{chat_id}"
    try:
        token = await deps.locks.acquire_lock(redis, lock_key, CHATPREP_LOCK_TTL_SECONDS)
    except (RedisError, OSError) as exc:
        logger.warning(
            "Chat prepare lock unreadable; failing closed key=%s", lock_key, exc_info=True
        )
        raise RedisUnavailableError() from exc
    if token is None:
        raise ChatBusyError()
    return lock_key, token


@asynccontextmanager
async def turn_resources(
    deps: ChatTurnDeps,
    redis: Redis,
    *,
    user_id: UUID,
    chat_id: UUID,
    borrowed: TurnResources | None = None,
) -> AsyncIterator[TurnResources]:
    if borrowed is not None:
        yield borrowed
        return

    lock_key, lock_token = await acquire_chatprep_lock(deps, redis, chat_id)
    resources = TurnResources(
        deps=deps,
        redis=redis,
        user_id=user_id,
        chat_id=chat_id,
        lock_key=lock_key,
        lock_token=lock_token,
    )
    refresh_task = asyncio.create_task(
        chatprep_refresh_loop(resources),
        name="chatprep-refresh",
    )
    try:
        yield resources
    except BaseException:
        await resources.refund()
        raise
    finally:
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await refresh_task
        await deps.locks.release_lock(redis, lock_key, lock_token)


async def _refresh_chatprep_lock(res: TurnResources) -> bool:
    return await res.deps.locks.refresh_lock(
        res.redis,
        res.lock_key,
        res.lock_token,
        CHATPREP_LOCK_TTL_SECONDS,
    )


async def chatprep_refresh_loop(res: TurnResources) -> None:
    """Keep the prepare lock alive for the whole turn, through Redis blips.

    A failed or refused refresh is logged and retried on the next tick: it
    must never end the turn, whose reply is streaming and still has to save.
    """
    try:
        while True:
            await asyncio.sleep(CHATPREP_LOCK_REFRESH_INTERVAL_SECONDS)
            try:
                if not await _refresh_chatprep_lock(res):
                    logger.warning("Chat prepare lock no longer held key=%s", res.lock_key)
            except Exception:
                logger.warning(
                    "Chat prepare lock refresh failed key=%s", res.lock_key, exc_info=True
                )
    except asyncio.CancelledError:
        return


def wrap_stream_status(
    timing: TurnTimingTracker | None,
    on_status: StreamStatusFn | None,
) -> StreamStatusFn | None:
    if timing is None and on_status is None:
        return None

    async def emit(phase: str, detail: str | None = None, *, elapsed_ms: int | None = None) -> None:
        if timing is not None:
            timing.mark_phase(phase)
        if on_status is not None:
            await on_status(phase, detail, elapsed_ms=elapsed_ms)

    return emit


def weighted_reserve_tokens(
    *,
    content: str,
    model: str,
    settings: Settings,
    max_output: int | None = None,
    vision_extra: int = 0,
) -> int:
    base = estimate_tokens(content) + (
        max_output if max_output is not None else settings.max_output_tokens
    )
    base += vision_extra
    return math.ceil(base * model_catalog.quota_multiplier(model))


def prompt_weighted_reserve_tokens(
    prompt_messages: list[dict[str, Any]],
    *,
    model: str,
    settings: Settings,
    max_output: int | None = None,
) -> int:
    prompt_tokens = sum(
        estimate_tokens(content)
        for message in prompt_messages
        if isinstance((content := message.get("content")), str)
    )
    base = prompt_tokens + (max_output if max_output is not None else settings.max_output_tokens)
    return math.ceil(base * model_catalog.quota_multiplier(model))


async def top_up_reserve_for_prompt(
    res: TurnResources,
    *,
    settings: Settings,
    ctx: StreamContext,
    daily_limit: int,
) -> None:
    """Grow the reservation to the assembled prompt's estimate, as far as today allows.

    Never refuses: the turn already holds a reservation and its context work
    is done. Finalize settles to actual usage and clips the counter at the limit.
    """
    messages = ctx.prompt_messages
    if res.reserved_tokens <= 0 or not isinstance(messages, list):
        ctx.reserved_tokens = res.reserved_tokens
        return
    needed = prompt_weighted_reserve_tokens(
        messages,
        model=ctx.model,
        settings=settings,
        max_output=ctx.max_output_tokens,
    )
    extra = needed - res.reserved_tokens
    if extra > 0:
        res.reserved_tokens += await _reserve_up_to(
            res.deps, res.redis, res.user_id, extra, daily_limit=daily_limit
        )
    ctx.reserved_tokens = res.reserved_tokens


async def _reserve_up_to(
    deps: ChatTurnDeps, redis: Redis, user_id: UUID, wanted: int, *, daily_limit: int
) -> int:
    """``reserve_usage_up_to`` for a turn; what Redis grants after the turn is cancelled
    goes back.

    A Stop can cancel the turn while Redis answers: the grant then sat in the day's
    total with no turn holding it, and nothing refunded it.
    """
    reserving = asyncio.ensure_future(
        deps.quota.reserve_usage_up_to(redis, str(user_id), wanted, daily_limit=daily_limit)
    )
    try:
        return await asyncio.shield(reserving)
    except asyncio.CancelledError:
        create_background_task(
            _give_back(deps, redis, user_id, reserving), name="turn_quota_give_back"
        )
        raise


async def _give_back(
    deps: ChatTurnDeps, redis: Redis, user_id: UUID, reserving: asyncio.Future[int]
) -> None:
    try:
        granted = await reserving
    except Exception:
        return  # A reserve that failed took nothing (it logs its own failure).
    try:
        await deps.quota.refund_usage(redis, str(user_id), granted)
    except Exception:
        logger.warning("Stopped turn's tokens not given back user_id=%s", user_id, exc_info=True)


async def reserve_turn_quota(
    deps: ChatTurnDeps,
    redis: Redis,
    *,
    user: User,
    content: str,
    model: str,
    settings: Settings,
    daily_limit: int | None = None,
    max_output: int | None = None,
    vision_extra: int = 0,
) -> int:
    """Refuse a turn the global spend cap or today's token budget cannot cover.

    Returns the tokens reserved: this turn's estimate (the message plus the
    turn's max output, weighted by the model's multiplier) or, near the cap,
    whatever is left. Concurrent turns in different chats share that one
    remaining budget, so thirty open chats cannot each start against the
    same last thousand tokens. A turn that starts below the limit still
    finishes whole: its max output is not cut to the reservation (a lesson
    or a page of code would stop mid-fence), and finalize clips the counter
    at the limit, so one turn is the most a user can go over.

    When Redis had lost today's total, the turn read it back from the DB as it
    loaded (``turn_load``).
    """
    if await deps.quota.global_spend_exceeded(redis, settings):
        raise SpendCapReachedError(CHAT_SPEND_CAP_MESSAGE)
    if daily_limit is None:
        daily_limit = deps.quota.daily_limit_for_user(user, settings)
    wanted = weighted_reserve_tokens(
        content=content,
        model=model,
        settings=settings,
        max_output=max_output,
        vision_extra=vision_extra,
    )
    reserved = await _reserve_up_to(deps, redis, user.id, wanted, daily_limit=daily_limit)
    if reserved <= 0:
        raise QuotaExceededError(quota_exceeded_message(user))
    return reserved
