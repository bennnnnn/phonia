"""Todo selection/formatting injected into the chat system prompt."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.orm import TodoItem, User
from app.modules.todos import repository as todos_repo
from app.modules.todos.chat_language import writes_todos_in_todo_screen
from app.modules.todos.classification import query_implies_todos
from app.modules.todos.prompt_hint import TODO_HINT, TODO_READ_ONLY_HINT
from app.modules.todos.repository import DEFAULT_TOPIC
from app.services import day_planning as day_planning_service
from app.services import time_context as time_context_service

# Voice inject stays shorter than typed-chat prompt_limit (48).
_VOICE_TODO_LIMIT = 12
_QUERY_STOP_TERMS = {
    "from",
    "list",
    "need",
    "please",
    "reminder",
    "show",
    "task",
    "todo",
    "what",
    "when",
    "with",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _search_terms(text: str) -> set[str]:
    """Small lexical normalization for list queries (grocery/groceries, tasks/task)."""
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", _normalize(text)):
        if len(token) < 4:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = f"{token[:-3]}y"
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
            token = token[:-1]
        if token not in _QUERY_STOP_TERMS:
            terms.add(token)
    return terms


def _topic_key(topic: str) -> str:
    return _normalize(topic or DEFAULT_TOPIC)


def _due_local(due_at: datetime, user_timezone: str | None) -> datetime:
    tz = time_context_service.resolve_timezone(user_timezone)
    due = due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    return due.astimezone(tz)


def _todo_group(todo: TodoItem, user_timezone: str | None) -> tuple[str, str]:
    """Sort key and heading matching the mobile To-do list."""
    if todo.checked:
        return ("9", "Completed")
    if todo.due_at is None:
        return ("8", "Anytime")
    tz = time_context_service.resolve_timezone(user_timezone)
    now = datetime.now(tz)
    due_local = _due_local(todo.due_at, user_timezone)
    if due_local < now:
        return ("0", "Overdue")
    due_date = due_local.date()
    if due_date == now.date():
        return ("1", "Today")
    if due_date == (now + timedelta(days=1)).date():
        return ("2", "Tomorrow")
    return ("3", due_local.strftime("%a %b %d"))


def _todo_priority(
    item: TodoItem,
    *,
    query_text: str | None,
    user_timezone: str | None,
) -> tuple[int, int, datetime]:
    """Lower tuple sorts first — query matches survive prompt trimming."""
    tz = time_context_service.resolve_timezone(user_timezone)
    now = datetime.now(tz)
    bucket = 50
    if item.due_at is not None:
        due_local = _due_local(item.due_at, user_timezone)
        if not item.checked and due_local < now:
            bucket = 0
        elif due_local.date() == now.date():
            bucket = 1
        elif due_local.date() == (now + timedelta(days=1)).date():
            bucket = 2
        elif not item.checked:
            bucket = 4
        else:
            bucket = 6
        sort_due = due_local
    else:
        bucket = 8 if not item.checked else 9
        sort_due = datetime.max.replace(tzinfo=UTC)

    q = _normalize(query_text or "")
    match_rank = 0
    if q:
        hay = f"{_normalize(item.content)} {_topic_key(item.topic)}"
        if q in hay or _search_terms(q).intersection(_search_terms(hay)):
            match_rank = -1
    return (match_rank, bucket, sort_due)


def select_todos_for_prompt(
    items: list[TodoItem],
    settings: Settings,
    *,
    query_text: str | None = None,
    user_timezone: str | None = None,
) -> list[TodoItem]:
    """Trim large to-do snapshots while keeping urgent dated items first."""
    limit = max(8, settings.todo_prompt_limit)
    if len(items) <= limit:
        return list(items)

    ranked = sorted(
        items,
        key=lambda item: _todo_priority(item, query_text=query_text, user_timezone=user_timezone),
    )
    return ranked[:limit]


def format_todos_block(items: list[TodoItem], *, user_timezone: str | None = None) -> str:
    if not items:
        return ""

    overdue_open = [
        item
        for item in items
        if item.due_at is not None
        if not item.checked
        and time_context_service.describe_due_at(item.due_at, user_timezone).startswith("overdue")
    ]

    lines: list[str] = []

    if overdue_open:
        names = ", ".join(f"{i.content} ({i.topic})" for i in overdue_open[:5])
        extra = f" (+{len(overdue_open) - 5} more)" if len(overdue_open) > 5 else ""
        lines.append(
            f"⚠ {len(overdue_open)} overdue reminder(s): {names}{extra} — nudge if relevant."
        )

    lines.append("User To-do list (grouped by day; dates are optional):")
    open_todos = [item for item in items if not item.checked]
    done_todos = [item for item in items if item.checked]
    display = open_todos + done_todos

    grouped: dict[tuple[str, str], list[TodoItem]] = {}
    for todo in display:
        key = _todo_group(todo, user_timezone)
        grouped.setdefault(key, []).append(todo)

    for key in sorted(grouped.keys(), key=lambda item: item[0]):
        heading = key[1]
        lines.append(f"\n### {heading}")
        day_items = sorted(
            grouped[key],
            key=lambda item: _todo_priority(item, query_text=None, user_timezone=user_timezone),
        )
        for todo in day_items:
            status = "done" if todo.checked else "open"
            mark = "✓" if todo.checked else "○"
            topic = todo.topic.strip() or DEFAULT_TOPIC
            if todo.due_at is None:
                lines.append(f"- {mark} {todo.content} ({status}, no date, topic: {topic})")
            else:
                due_local = _due_local(todo.due_at, user_timezone)
                clock = due_local.strftime("%H:%M")
                due_label = time_context_service.describe_due_at(
                    todo.due_at, user_timezone, checked=todo.checked
                )
                rel = f", {due_label}" if due_label else ""
                repeat = f", repeats {todo.recurrence_rule}" if todo.recurrence_rule else ""
                lines.append(
                    f"- {mark} {todo.content} at {clock}{rel}{repeat} ({status}, topic: {topic})"
                )

    return "\n".join(lines)


def format_todos_voice_block(items: list[TodoItem], *, user_timezone: str | None = None) -> str:
    """Compact To-do snapshot for spoken Live Talk instructions (no markdown)."""
    if not items:
        return ""

    ranked = sorted(
        items,
        key=lambda item: _todo_priority(item, query_text=None, user_timezone=user_timezone),
    )[:_VOICE_TODO_LIMIT]

    grouped: dict[tuple[str, str], list[TodoItem]] = {}
    for todo in ranked:
        key = _todo_group(todo, user_timezone)
        grouped.setdefault(key, []).append(todo)

    lines = ["User To-do list:"]
    for key in sorted(grouped.keys(), key=lambda item: item[0]):
        heading = key[1]
        day_items = sorted(
            grouped[key],
            key=lambda item: _todo_priority(item, query_text=None, user_timezone=user_timezone),
        )
        for todo in day_items:
            status = "done" if todo.checked else "open"
            if todo.due_at is None:
                lines.append(f"{heading}: {todo.content} ({status}, no date)")
            else:
                due_local = _due_local(todo.due_at, user_timezone)
                clock = due_local.strftime("%H:%M")
                lines.append(f"{heading}: {todo.content} at {clock} ({status})")
    return "\n".join(lines)


def _has_overdue_open_reminders(items: list[TodoItem], user_timezone: str | None) -> bool:
    for item in items:
        if item.checked or item.due_at is None:
            continue
        label = time_context_service.describe_due_at(item.due_at, user_timezone)
        if label.startswith("overdue"):
            return True
    return False


def should_inject_todos_prompt(
    items: list[TodoItem],
    *,
    query_text: str | None = None,
    user_timezone: str | None = None,
) -> bool:
    """Skip todo blocks on unrelated turns to save tokens; keep overdue nudges."""
    if query_text and day_planning_service.is_day_planning_question(query_text):
        return True
    if query_implies_todos(query_text):
        return True
    return _has_overdue_open_reminders(items, user_timezone)


async def build_todos_system_section(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    client_timezone: str | None = None,
    query_text: str | None = None,
    accepted_offer: bool = False,
) -> str | None:
    """Todo hint + snapshot block, or None when the turn is unrelated.

    ``accepted_offer``: the message is a yes to the last reply's offer of a reminder
    (``offer_reply``), so the turn is that request.
    """
    tz = time_context_service.effective_timezone(user.timezone, client_timezone)
    probe: list[TodoItem] = []
    text_hit = bool(
        accepted_offer
        or (query_text and day_planning_service.is_day_planning_question(query_text))
        or query_implies_todos(query_text)
    )
    if not text_hit:
        probe = await todos_repo.list_due_soon(session, user.id, before_utc=datetime.now(UTC))
    if not text_hit and not should_inject_todos_prompt(
        probe, query_text=query_text, user_timezone=tz
    ):
        return None
    items = await todos_repo.list_for_user(session, user.id, limit=settings.todo_inject_limit)
    selected = select_todos_for_prompt(items, settings, query_text=query_text, user_timezone=tz)
    block = format_todos_block(selected, user_timezone=tz)
    # A turn that may only read its to-dos is never taught to write them.
    read_only = writes_todos_in_todo_screen(query_text, locale=user.locale)
    hint = TODO_READ_ONLY_HINT if read_only else TODO_HINT
    return f"{hint}\n\n{block}" if block else hint
