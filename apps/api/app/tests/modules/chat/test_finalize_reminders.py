"""A reply cut off inside its ```reminder fence reaches the reminder pass without it."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.finalize_reminders import apply_reminder_pass, drop_cut_reminder_fence
from app.modules.chat.turn_prep.context import StreamContext
from app.services.md_fence_scan import close_unclosed_fences
from app.tests.modules.chat.chat_test_support import turn_deps

_CUT = 'Sure.\n\n```reminder\n{"title": "Dentist", "due_at": "2026-10-15T15:00'
_CLOSED = 'Sure.\n\n```reminder\n{"title": "Dentist"}\n```'


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        (_CUT, "Sure."),
        ('```reminder\n{"title": "Den', ""),
        ("Here:\n\n```Reminder\n{", "Here:"),
        (f"```python\nprint(1)\n```\n\n{_CUT}", "```python\nprint(1)\n```\n\nSure."),
        # Closed fences, other open fences and plain prose are not the reminder pass's.
        (_CLOSED, _CLOSED),
        ("Sure.\n\n```python\nprint(1", "Sure.\n\n```python\nprint(1"),
        ('```reminder_proposal\n{"proposal_id": "a"', '```reminder_proposal\n{"proposal_id": "a"'),
        ("No fences at all.", "No fences at all."),
    ],
)
def test_drop_cut_reminder_fence_drops_only_an_open_reminder_fence(text: str, kept: str) -> None:
    assert drop_cut_reminder_fence(text) == kept


def test_a_dropped_fence_leaves_nothing_for_the_fence_repair_to_close() -> None:
    assert close_unclosed_fences(drop_cut_reminder_fence(_CUT)) == "Sure."


@pytest.mark.asyncio
async def test_a_reply_emptied_by_the_reminder_pass_asks_when() -> None:
    """A reply that was only a fence, with nothing saved, came back empty: done
    carried nothing, so the phone kept the streamed fence."""
    deps = turn_deps(todos={"materialize_reminder_fences": AsyncMock(return_value=("", 0))})
    ctx = SimpleNamespace(
        user=MagicMock(timezone="UTC"),
        user_id=uuid4(),
        chat_id=uuid4(),
        user_timezone="UTC",
        user_message_content="remind me to plate the dinner",
        prompt_messages=[],
        recent_messages=None,
        skip_memory_jobs=True,
    )
    text = await apply_reminder_pass(
        deps, AsyncMock(), Settings(), cast(StreamContext, ctx), _CLOSED, None
    )
    assert text == "When should I remind you?"


@pytest.mark.asyncio
@pytest.mark.parametrize(("created", "changed"), [(0, False), (2, True)])
async def test_the_list_is_flagged_changed_only_when_rows_were_written(
    created: int, changed: bool
) -> None:
    """``todos_changed`` sent the phone to reload its list three times for a background
    extraction that no longer exists (code-health audit NET-14)."""
    from app.modules.chat.turn_outcome import TurnOutcome

    deps = turn_deps(
        todos={"materialize_reminder_fences": AsyncMock(return_value=("Done.", created))}
    )
    ctx = SimpleNamespace(
        user=MagicMock(timezone="UTC"),
        user_id=uuid4(),
        chat_id=uuid4(),
        user_timezone="UTC",
        user_message_content="yes, move them all to tomorrow",
        prompt_messages=[],
        recent_messages=None,
        skip_memory_jobs=False,
    )
    outcome = TurnOutcome()
    await apply_reminder_pass(
        deps, AsyncMock(), Settings(), cast(StreamContext, ctx), "Done.", outcome
    )
    assert outcome.todos_changed is changed


def _ctx(message: str, locale: str = "en", prior: str | None = None) -> StreamContext:
    earlier = [{"role": "user", "content": prior}, {"role": "assistant", "content": "?"}]
    return cast(
        StreamContext,
        SimpleNamespace(
            user=MagicMock(timezone="UTC", locale=locale),
            user_id=uuid4(),
            chat_id=uuid4(),
            user_timezone="UTC",
            user_message_content=message,
            prompt_messages=[*(earlier if prior else []), {"role": "user", "content": message}],
            recent_messages=None,
            skip_memory_jobs=True,
        ),
    )


_SPANISH = "recuérdame mañana a las 9 llamar a mamá"
_LINK = "```todo_link\n```"
_ES_LINE = "Puedes añadirlo o cambiarlo en **Tareas**."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reply", "kept"),
    [
        # The model wrote a reminder anyway: no card, the server's line and button instead.
        (
            'Claro.\n\n```reminder\n{"title": "Llamar a mamá", "due_at": "2026-10-24T09:00:00"}\n```',
            f"{_ES_LINE}\n\n{_LINK}",
        ),
        # Live, beside the button: "Done. I've added Buy milk…" for a change nothing made.
        (
            f"Ya está. He añadido **Comprar leche** para mañana a las 17:00.\n\n{_LINK}",
            f"{_ES_LINE}\n\n{_LINK}",
        ),
        # A reply with no words of its own still says, in Spanish, where to go.
        ('```reminder\n{"title": "Llamar a mamá"}\n```', f"{_ES_LINE}\n\n{_LINK}"),
        (_LINK, f"{_ES_LINE}\n\n{_LINK}"),
        # A search the model made (the time zone) cites nothing above the button.
        (
            f'```sources\n[{{"title": "EAT", "url": "https://time.example"}}]\n```\n\n{_LINK}',
            f"{_ES_LINE}\n\n{_LINK}",
        ),
        # The model already offered the button: the server's line says the same.
        (f"Puedes añadirlo en Tareas.\n\n{_LINK}", f"{_ES_LINE}\n\n{_LINK}"),
        # A read of the list is left as it is.
        ("Hoy tienes: llamar a mamá.", "Hoy tienes: llamar a mamá."),
    ],
)
async def test_a_message_in_another_language_gets_the_todo_button_not_a_card(
    reply: str, kept: str
) -> None:
    materialize = AsyncMock(return_value=("unused", 1))
    deps = turn_deps(todos={"materialize_reminder_fences": materialize})
    text = await apply_reminder_pass(deps, AsyncMock(), Settings(), _ctx(_SPANISH), reply, None)
    # Exactly the kept reply: never the English "when?" the reminder pass answers with.
    assert text == kept
    materialize.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "locale", "line"),
    [
        ("напомни завтра в 9 позвонить маме", "en", "Добавить или изменить это можно в разделе **Задачи**."),
        ("ነገ 9 ሰዓት እናቴን እንድደውል አስታውሰኝ", "en", "በ**የሚደረጉ** ውስጥ ማከል ወይም መቀየር ይችላሉ።"),
        ("rappelle-moi demain à 9h d'appeler maman", "en", "Vous pouvez l'ajouter ou le modifier dans **Tâches**."),
        ("erinnere mich morgen um 9 Uhr, Mama anzurufen", "es", "Du kannst das unter **Aufgaben** hinzufügen oder ändern."),
        # A language the app has no line for: the user's own app language, then English.
        ("ذكرني غدا الساعة 9 بالاتصال بأمي", "es", _ES_LINE),
        ("ذكرني غدا الساعة 9 بالاتصال بأمي", "en", "You can add or change it in **To-do**."),
    ],
)  # fmt: skip
async def test_the_line_above_a_bare_button_is_in_the_message_s_language(
    message: str, locale: str, line: str
) -> None:
    deps = turn_deps(todos={"materialize_reminder_fences": AsyncMock()})
    text = await apply_reminder_pass(
        deps, AsyncMock(), Settings(), _ctx(message, locale), _LINK, None
    )
    assert text == f"{line}\n\n{_LINK}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "prior", "locale"),
    [
        # The answer to "¿cuándo?" has no language of its own: the Spanish chat decides.
        ("a las 5", "añade comprar leche a mis tareas", "en"),
        ("17:00", "recuérdame llamar a mamá", "en"),
        # A Spanish user's first message with no language of its own.
        ("leche 17:00", None, "es"),
    ],
)
async def test_an_answer_in_a_spanish_chat_never_writes_a_to_do(
    message: str, prior: str | None, locale: str
) -> None:
    materialize = AsyncMock(return_value=("unused", 1))
    deps = turn_deps(todos={"materialize_reminder_fences": materialize})
    reply = '```reminder\n{"title": "Comprar leche", "due_at": "2026-10-24T17:00:00"}\n```'
    text = await apply_reminder_pass(
        deps, AsyncMock(), Settings(), _ctx(message, locale, prior), reply, None
    )
    assert text == f"{_ES_LINE}\n\n{_LINK}"
    materialize.assert_not_called()


@pytest.mark.asyncio
async def test_an_english_message_still_reaches_the_reminder_pass() -> None:
    materialize = AsyncMock(return_value=("Saved.", 1))
    deps = turn_deps(todos={"materialize_reminder_fences": materialize})
    text = await apply_reminder_pass(
        deps, AsyncMock(), Settings(), _ctx("remind me to call mom at 9"), _CLOSED, None
    )
    assert text == "Saved."
    materialize.assert_awaited_once()


_REMEMBER = (
    "Ok making the paste first is smart, ill try that this weekend. "
    "Remember that i want to try cacao e Pepe again"
)
_TODO_CLAIM = "I've added that to your to-do list so you don't forget. \U0001f35d"


def _remember_ctx(message: str, *, memory: bool = True) -> StreamContext:
    ctx = _ctx(message)
    cast(SimpleNamespace, ctx).user = MagicMock(timezone="UTC", locale="en", memory_enabled=memory)
    return ctx


def _unchanged_by_the_writes() -> AsyncMock:
    async def materialize(*_args: object, **kwargs: object) -> tuple[str, int]:
        return str(kwargs["assistant_text"]), 0

    return AsyncMock(side_effect=materialize)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "reply", "memory", "kept"),
    [
        # Live (2026-10-25): saved to memory, called a to-do.
        (_REMEMBER, _TODO_CLAIM, True, "Got it, I'll remember that."),
        (
            _REMEMBER,
            _TODO_CLAIM,
            False,
            "Memory is off, so I didn't save that. You can turn it on in Settings → Memory.",
        ),
        (
            _REMEMBER,
            "Nice, the paste trick works. I've added that to your to-do list.",
            True,
            "Nice, the paste trick works.",
        ),
        (_REMEMBER, "Got it, I'll remember that you want to try it again.", True, None),
        # A one-off item memory won't keep: no promise to remember it.
        (
            "please remember my flight is Friday at 6am",
            "I've set a reminder for your flight.",
            True,
            "Got it.",
        ),
        # Memory's own words stay (review, 2026-10-25).
        (
            "remember that my dentist appointment is tomorrow at 3pm",
            "Got it! I've noted that your dentist appointment is tomorrow at 3 PM. If you'd "
            "like, I can also set a reminder.",
            True,
            None,
        ),
        (
            "please remember my flight is Friday at 6am",
            "Saved — your flight is Friday at 6 AM. Want a reminder the night before?",
            True,
            None,
        ),
        (
            "remember that I go to the gym every Monday, Wednesday and Friday at 7am",
            "Got it! I've noted that you go to the gym then. I won't add it to your to-dos "
            "unless you ask.",
            True,
            None,
        ),
        (
            "save to memory that I use Todoist for my tasks",
            "Saved: you use Todoist for your tasks.",
            True,
            None,
        ),
        (
            "Save to memory that I'm lactose intolerant",
            "Saved: you're lactose intolerant.",
            True,
            None,
        ),
        (
            _REMEMBER,
            "Cacio e pepe is a Roman classic! I'll add it to your list of dishes to try.",
            True,
            None,
        ),
        # Code that says "list" is left alone.
        (
            _REMEMBER,
            "Noted.\n\n```python\nitems.append(x)  # I've added x to the list\n```",
            True,
            None,
        ),
        # A to-do card offered on the same turn is the user's to tap.
        (
            "remember that i like it salty and remind me to buy pecorino at 5",
            'I\'ve added that to your to-do list.\n\n```reminder_proposal\n{"proposal_id": "a"}\n```',
            True,
            None,
        ),
        # Not a remember turn: the reminder pass's own rules decide.
        ("what's on my list", "Your reminder Study pharm is set for Wednesday.", True, None),
        ("forget that i like sushi", _TODO_CLAIM, True, None),
    ],
)
async def test_a_remember_turn_claims_no_todo(
    message: str, reply: str, memory: bool, kept: str | None
) -> None:
    deps = turn_deps(todos={"materialize_reminder_fences": _unchanged_by_the_writes()})
    text = await apply_reminder_pass(
        deps, AsyncMock(), Settings(), _remember_ctx(message, memory=memory), reply, None
    )
    assert text == (reply if kept is None else kept)
