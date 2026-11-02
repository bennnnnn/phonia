"""Build and dispatch Expo push notifications for reminders.

Delivery semantics (do not conflate ticket accept with receipt polling):

- **Delivered** — set when Expo accepts a push ticket (`status: ok` on send). That is
  when we mark todos as sent.
- **Receipt polling** — deferred (see ``RECEIPT_MIN_AGE_SECONDS``) and used only to
  prune invalid device tokens. A missing or slow receipt must never block delivery
  marking or cause a resend on the next scheduler cycle.
- **Holds** — a send Expo may have accepted, throttled, refused or failed on its side
  holds its reminders (``send_backoff``) instead of going again next minute.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.gateways import expo_push_gateway
from app.gateways.expo_push_gateway import HoldReason, PushSendResult
from app.models.orm import PushToken, TodoItem
from app.modules.notifications.send_backoff import SendBackoff, occurrence_key
from app.modules.todos import (
    PUSH_REMINDERS,
    aged_out_unsent,
    due_reminder_page,
    is_due_now,
    mark_reminder_pushed,
    reminder_page_key,
)
from app.repositories import push_tokens as push_repo
from app.services.reminder_timing import OVERDUE_MAX_HOURS, reminder_title

logger = logging.getLogger(__name__)

RECEIPT_PENDING_ZSET = "phonia:push:receipts:pending"
RECEIPT_MIN_AGE_SECONDS = 15 * 60
RECEIPT_MAX_AGE_SECONDS = 24 * 60 * 60
# Receipts polled per batch, and tickets kept at most (the oldest go past it). A pass
# polls batches until its time budget (``push_receipt_poll_budget_seconds``).
RECEIPT_POLL_BATCH = 1_000
RECEIPT_PENDING_MAX = 50_000
# Due to-dos read per page; a cycle reads pages until its time budget
# (``reminder_cycle_budget_seconds``) and the rest come next minute.
PUSH_PAGE_ROWS = 500
# Delivered at once, waking an Android phone in Doze; a reminder is the point of a push.
PUSH_PRIORITY = "high"


@dataclass
class OutboundPush:
    message: dict[str, Any]
    todos: list[TodoItem] = field(default_factory=list)


def _receipt_token_key(ticket_id: str) -> str:
    return f"phonia:push:receipt:token:{ticket_id}"


def _redis_str_members(raw: list[object]) -> list[str]:
    ids: list[str] = []
    for item in raw:
        if isinstance(item, bytes):
            ids.append(item.decode())
        elif isinstance(item, str):
            ids.append(item)
    return ids


async def enqueue_push_receipts(redis: Redis, tickets: list[tuple[str, str]]) -> None:
    """Queue Expo ticket ids for deferred receipt polling (token pruning only)."""
    if not tickets:
        return
    now = time.time()
    async with redis.pipeline(transaction=False) as pipe:
        for ticket_id, token in tickets:
            pipe.set(_receipt_token_key(ticket_id), token, ex=RECEIPT_MAX_AGE_SECONDS)
            pipe.zadd(RECEIPT_PENDING_ZSET, {ticket_id: now})
        # Bounded: past the cap the oldest tickets go; their token keys expire anyway.
        pipe.zremrangebyrank(RECEIPT_PENDING_ZSET, 0, -RECEIPT_PENDING_MAX - 1)
        await pipe.execute()


async def poll_deferred_push_receipts(
    session: AsyncSession,
    redis: Redis,
    *,
    now: float | None = None,
    budget_seconds: float = 0.0,
) -> int:
    """Poll receipts old enough to be ready, a batch at a time, for ``budget_seconds``
    (at least one batch); prune dead tokens. How many receipts were decided.

    One batch of 1,000 per pass (every five minutes) kept up with 12,000 pushes an hour;
    past that, tickets aged out unread and dead tokens were never pruned.
    """
    now = time.time() if now is None else now
    # Token keys carry the same 24 h TTL, so stale tickets only need leaving the set.
    await redis.zremrangebyscore(RECEIPT_PENDING_ZSET, 0, now - RECEIPT_MAX_AGE_SECONDS)
    stop_at = time.monotonic() + budget_seconds
    # Undecided (still pending) tickets stay in the set: the next batch reads past them.
    offset = 0
    decided_total = 0
    while True:
        ticket_ids = _redis_str_members(
            list(
                await redis.zrangebyscore(
                    RECEIPT_PENDING_ZSET,
                    0,
                    now - RECEIPT_MIN_AGE_SECONDS,
                    start=offset,
                    num=RECEIPT_POLL_BATCH,
                )
            )
        )
        if not ticket_ids:
            break
        decided = await _poll_receipt_batch(session, redis, ticket_ids)
        decided_total += decided
        offset += len(ticket_ids) - decided
        if len(ticket_ids) < RECEIPT_POLL_BATCH or time.monotonic() >= stop_at:
            break
    return decided_total


async def _poll_receipt_batch(session: AsyncSession, redis: Redis, ticket_ids: list[str]) -> int:
    """One batch of receipts: forget the decided tickets, prune dead tokens; how many."""
    receipt_map = await expo_push_gateway.fetch_push_receipts(ticket_ids)
    decided = [
        (ticket_id, receipt)
        for ticket_id in ticket_ids
        if (receipt := receipt_map.get(ticket_id))
        and receipt.get("status") not in (None, "pending")
    ]
    if not decided:
        return 0
    async with redis.pipeline(transaction=False) as pipe:
        for ticket_id, _receipt in decided:
            pipe.get(_receipt_token_key(ticket_id))
        tokens = await pipe.execute()
    async with redis.pipeline(transaction=False) as pipe:
        pipe.zrem(RECEIPT_PENDING_ZSET, *[ticket_id for ticket_id, _receipt in decided])
        pipe.delete(*[_receipt_token_key(ticket_id) for ticket_id, _receipt in decided])
        await pipe.execute()
    pruned = False
    for (ticket_id, receipt), token in zip(decided, tokens, strict=True):
        if token and expo_push_gateway.receipt_indicates_invalid_token(receipt):
            try:
                await push_repo.delete_by_token(session, token)
                pruned = True
                logger.info("Pruned invalid push token from receipt ticket=%s", ticket_id[:12])
            except Exception:
                logger.debug("Failed to prune push token from receipt", exc_info=True)

    if pruned:
        await session.commit()
    return len(decided)


# "split" installs created phonia-reminders. "tone" installs created the v2
# channels that play the bundled cue. Older builds only have
# phonia-notifications; Expo drops a channelId the device never created.
SPLIT_ANDROID_CHANNELS = "split"
TONE_ANDROID_CHANNELS = "tone"
PUSH_SOUND = "phonia_notify.wav"


def android_channel_id(data: dict[str, Any], channels: str = SPLIT_ANDROID_CHANNELS) -> str:
    """Match the Android channels created in the mobile app."""
    suffix = "-v2" if channels == TONE_ANDROID_CHANNELS else ""
    return f"phonia-reminders{suffix}"


def channel_id_for_token(token: PushToken, data: dict[str, Any]) -> str | None:
    """Channel for this device, or None so Expo keeps the default channel."""
    if token.platform != "android" or token.android_channels not in {
        SPLIT_ANDROID_CHANNELS,
        TONE_ANDROID_CHANNELS,
    }:
        return None
    return android_channel_id(data, token.android_channels)


def _append_outbound(
    out: list[OutboundPush],
    tokens: list[PushToken],
    *,
    title: str,
    body: str,
    data: dict[str, Any],
    todos: list[TodoItem] | None = None,
    ttl_seconds: int | None = None,
) -> None:
    seen_tokens: set[str] = set()
    for token in tokens:
        if token.expo_push_token in seen_tokens:
            continue
        seen_tokens.add(token.expo_push_token)
        message: dict[str, Any] = {
            "to": token.expo_push_token,
            "title": title,
            "body": body[:240],
            "data": data,
            "sound": PUSH_SOUND,
            "priority": PUSH_PRIORITY,
        }
        if ttl_seconds is not None:
            # Not delivered by then (the phone was off): dropped, not shown hours late.
            message["ttl"] = ttl_seconds
        channel_id = channel_id_for_token(token, data)
        if channel_id is not None:
            message["channelId"] = channel_id
        out.append(
            OutboundPush(
                message=message,
                todos=list(todos or []),
            )
        )


# How far back the aged-unsent count looks: one push cycle, so each row that
# ages out is counted once (background/push_scheduler.py runs every 60s).
AGED_UNSENT_WINDOW = timedelta(seconds=60)


async def log_aged_unsent_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    """Count reminders that should have been pushed but aged out unsent this cycle.

    It used to count every old unsent dated row, whatever the user's push
    settings (everyone who denied notification permission has them), so the
    WARNING fired every minute forever. Now only rows that crossed the 48h
    overdue window during the last cycle, for users who have push reminders
    on and a device token, count: a real delivery failure, each counted once.
    """
    when = now or datetime.now(UTC)
    count = await aged_out_unsent(session, PUSH_REMINDERS, now=when, window=AGED_UNSENT_WINDOW)
    if count:
        logger.warning(
            "Aged unsent reminders count=%s older_than_hours=%s",
            count,
            OVERDUE_MAX_HOURS,
        )
    return count


@dataclass
class PushPage:
    """One page of due reminders as push messages, and where the next page starts."""

    messages: list[OutboundPush]
    next_after: tuple[datetime, UUID] | None


async def collect_push_page(
    session: AsyncSession,
    *,
    now: datetime,
    after: tuple[datetime, UUID] | None = None,
    limit: int = PUSH_PAGE_ROWS,
    ttl_seconds: int | None = None,
) -> PushPage:
    """Push messages for one page of due to-dos (``todos.due_reminder_page``)."""
    rows = await due_reminder_page(session, PUSH_REMINDERS, now=now, after=after, limit=limit)
    if not rows:
        return PushPage(messages=[], next_after=None)

    # One page names at most ``limit`` users: the token lookup's bind parameters stay
    # bounded (asyncpg refuses more than 32,767).
    tokens = await push_repo.list_for_users(session, list({todo.user_id for todo, _ in rows}))
    tokens_by_user: dict[UUID, list[PushToken]] = {}
    for token in tokens:
        tokens_by_user.setdefault(token.user_id, []).append(token)

    messages: list[OutboundPush] = []
    for todo, user in rows:
        # One bad row must not drop every other user's reminders this cycle.
        try:
            if todo.due_at is None or not is_due_now(todo, user, now=now):
                continue
            user_tokens = tokens_by_user.get(todo.user_id, [])
            if not user_tokens:
                continue
            title = reminder_title(is_overdue=todo.due_at < now, locale=user.locale)
            _append_outbound(
                messages,
                user_tokens,
                title=title,
                body=todo.content,
                data={
                    "type": "todo_reminder",
                    "screen": "todos",
                    "todo_id": str(todo.id),
                    "focus": "reminders",
                },
                todos=[todo],
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            logger.exception("Todo reminder failed user_id=%s todo_id=%s", todo.user_id, todo.id)
    next_after = reminder_page_key(rows) if len(rows) >= limit else None
    return PushPage(messages=messages, next_after=next_after)


async def _finalize_push_deliveries(
    session: AsyncSession,
    outbound: list[OutboundPush],
    delivered: list[bool],
    *,
    now: datetime,
) -> None:
    todos_marked: set[UUID] = set()

    for item, ok in zip(outbound, delivered, strict=False):
        if not ok:
            continue
        for todo in item.todos:
            todo_id = getattr(todo, "id", None)
            if todo_id is None or todo_id in todos_marked:
                continue
            if await mark_reminder_pushed(session, todo, now=now):
                todos_marked.add(todo_id)

    if todos_marked:
        await session.commit()


async def dispatch_expo(outbound: list[OutboundPush], settings: Settings) -> PushSendResult:
    """Send via Expo (or mock): per message, delivered and held, and the tokens and
    tickets to act on."""
    if not outbound:
        return PushSendResult(invalid_tokens=[], delivered=[])
    if settings.mock_llm_enabled and settings.environment == "development":
        logger.debug("Skipping expo push in dev mock mode count=%s", len(outbound))
        return PushSendResult(invalid_tokens=[], delivered=[True] * len(outbound))

    result = await expo_push_gateway.send_push_messages([item.message for item in outbound])
    if len(result.delivered) != len(outbound):
        result.delivered = [False] * len(outbound)
    return result


def push_backoff(redis: Redis, settings: Settings) -> SendBackoff:
    return SendBackoff.for_channel(redis, settings, "push")


def _todo_key(todo: TodoItem) -> str:
    return occurrence_key(todo.id, todo.due_at)


async def without_held(backoff: SendBackoff, outbound: list[OutboundPush]) -> list[OutboundPush]:
    """The messages whose reminder is not waiting out a hold."""
    held = await backoff.held(sorted({_todo_key(todo) for item in outbound for todo in item.todos}))
    if not held:
        return outbound
    return [item for item in outbound if not all(_todo_key(t) in held for t in item.todos)]


async def hold_failed(
    backoff: SendBackoff, outbound: list[OutboundPush], result: PushSendResult, settings: Settings
) -> int:
    """Hold each reminder whose push must not go again next minute (``HoldReason``),
    unless another of its messages (another device) was delivered. How many held."""
    delivered_keys = {
        _todo_key(todo)
        for item, ok in zip(outbound, result.delivered, strict=False)
        if ok
        for todo in item.todos
    }
    waits: dict[str, float] = {}
    for item, hold in zip(outbound, result.holds, strict=False):
        if hold is None:
            continue
        at_least = _hold_floor(hold.reason, hold.retry_after, backoff, settings)
        for todo in item.todos:
            key = _todo_key(todo)
            if key not in delivered_keys:
                waits[key] = max(waits.get(key, 0.0), at_least)
    for key, at_least in waits.items():
        await backoff.hold(key, at_least=at_least)
    return len(waits)


def _hold_floor(
    reason: HoldReason, retry_after: float | None, backoff: SendBackoff, settings: Settings
) -> float:
    """The shortest wait a hold of ``reason`` gets (the back-off may be longer)."""
    if reason is HoldReason.AMBIGUOUS:
        return float(settings.push_ambiguous_hold_seconds)
    if reason is HoldReason.REJECTED:
        return float(backoff.max_seconds)
    return retry_after or 0.0


async def finalize_push_deliveries(
    session: AsyncSession,
    outbound: list[OutboundPush],
    delivered: list[bool],
    *,
    now: datetime | None = None,
) -> None:
    await _finalize_push_deliveries(session, outbound, delivered, now=now or datetime.now(UTC))
