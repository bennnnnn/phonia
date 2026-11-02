"""Which saved reminder a spoken change names.

``spoken_change`` reads what the user asked; this picks the one reminder it
means: by the title words they said, by the other clause ("I paid rent, check
it off"), or the latest one for "it", "this" or "that". A tie matches nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from app.modules.todos.spoken_change import SpokenReminderChange

SpokenAction = Literal["complete", "uncheck", "delete", "set_due"]

_SKIP = frozenset(
    {
        "the",
        "a",
        "an",
        "my",
        "me",
        "to",
        "it",
        "reminder",
        "reminders",
        "todo",
        "todos",
        "task",
        "tasks",
        "call",
        "item",
    }
)


class _Named(Protocol):
    content: str
    checked: bool


def match_spoken_reminder(
    items: Sequence[_Named],
    hint: str,
    *,
    action: SpokenAction,
) -> _Named | None:
    """Match a hint to one reminder. A tie matches nothing."""
    hint_words = title_words(hint)
    if not hint_words:
        return None
    pool = _pool(items, action)
    scored: list[tuple[int, _Named]] = []
    for item in pool:
        words = title_words(item.content or "")
        if not words:
            continue
        if hint_words <= words or words <= hint_words:
            scored.append((len(hint_words & words), item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _pool(items: Sequence[_Named], action: SpokenAction) -> list[_Named]:
    if action == "uncheck":
        checked = [item for item in items if item.checked]
        return checked or list(items)
    if action == "delete":
        return list(items)
    open_items = [item for item in items if not item.checked]
    return open_items or list(items)


def title_words(text: str) -> set[str]:
    """The words that name a reminder: three letters or more, not filler like "the" or "task"."""
    words: set[str] = set()
    token: list[str] = []
    for char in text.lower():
        if char.isalnum():
            token.append(char)
            continue
        if token:
            word = "".join(token)
            token = []
            if len(word) > 2 and word not in _SKIP:
                words.add(word)
    if token:
        word = "".join(token)
        if len(word) > 2 and word not in _SKIP:
            words.add(word)
    return words


def match_from_context(items: Sequence[_Named], change: SpokenReminderChange) -> _Named | None:
    """The one reminder that shares the most words with the other clause, if any."""
    context = title_words(change.context_hint)
    if not context:
        return None
    scored = sorted(
        (
            (len(context & title_words(item.content or "")), item)
            for item in _pool(items, change.action)
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored or scored[0][0] == 0:
        return None
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def resolve_spoken_target(items: Sequence[_Named], change: SpokenReminderChange) -> _Named | None:
    """The named reminder, or the latest one when they said it/this/that."""
    if change.use_latest and change.context_hint:
        named = match_from_context(items, change)
        if named is not None:
            return named
    if change.use_latest or not title_words(change.title_hint):
        return latest_reminder(items, change.action)
    return match_spoken_reminder(items, change.title_hint, action=change.action)


def latest_reminder(items: Sequence[_Named], action: SpokenAction) -> _Named | None:
    pool = _pool(items, action)
    if not pool:
        return None
    return max(pool, key=_recency)


def _recency(item: _Named) -> tuple[datetime, datetime]:
    return (_moment(getattr(item, "updated_at", None)), _moment(getattr(item, "created_at", None)))


def _moment(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    return datetime.min.replace(tzinfo=UTC)
