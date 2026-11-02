"""The reply's reminder changes: the last finalize step, on the finished text.

This is the finalize step with an effect outside the reply. With reminder cards
on it stores a proposal in Redis and ends the reply with its card; with them
off it writes To-do rows. It runs after every text pass, so no later pass can
fail and throw away a card the user was already offered (ES-03).
"""

from __future__ import annotations

import logging
import re

from redis.asyncio import Redis

from app.core.config import Settings
from app.modules import todos as todos_service
from app.modules.chat.remember_reply import without_remember_turn_claims
from app.modules.chat.turn_deps import ChatTurnDeps
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.services.md_fence_scan import iter_fences, last_fence

logger = logging.getLogger(__name__)

_REMINDER_FENCE_LANG = "reminder"
_ASK_WHEN = "When should I remind you?"
_TAG_CLOSER = re.compile(r"^[ \t]*</reminder>[ \t]*$\n?", re.MULTILINE)


def drop_cut_reminder_fence(text: str) -> str:
    """The reply without a ```reminder fence it was cut off inside.

    A reply stopped or dropped mid-fence leaves the fence open, and the reminder
    pass never applies an open one. Finalize closes every open fence before that
    pass runs, so the cut fence goes first (the phone hides reminder fences).
    """
    last = last_fence(text)
    if last is None or last.closed or last.lang != _REMINDER_FENCE_LANG:
        return text
    # "```reminder … </reminder>" (2026-10-25) closed it as a tag: the reply goes on after it.
    closer = _TAG_CLOSER.search(text, last.start)
    if closer is not None:
        return f"{text[: last.start]}{text[closer.end() :]}".strip()
    return text[: last.start].rstrip()


async def apply_reminder_pass(
    deps: ChatTurnDeps,
    redis: Redis,
    settings: Settings,
    ctx: StreamContext,
    text: str,
    outcome: TurnOutcome | None,
) -> str:
    """The reply with its reminder changes applied; ``todos_changed`` when the list changed.

    A failure keeps the text it was given: the finalize passes are done with it.
    """
    # Chat in another language only reads to-dos; changes are made in To-do: the server
    # reads a change against the user's words in English (docs: modules/todos/chat_language).
    message, prior = ctx.user_message_content, _prior_text(ctx, "user")
    locale = ctx.user.locale if ctx.user else None
    if todos_service.writes_todos_in_todo_screen(message, prior_user=prior, locale=locale):
        language = todos_service.message_language(message) or todos_service.message_language(prior)
        return offer_todo_screen(text, language or locale)
    try:
        given = text
        text, created = await _materialize(deps, redis, settings, ctx, text)
        text = without_remember_turn_claims(ctx.user_message_content or "", ctx.user, text)
        # "I can't set reminders from here" is false: the card above, or the next one.
        text = todos_service.without_denials(text)
        # A reply that was only a reminder fence, with nothing saved, must still
        # say something: an empty one kept the streamed fence on the phone.
        if given.strip() and not text.strip():
            text = _ASK_WHEN
        # Rows written this turn: the phone reloads its list once (code-health audit
        # NET-14). No background job writes to-dos after the reply any more.
        if outcome is not None and created > 0:
            outcome.todos_changed = True
    except Exception:
        logger.exception("Reminder pass failed; keeping the finished reply")
    return text


def offer_todo_screen(text: str, language: str | None) -> str:
    """The reply with no reminder change: the server's line and the To-do button when
    the model took the turn for one.

    A ```reminder fence the model wrote anyway would have been read against English
    words and answered "When should I remind you?". Its words go too: beside the
    fence a model wrote "He añadido…" (I've added it) for a change nothing made.
    """
    link = todos_service.TODO_LINK_FENCE
    if not any(fence.lang in (_REMINDER_FENCE_LANG, link) for fence in iter_fences(text)):
        return text
    return todos_service.todo_screen_answer(language)


async def _materialize(
    deps: ChatTurnDeps, redis: Redis, settings: Settings, ctx: StreamContext, text: str
) -> tuple[str, int]:
    user = ctx.user
    if user is None:
        async with deps.session_factory() as session:
            user = await deps.users.get_by_id(session, ctx.user_id)
    if user is None:
        return text, 0
    async with deps.session_factory() as session:
        materialized: tuple[str, int] = await deps.todos.materialize_reminder_fences(
            session,
            user_id=ctx.user_id,
            chat_id=ctx.chat_id,
            assistant_text=text,
            user_timezone=ctx.user_timezone or user.timezone,
            user_text=ctx.user_message_content,
            # "Mark it done" points at a reminder only after a reply about
            # reminders, or right after a message that asked about them.
            prior_assistant=_prior_text(ctx, "assistant"),
            prior_user=_prior_text(ctx, "user"),
            redis=redis,
            # A reminder change in chat is a card the user taps; nothing is written yet.
            confirm=True,
            window=ctx.recent_messages,
        )
        # The pass never commits the session it is given; this one is the pass's own.
        await session.commit()
    return materialized


def _prior_text(ctx: StreamContext, role: str) -> str:
    """The latest earlier message from ``role`` ("" when none)."""
    for message in reversed(ctx.prompt_messages[:-1]):
        if message.get("role") == role:
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""
