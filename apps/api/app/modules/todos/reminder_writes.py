"""Write one reminder draft: create it, or complete, reopen, delete or move it.

Each write returns the app's own result line ("Set: gym — Thursday, 6:00 PM.",
"Done: gym.") and whether the row was saved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import TodoItem
from app.modules.todos import repository as todos_repo
from app.modules.todos.actions import _ACTION_RELOAD_LIMIT, REMINDER_TOPIC, apply_todo_actions
from app.modules.todos.recurrence import snap_first_due
from app.modules.todos.reminder_fence_parse import ReminderFence
from app.modules.todos.schemas import RecurrenceRule, TodoActionItem
from app.services import time_context as time_context_service

logger = logging.getLogger(__name__)

_FAIL_VERB = {
    "add": "set",
    "delete": "delete",
    "complete": "complete",
    "uncheck": "reopen",
    "set_due": "reschedule",
    "clear_due": "remove the date from",
}
_OK_PREFIX = {
    "add": "Set",
    "delete": "Deleted",
    "complete": "Done",
    "uncheck": "Reopened",
    "set_due": "Moved",
    "clear_due": "Date removed",
}
# The app's own result lines: "Set: gym — Thursday, 6:00 PM.", "Done: gym.".
OK_PREFIXES = tuple(f"{prefix}:" for prefix in dict.fromkeys(_OK_PREFIX.values()))


def result_prefix(action: str) -> str:
    """The word a result line starts with: "Set", "Done", "Moved"."""
    return _OK_PREFIX.get(action, "Moved" if action == "move" else "Set")


@dataclass
class ReminderWrites:
    """One turn's writes: the saved rows, read once, and how many changes were applied."""

    session: AsyncSession
    user_id: UUID
    chat_id: UUID
    user_timezone: str | None
    existing: list[TodoItem] = field(default_factory=list)
    existing_loaded: bool = False
    applied: int = 0


def format_schedule_when(
    due_at: datetime,
    user_timezone: str | None,
    repeat: RecurrenceRule | str | None = None,
) -> str:
    tz = time_context_service.resolve_timezone(user_timezone)
    due_local = (
        due_at.astimezone(tz) if due_at.tzinfo else due_at.replace(tzinfo=UTC).astimezone(tz)
    )
    hour = due_local.strftime("%I").lstrip("0") or "0"
    when = (
        f"{due_local.strftime('%A')}, {due_local.strftime('%b')} {due_local.day}, "
        f"{hour}:{due_local.strftime('%M')} {due_local.strftime('%p')}"
    )
    if repeat:
        when = f"{when} · {repeat}"
    return when


def format_schedule_result(
    *,
    action: str,
    title: str,
    due_at: datetime | None,
    repeat: RecurrenceRule | str | None,
    user_timezone: str | None,
    ok: bool,
) -> str:
    if not ok:
        verb = _FAIL_VERB.get(action, "update")
        return f"Could not {verb} {title}."
    prefix = _OK_PREFIX.get(action, "Set")
    if action in ("add", "set_due") and due_at is not None:
        return f"{prefix}: {title} — {format_schedule_when(due_at, user_timezone, repeat)}."
    return f"{prefix}: {title}."


async def load_existing(state: ReminderWrites) -> None:
    """Load To-dos once (lazily) so multi-fence replies don't re-read the DB."""
    if not state.existing_loaded:
        state.existing = await todos_repo.list_for_user(
            state.session, state.user_id, limit=_ACTION_RELOAD_LIMIT
        )
        state.existing_loaded = True


def _existing_open_match(
    state: ReminderWrites, title: str, due_at: datetime | None
) -> TodoItem | None:
    """Find a true duplicate, or an undated task that can be promoted.

    A same-title reminder on another day is a separate reminder.  Treating it
    as a duplicate both lost the requested date and produced a false success
    confirmation.  Plain to-dos keep the historical title-only de-duplication.
    """
    needle = title.lower()
    matches: list[TodoItem] = []
    for item in state.existing:
        if (item.content or "").strip().lower() != needle:
            continue
        if item.checked:
            continue
        matches.append(item)
    if due_at is None:
        return matches[0] if matches else None
    exact = next((item for item in matches if item.due_at == due_at), None)
    if exact is not None:
        return exact
    return next((item for item in matches if item.due_at is None), None)


def _existing_mutation_match(state: ReminderWrites, title: str, action: str) -> TodoItem | None:
    needle = title.lower()
    matches = [item for item in state.existing if (item.content or "").strip().lower() == needle]
    if action == "uncheck":
        return next((item for item in matches if item.checked), matches[0] if matches else None)
    return next((item for item in matches if not item.checked), matches[0] if matches else None)


async def create_one(state: ReminderWrites, draft: ReminderFence) -> tuple[str, bool]:
    due_at = time_context_service.normalize_due_at(draft.due_at, state.user_timezone)
    if draft.repeat:
        assert due_at is not None
        due_at = snap_first_due(due_at, draft.repeat, timezone=state.user_timezone)
    title = draft.title.strip()
    await load_existing(state)
    match = _existing_open_match(state, title, due_at)
    if match is not None:
        if due_at is not None and match.due_at is None:
            if draft.repeat is not None:
                match = await todos_repo.update(
                    state.session,
                    match,
                    due_at=due_at,
                    recurrence_rule=draft.repeat,
                    commit=False,
                )
            else:
                match = await todos_repo.update(state.session, match, due_at=due_at, commit=False)
        elif draft.repeat is not None and match.recurrence_rule != draft.repeat:
            match = await todos_repo.update(
                state.session, match, recurrence_rule=draft.repeat, commit=False
            )
        saved_due = match.due_at if match.due_at is not None else due_at
        return format_schedule_result(
            action="add",
            title=title,
            due_at=saved_due,
            repeat=getattr(match, "recurrence_rule", None) or draft.repeat,
            user_timezone=state.user_timezone,
            ok=True,
        ), True
    try:
        # A savepoint: a duplicate (an open dated row outside the snapshot, or one saved
        # concurrently) undoes this insert only, never the caller's turn (audit ARCH-07).
        async with state.session.begin_nested():
            new_todo = await todos_repo.create(
                state.session,
                user_id=state.user_id,
                content=title,
                topic=REMINDER_TOPIC if due_at is not None else todos_repo.DEFAULT_TOPIC,
                chat_id=state.chat_id,
                due_at=due_at,
                recurrence_rule=draft.repeat,
                commit=False,
            )
    except IntegrityError as exc:
        if due_at is None or not todos_repo.is_open_content_due_conflict(exc):
            raise
        existing = await todos_repo.get_open_dated_duplicate(
            state.session, state.user_id, content=title, due_at=due_at
        )
        if existing is None:
            raise
        saved_due = existing.due_at if existing.due_at is not None else due_at
        return format_schedule_result(
            action="add",
            title=title,
            due_at=saved_due,
            repeat=getattr(existing, "recurrence_rule", None) or draft.repeat,
            user_timezone=state.user_timezone,
            ok=True,
        ), True
    state.existing.append(new_todo)
    logger.info(
        "To-do fence applied: user_id=%s chat_id=%s title_chars=%d",
        state.user_id,
        state.chat_id,
        len(title),
    )
    return format_schedule_result(
        action="add",
        title=title,
        due_at=due_at,
        repeat=draft.repeat,
        user_timezone=state.user_timezone,
        ok=True,
    ), True


async def mutate_one(state: ReminderWrites, draft: ReminderFence) -> tuple[str, bool]:
    title = draft.title.strip()
    due_at = time_context_service.normalize_due_at(draft.due_at, state.user_timezone)
    await load_existing(state)
    existing = _existing_mutation_match(state, title, draft.action)
    action = TodoActionItem(
        action=draft.action,
        topic=existing.topic if existing is not None else REMINDER_TOPIC,
        content=title,
        due_at=draft.due_at,
        recurrence_rule=draft.repeat if draft.action == "set_due" else None,
    )
    applied = await apply_todo_actions(
        state.session,
        user_id=state.user_id,
        actions=[action],
        chat_id=state.chat_id,
        user_timezone=state.user_timezone,
    )
    ok = applied > 0
    if ok and draft.action == "delete":
        needle = title.lower()
        state.existing = [
            item for item in state.existing if (item.content or "").strip().lower() != needle
        ]
    return format_schedule_result(
        action=draft.action,
        title=title,
        due_at=due_at,
        repeat=draft.repeat if draft.action == "set_due" else None,
        user_timezone=state.user_timezone,
        ok=ok,
    ), ok
