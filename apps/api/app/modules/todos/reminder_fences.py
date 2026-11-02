"""Materialize the turn's To-do changes from its ``reminder`` fences and the user's words.

A turn is read in order: find the fences, match the turn to what the user asked
(their words outrank a missing or mislabeled fence), write, and render the reply
with the app's result lines in place of the fences.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.todos import proposals, write_log
from app.modules.todos.actions import MAX_TODO_ACTIONS_PER_TURN
from app.modules.todos.card_retime import retime_untapped_card
from app.modules.todos.offer_reply import accepted_reminder_offer
from app.modules.todos.read_asks import asks_to_read_reminders
from app.modules.todos.recurrence import next_recurring_due
from app.modules.todos.reminder_fence_parse import (
    ReminderFence,
    explicit_user_remind,
    explicitly_declines_reminder_creation,
    find_reminder_fences,
    parse_fence,
)
from app.modules.todos.reminder_writes import ReminderWrites, create_one, load_existing, mutate_one
from app.modules.todos.reply_check import (
    about_saved_reminders,
    edits_prior_reply,
    reply_when_nothing_saved,
)
from app.modules.todos.reply_claims import without_claims, without_when_questions
from app.modules.todos.spoken_add import (
    SpokenAdd,
    chat_add_needs_a_stated_time,
    due_for_add,
    due_is_past,
    parse_spoken_add,
    passed_time_reply,
    relative_due,
)
from app.modules.todos.spoken_apply import apply_spoken_change, format_reminder_reading
from app.modules.todos.spoken_change import (
    asks_about_my_reminders,
    names_reminders,
    parse_spoken_reminder_change,
)
from app.modules.todos.spoken_clauses import answered_when, parse_spoken_adds
from app.services.draft_fences import has_draft

logger = logging.getLogger(__name__)

# "Always remind me to drink water" got a repeating fence with no start time,
# and the user read "the format was invalid". Nothing was saved: ask when.
_ASK_WHEN = "When should I remind you?"
# One of two reminders in a message with no time, or one already past.
_ASK_WHEN_FOR = "When should I remind you to {title}?"
# Each fence in the reply: (start, end, body).
_Spans = list[tuple[int, int, str]]


async def materialize_reminder_fences(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_id: UUID,
    assistant_text: str,
    user_timezone: str | None,
    user_text: str | None = None,
    prior_assistant: str | None = None,
    prior_user: str | None = None,
    redis: Redis | None = None,
    confirm: bool = False,
    window: Sequence[object] | None = None,
) -> tuple[str, int]:
    """Apply the turn's To-do changes, or with ``confirm`` offer them as a card.

    With ``confirm`` the same rules run, but nothing is written: the reply ends
    with a ``reminder_proposal`` card in place of the result lines, and the
    writes wait in Redis for the user's tap. Returns (text, rows written).
    ``window``: the chat's last messages as the turn read them, its user's message
    last (``card_retime.retime_untapped_card``); None reads them.

    The writes join the caller's session and are never committed or rolled back
    here: the caller commits them with its own rows (live talk's voice turn) or
    rolls them back (code-health audit ARCH-07).
    """
    turn = partial(
        _materialize,
        session,
        user_id=user_id,
        chat_id=chat_id,
        assistant_text=proposals.strip_cards(assistant_text),
        user_timezone=user_timezone,
        user_text=user_text,
        prior_assistant=prior_assistant,
        prior_user=prior_user,
        window=window,
    )
    if not confirm or redis is None:
        return await turn()
    with write_log.recording() as writes:
        text, _applied = await turn()
    if not writes:
        return text, 0
    card = await proposals.propose(
        redis,
        user_id=user_id,
        chat_id=chat_id,
        writes=writes,
        user_timezone=user_timezone,
    )
    kept = [line for line in text.split("\n") if not proposals.is_card_line(line, writes)]
    # Nothing is saved until the tap: "Done! I've set a reminder" would be false.
    body = without_claims("\n".join(kept), [write.title for write in writes])
    return (f"{body}\n\n{card}" if body else card), 0


@dataclass(frozen=True)
class _Turn:
    """The reply being finished and the words around it."""

    session: AsyncSession
    user_id: UUID
    chat_id: UUID
    assistant_text: str
    user_timezone: str | None
    user_text: str | None
    prior_assistant: str | None
    prior_user: str | None
    window: Sequence[object] | None = None
    # The last reply's offer of a reminder that this message ("yes") accepts.
    offer: str | None = None

    @property
    def said(self) -> str | None:
        """What the user agreed to: their words, and the offer they said yes to."""
        if self.offer is None:
            return self.user_text
        return f"{self.user_text or ''} {self.offer}".strip()

    def writes(self) -> ReminderWrites:
        return ReminderWrites(
            session=self.session,
            user_id=self.user_id,
            chat_id=self.chat_id,
            user_timezone=self.user_timezone,
        )


async def _materialize(
    session: AsyncSession,
    *,
    user_id: UUID,
    chat_id: UUID,
    assistant_text: str,
    user_timezone: str | None,
    user_text: str | None = None,
    prior_assistant: str | None = None,
    prior_user: str | None = None,
    window: Sequence[object] | None = None,
) -> tuple[str, int]:
    """Apply To-do fences (create + mutations) and strip them from the reply.

    ``prior_assistant`` is the reply before this turn: "mark it done" points at
    a reminder only after a reply about reminders, or right after a message
    (``prior_user``) that asked about them.

    Returns (updated_text, applied_count). Saves from a valid fence. If the model
    omitted the fence, or emitted an invalid one, an explicit user "remind me …
    today/tomorrow at 6pm" (clock required) is applied so the dated To-do is saved.
    """
    turn = _Turn(
        session=session,
        user_id=user_id,
        chat_id=chat_id,
        assistant_text=assistant_text,
        user_timezone=user_timezone,
        user_text=user_text,
        prior_assistant=prior_assistant,
        prior_user=prior_user,
        window=window,
        offer=accepted_reminder_offer(user_text, prior_assistant),
    )
    spans = find_reminder_fences(assistant_text)
    # The user's explicit restraint outranks an LLM-emitted write fence. This
    # is the last boundary before an external state change, so fail closed even
    # when the model misunderstood "don't create a reminder".
    if explicitly_declines_reminder_creation(user_text):
        if not spans:
            return reply_when_nothing_saved(assistant_text, user_text), 0
        kept = _render(assistant_text, spans, [""] * len(spans), [])
        return reply_when_nothing_saved(kept, user_text), 0
    matched = await _match_user_words(turn, spans)
    if matched is not None:
        return matched
    if not spans:
        return await _save_user_remind(turn)
    return await _apply_fences(turn, spans)


async def _match_user_words(turn: _Turn, spans: _Spans) -> tuple[str, int] | None:
    """The turn as the user's own words decide it, or None to go by the fences."""
    # Right after a draft, "add that I'll be late tomorrow at 9am" edits the
    # draft. Only a message that says reminder or task touches reminders.
    if not spans and has_draft(turn.prior_assistant) and not names_reminders(turn.user_text):
        return turn.assistant_text, 0
    # A question about the schedule is answered from the saved rows. The model's
    # list is discarded, including any reminder it invented.
    if asks_to_read_reminders(turn.user_text):
        state = turn.writes()
        await load_existing(state)
        return format_reminder_reading(state.existing, turn.user_timezone), 0
    # "Actually make it 8" re-times the card just offered, not the latest saved reminder.
    retimed = await retime_untapped_card(
        turn.session,
        turn.chat_id,
        turn.user_text,
        user_timezone=turn.user_timezone,
        window=turn.window,
    )
    if retimed:
        return await _save_spoken_adds(replace(turn, assistant_text=""), [], retimed)
    # The user's words outrank a missing or mislabeled fence. "Mark done"
    # must check the row, not delete it, and the reply is only that result.
    spoken = parse_spoken_reminder_change(turn.user_text, user_timezone=turn.user_timezone)
    if spoken is not None:
        applied = await apply_spoken_change(
            turn.session,
            user_id=turn.user_id,
            chat_id=turn.chat_id,
            user_timezone=turn.user_timezone,
            spoken=spoken,
            user_text=turn.user_text,
            prior_assistant=turn.prior_assistant,
            prior_user=turn.prior_user,
            reply=turn.assistant_text,
        )
        if applied is not None:
            return applied
    answered = await _match_clock_reply(turn, widen=not spans)
    if answered is not None:
        return answered
    return await _match_spoken_add(turn, spans)


async def _match_clock_reply(turn: _Turn, *, widen: bool) -> tuple[str, int] | None:
    """A reply that is only a time finishes the add the user just described."""
    stated = await answered_when(
        turn.session,
        turn.chat_id,
        turn.user_text or "",
        turn.prior_assistant,
        user_timezone=turn.user_timezone,
        widen=widen,
    )
    if stated is None:
        return None
    if _upcoming_due(stated, turn.user_timezone) is None:
        return passed_time_reply(), 0
    # The message is only the time: there is nothing else for a reply to answer.
    return await _save_spoken_adds(replace(turn, assistant_text=""), [], [stated])


async def _match_spoken_add(turn: _Turn, spans: _Spans) -> tuple[str, int] | None:
    """An add the user stated with a day and a clock, saved without a fence."""
    adds = parse_spoken_adds(turn.user_text, user_timezone=turn.user_timezone)
    if not adds:
        return None
    if len(adds) > 1:
        # Two reminders in one message: the model's own fences, when it wrote
        # them, decide; otherwise each clause is saved with its own time.
        return None if spans else await _save_spoken_adds(turn, spans, adds)
    stated = adds[0]
    if (
        not spans
        and not names_reminders(turn.user_text)
        and not asks_about_my_reminders(turn.prior_user)
        and edits_prior_reply(
            stated.title, prior_assistant=turn.prior_assistant, reply=turn.assistant_text
        )
    ):
        return turn.assistant_text, 0
    # The model's own reminder fence, when it wrote one, keeps its cleaner title,
    # unless its time already passed: "at 7pm" said at 9pm is tomorrow's 7pm, and
    # the model's "today 19:00" saved nothing and emptied the reply.
    if spans:
        title = _past_fence_title(spans, turn.user_timezone)
        if title is None:
            return None
        stated = replace(stated, title=title)
    if stated.after_minutes is None and (stated.day is None or stated.hour is None):
        return None
    if _upcoming_due(stated, turn.user_timezone) is None:
        return passed_time_reply(), 0
    return await _save_spoken_adds(turn, spans, [stated])


def _upcoming_due(add: SpokenAdd, user_timezone: str | None) -> datetime | None:
    """The instant to save; a repeat that passed moves on, a one-off that passed is None."""
    due = due_for_add(add, user_timezone=user_timezone)
    if due is not None and add.repeat and due_is_past(due, user_timezone=user_timezone):
        due = next_recurring_due(due, add.repeat, now=datetime.now(UTC), timezone=user_timezone)
    if due is None or due_is_past(due, user_timezone=user_timezone):
        return None
    return due


def _past_fence_title(spans: _Spans, user_timezone: str | None) -> str | None:
    """The title of the turn's one add fence when its time already passed."""
    if len(spans) != 1:
        return None
    draft = parse_fence(spans[0][2])
    if draft is None or draft.action != "add" or draft.due_at is None:
        return None
    return draft.title if due_is_past(draft.due_at, user_timezone=user_timezone) else None


async def _save_user_remind(turn: _Turn) -> tuple[str, int]:
    """No fence: save an explicit "remind me … at 6pm", or pass on no false claim."""
    draft = _user_remind(turn)
    if draft is None:
        # Right after a reply about saved reminders, "Moved **gym** to Sunday"
        # with nothing moved is a false claim.
        about = about_saved_reminders(turn.prior_assistant) or asks_about_my_reminders(
            turn.prior_user
        )
        reply = reply_when_nothing_saved(turn.assistant_text, turn.user_text, about_reminders=about)
        return reply, 0
    line, ok = await create_one(turn.writes(), draft)
    updated = turn.assistant_text.strip()
    if not ok:
        # "Could not set …" follows: the model's "I've set it" is false.
        updated = without_claims(updated, [draft.title])
    if line:
        updated = f"{updated}\n\n{line}" if updated else line
    return _tidy(updated), (1 if ok else 0)


@dataclass(frozen=True)
class _FenceResult:
    """What one fence came to: its result line, and whether it stays as invalid."""

    line: str | None = None
    ok: bool = False
    invalid: bool = False


async def _apply_fences(turn: _Turn, spans: _Spans) -> tuple[str, int]:
    """Write each fence, up to the per-turn cap, and render the reply."""
    # Open reminders are loaded once, lazily, on the first create. Mutations go
    # through apply_todo_actions, which loads its own snapshot.
    state = turn.writes()
    in_place: list[str] = []
    result_lines: list[str] = []
    invalid_any = False
    for _start, _end, body in spans:
        result = _FenceResult()
        if state.applied < MAX_TODO_ACTIONS_PER_TURN:
            result = await _apply_fence(turn, state, body)
        in_place.append("")
        invalid_any = invalid_any or result.invalid
        if result.line is not None:
            result_lines.append(result.line)
        if result.ok:
            state.applied += 1
    updated = _render(turn.assistant_text, spans, in_place, result_lines)
    if state.applied == 0:
        updated = reply_when_nothing_saved(updated, turn.user_text, about_reminders=True)
        if invalid_any and not updated.strip():
            updated = _ASK_WHEN
    return updated, state.applied


async def _apply_fence(turn: _Turn, state: ReminderWrites, body: str) -> _FenceResult:
    draft = parse_fence(body)
    if draft is None:
        logger.warning("Invalid reminder fence payload for user_id=%s", state.user_id)
        return await _apply_invalid_fence(turn, state)
    if draft.action == "add" and chat_add_needs_a_stated_time(turn.said, draft.due_at):
        return await _apply_stated_clock(turn, state)
    # "In 3 minutes" is the server's arithmetic on the user's clock, not the model's.
    after = relative_due(turn.user_text, user_timezone=turn.user_timezone)
    if draft.action == "add" and after is not None:
        draft = draft.model_copy(update={"due_at": after})
    if (
        draft.action == "add"
        and turn.user_text is not None
        and draft.due_at is not None
        and due_is_past(draft.due_at, user_timezone=turn.user_timezone)
    ):
        # Saying nothing left an empty reply: the user hears the time passed.
        return _FenceResult(line=passed_time_reply())
    if draft.action == "add":
        line, ok = await create_one(state, draft)
        return _FenceResult(line=line, ok=ok)
    line, ok = await mutate_one(state, draft)
    return _FenceResult(line=line, ok=ok)


async def _apply_invalid_fence(turn: _Turn, state: ReminderWrites) -> _FenceResult:
    """An invalid fence saves the user's explicit "remind me … at 6pm", or asks when."""
    fallback = _user_remind(turn)
    if fallback is None:
        return _FenceResult(invalid=True)
    line, ok = await create_one(state, fallback)
    return _FenceResult(line=line, ok=ok, invalid=not ok)


async def _apply_stated_clock(turn: _Turn, state: ReminderWrites) -> _FenceResult:
    """The fence time was not in the user's message: save only a clock they wrote.

    Otherwise nothing is saved, and the reply asks when.
    """
    fallback = _user_remind(turn)
    due_at = fallback.due_at if fallback is not None else None
    if fallback is None or due_at is None or due_is_past(due_at, user_timezone=turn.user_timezone):
        return _FenceResult()
    line, ok = await create_one(state, fallback)
    return _FenceResult(line=line, ok=ok)


def _user_remind(turn: _Turn) -> ReminderFence | None:
    """The reminder the user's own words state: "… at 6pm", or "… in 3 minutes"."""
    stated = explicit_user_remind(turn.user_text, turn.user_timezone)
    if stated is not None:
        return stated
    after = relative_due(turn.user_text, user_timezone=turn.user_timezone)
    add = parse_spoken_add(turn.user_text) if after is not None else None
    return None if add is None else ReminderFence(action="add", title=add.title, due_at=after)


def _render(text: str, spans: _Spans, in_place: list[str], result_lines: list[str]) -> str:
    """The reply with each fence replaced by ``in_place``, then the result lines."""
    parts: list[str] = []
    last = 0
    for (start, end, _body), kept in zip(spans, in_place, strict=True):
        parts.append(text[last:start])
        parts.append(kept)
        last = end
    parts.append(text[last:])
    updated = "".join(parts).strip()
    if result_lines:
        updated = f"{updated}\n\n" + "\n".join(result_lines) if updated else "\n".join(result_lines)
    return _tidy(updated)


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def _save_spoken_adds(turn: _Turn, spans: _Spans, adds: list[SpokenAdd]) -> tuple[str, int]:
    """Save each add, or ask when for one with no time or a time that passed.

    The model's answer stays, minus the fences and any claim of its own: "What
    is the boiling point of water? Also remind me…" keeps "Water boils at 100 °C".
    """
    state = turn.writes()
    lines: list[str] = []
    for add in adds[:MAX_TODO_ACTIONS_PER_TURN]:
        timed = add.hour is not None or add.after_minutes is not None
        due = _upcoming_due(add, turn.user_timezone) if timed else None
        if due is None:
            lines.append(_ASK_WHEN_FOR.format(title=add.title))
            continue
        draft = ReminderFence(action="add", title=add.title, due_at=due)
        draft.repeat = add.repeat
        line, ok = await create_one(state, draft)
        lines.append(line)
        state.applied += 1 if ok else 0
    answer = _render(turn.assistant_text, spans, [""] * len(spans), [])
    if state.applied:
        answer = without_when_questions(answer)
    titles = [add.title for add in adds]
    return _render(without_claims(answer, titles), [], [], lines), state.applied
