"""Apply LLM-extracted or explicit todo/reminder mutations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import TodoItem
from app.modules.todos import repository as todos_repo
from app.modules.todos.prompt_context import _normalize, _topic_key
from app.modules.todos.recurrence import RecurrenceRule, is_recurrence_rule, snap_first_due
from app.modules.todos.schemas import TodoActionItem
from app.services import time_context as time_context_service

logger = logging.getLogger(__name__)

_ACTION_RELOAD_LIMIT = 500

# Defensive caps for LLM-inferred mutations applied from a chat transcript.
# The model extracts actions from arbitrary user text; these limits prevent a
# misparse from wiping large amounts of data in one turn.
MAX_TODO_ACTIONS_PER_TURN = 12

REMINDER_TOPIC = "Reminders"


def _find_item(items: list[TodoItem], topic: str, content: str) -> TodoItem | None:
    # Exact normalized match only — fuzzy (0.92) was removed to match projects:
    # near-miss complete/delete must not hit the wrong todo.
    needle = _normalize(content)
    topic_norm = _topic_key(topic)
    candidates = [i for i in items if _topic_key(i.topic) == topic_norm and not i.checked]
    for item in candidates:
        if _normalize(item.content) == needle:
            return item
    return None


def _find_item_any_state(items: list[TodoItem], topic: str, content: str) -> TodoItem | None:
    needle = _normalize(content)
    topic_norm = _topic_key(topic)
    candidates = [i for i in items if _topic_key(i.topic) == topic_norm]
    for item in candidates:
        if _normalize(item.content) == needle:
            return item
    return None


def _due_local_date(item: TodoItem, user_timezone: str | None) -> date | None:
    tz = time_context_service.resolve_timezone(user_timezone)
    due = item.due_at
    if due is None:
        return None
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due.astimezone(tz).date()


def _rescheduled_due(item: TodoItem, due_at: datetime, timezone: str | None) -> datetime:
    rule = item.recurrence_rule
    return snap_first_due(due_at, rule if is_recurrence_rule(rule) else None, timezone=timezone)


@dataclass
class _TodoApplyState:
    session: AsyncSession
    user_id: UUID
    chat_id: UUID | None
    user_timezone: str | None
    items: list[TodoItem]


def _prepare_todo_action(action: TodoActionItem) -> TodoActionItem | None:
    topic = action.topic.strip()
    if not topic:
        if action.action == "add":
            default_topic = (
                REMINDER_TOPIC if action.due_at is not None else todos_repo.DEFAULT_TOPIC
            )
            return action.model_copy(update={"topic": default_topic})
        return None
    if topic != action.topic:
        return action.model_copy(update={"topic": topic})
    return action


async def _todo_action_add(state: _TodoApplyState, action: TodoActionItem) -> int:
    content = action.content.strip()
    if not content:
        return 0
    topic = action.topic
    if _find_item_any_state(state.items, topic, content):
        return 0
    due_at = time_context_service.normalize_due_at(action.due_at, state.user_timezone)
    recurrence = action.recurrence_rule if due_at is not None else None
    if due_at is not None and recurrence:
        due_at = snap_first_due(due_at, recurrence, timezone=state.user_timezone)
    try:
        # SAVEPOINT so a unique-index race rolls back this INSERT only —
        # session.rollback() would discard earlier commit=False writes.
        async with state.session.begin_nested():
            new_todo = await todos_repo.create(
                state.session,
                user_id=state.user_id,
                content=content,
                topic=topic,
                chat_id=state.chat_id,
                due_at=due_at,
                recurrence_rule=recurrence,
                commit=False,
            )
    except IntegrityError as exc:
        if due_at is None or not todos_repo.is_open_content_due_conflict(exc):
            raise
        logger.debug(
            "add reminder raced with an existing open dated row for user_id=%s; skipping",
            state.user_id,
        )
        return 0
    state.items.append(new_todo)
    return 1


async def _todo_action_complete(state: _TodoApplyState, action: TodoActionItem) -> int:
    item = _find_item(state.items, action.topic, action.content)
    if item and not item.checked:
        await todos_repo.update(state.session, item, checked=True, commit=False)
        return 1
    return 0


async def _todo_action_uncheck(state: _TodoApplyState, action: TodoActionItem) -> int:
    item = _find_item_any_state(state.items, action.topic, action.content)
    if item and item.checked:
        await todos_repo.update(state.session, item, checked=False, commit=False)
        return 1
    return 0


async def _todo_action_delete(state: _TodoApplyState, action: TodoActionItem) -> int:
    item = _find_item_any_state(state.items, action.topic, action.content)
    if item:
        await todos_repo.delete_by_id(state.session, item.id, state.user_id, commit=False)
        state.items = [i for i in state.items if i.id != item.id]
        return 1
    logger.warning(
        "Todo delete missed: user_id=%s topic=%s content_chars=%d",
        state.user_id,
        action.topic,
        len(action.content or ""),
    )
    return 0


def _set_due_fields(
    item: TodoItem,
    due_at: datetime,
    action: TodoActionItem,
    timezone: str | None,
) -> dict[str, datetime | RecurrenceRule]:
    effective_due = _rescheduled_due(item, due_at, timezone)
    fields: dict[str, datetime | RecurrenceRule] = {"due_at": effective_due}
    if action.recurrence_rule is not None:
        fields["recurrence_rule"] = action.recurrence_rule
        fields["due_at"] = snap_first_due(effective_due, action.recurrence_rule, timezone=timezone)
    return fields


async def _todo_action_set_due(state: _TodoApplyState, action: TodoActionItem) -> int:
    due_at = time_context_service.normalize_due_at(action.due_at, state.user_timezone)
    if due_at is None:
        return 0
    if action.content.strip() == "*":
        tz = time_context_service.resolve_timezone(state.user_timezone)
        today = datetime.now(tz).date()
        applied = 0
        for open_item in state.items:
            if open_item.checked or open_item.due_at is None:
                continue
            if _due_local_date(open_item, state.user_timezone) != today:
                continue
            await todos_repo.update(
                state.session,
                open_item,
                commit=False,
                **_set_due_fields(open_item, due_at, action, state.user_timezone),
            )
            applied += 1
        return applied
    item = _find_item_any_state(state.items, action.topic, action.content)
    if item:
        await todos_repo.update(
            state.session,
            item,
            commit=False,
            **_set_due_fields(item, due_at, action, state.user_timezone),
        )
        return 1
    return 0


async def _todo_action_clear_due(state: _TodoApplyState, action: TodoActionItem) -> int:
    item = _find_item_any_state(state.items, action.topic, action.content)
    if item and item.due_at is not None:
        await todos_repo.update(
            state.session, item, due_at=None, recurrence_rule=None, commit=False
        )
        return 1
    return 0


# Each handler mutates the preloaded state and returns how many rows it changed.
_TodoActionHandler = Callable[[_TodoApplyState, TodoActionItem], Awaitable[int]]
_TODO_ACTION_HANDLERS: dict[str, _TodoActionHandler] = {
    "add": _todo_action_add,
    "complete": _todo_action_complete,
    "uncheck": _todo_action_uncheck,
    "delete": _todo_action_delete,
    "set_due": _todo_action_set_due,
    "clear_due": _todo_action_clear_due,
}


async def apply_todo_actions(
    session: AsyncSession,
    *,
    user_id: UUID,
    actions: list[TodoActionItem],
    chat_id: UUID | None = None,
    user_timezone: str | None = None,
) -> int:
    """Apply the actions in the caller's session; how many rows changed. No commit.

    The caller owns the transaction: it commits these writes with its own, or rolls
    them back (code-health audit ARCH-07).
    """
    if not actions:
        return 0
    items = await todos_repo.list_for_user(session, user_id, limit=_ACTION_RELOAD_LIMIT)
    state = _TodoApplyState(
        session=session,
        user_id=user_id,
        chat_id=chat_id,
        user_timezone=user_timezone,
        items=items,
    )

    applied = 0
    for action in actions:
        prepared = _prepare_todo_action(action)
        if prepared is None:
            continue
        handler = _TODO_ACTION_HANDLERS.get(prepared.action)
        if handler is None:
            continue
        try:
            # Each action in its own savepoint: one that fails leaves the others and
            # the caller's transaction usable.
            async with session.begin_nested():
                applied += await handler(state, prepared)
        except Exception:
            logger.exception(
                "Failed todo action %s for user_id=%s topic=%s",
                prepared.action,
                user_id,
                prepared.topic,
            )
    if applied > 0:
        logger.info(
            "Applied %d todo action(s) for user_id=%s chat_id=%s",
            applied,
            user_id,
            chat_id,
        )
    return applied
