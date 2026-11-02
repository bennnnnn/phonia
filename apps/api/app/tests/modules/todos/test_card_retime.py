"""A new time for the card the user has not tapped re-offers that card's add."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.modules.conversation import messages_repository as messages_repo
from app.modules.todos.card_retime import (
    _reply_before_last_message,
    retime_untapped_card,
    retimed_adds,
)
from app.tests.modules.todos.test_reminder_proposals import (
    _card,
    _rows,
    _saved,
    _turn,
    _user_and_chat,
)

_TZ = "America/Indiana/Indianapolis"


def _card_fence(title: str = "Study bio", status: str | None = None, action: str = "add") -> str:
    card: dict[str, Any] = {
        "proposal_id": "p1",
        "tz": _TZ,
        "items": [{"action": action, "title": title, "due_at": "2026-10-23T23:00:00Z"}],
    }
    if status:
        card["status"] = status
    return f"```reminder_proposal\n{json.dumps(card)}\n```"


@pytest.mark.parametrize(
    ("said", "hour", "minute"),
    [
        # Live: these moved the latest saved reminder, or found no "study" one.
        ("actually make it 8", 20, 0),
        ("no not that one, the study one. 8pm", 20, 0),
        ("8pm instead", 20, 0),
        ("make it 8:30", 20, 30),
        ("what about 8?", 20, 0),
        # An am/pm the user says is kept.
        ("can you make it 9 am", 9, 0),
    ],
)
def test_a_new_time_re_times_the_untapped_card(said: str, hour: int, minute: int) -> None:
    [add] = retimed_adds(_card_fence(), said, user_timezone=_TZ) or []
    assert (add.title, add.day, add.hour, add.minute) == ("Study bio", "10-23", hour, minute)


@pytest.mark.parametrize(
    ("previous", "said"),
    [
        # A new reminder, more than a time, no time at all.
        (_card_fence(), "remind me to call mom at 8"),
        (_card_fence(), "and gym at 8"),
        (_card_fence(), "make it 8 and also call mom"),
        (_card_fence(), "ok thanks"),
        # A card already saved, a change card, or no card.
        (_card_fence(status="saved"), "make it 8"),
        (_card_fence(action="set_due"), "make it 8"),
        ("Pasta is quick tonight.", "make it 8"),
        # Beside the card the reply asked a time for another reminder: "9am" answers it.
        (f"When should I remind you to pay rent?\n\n{_card_fence()}", "9am"),
    ],
)
def test_anything_else_is_not_a_re_time(previous: str, said: str) -> None:
    assert retimed_adds(previous, said, user_timezone=_TZ) is None


def test_the_reply_before_a_regenerated_one_is_the_card() -> None:
    rows = [
        SimpleNamespace(role="user", content="remind me to study bio at 7pm"),
        SimpleNamespace(role="assistant", content=_card_fence()),
        SimpleNamespace(role="user", content="actually make it 8"),
        # Regenerating: the reply being replaced is still saved.
        SimpleNamespace(role="assistant", content="Moved Take chicken out of freezer."),
    ]
    assert _reply_before_last_message(rows) == _card_fence()
    assert _reply_before_last_message(rows[:3]) == _card_fence()


class _CountingSession:
    """A session that only counts what is asked of it."""

    def __init__(self) -> None:
        self.reads = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        self.reads += 1
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=list))


@pytest.mark.asyncio
async def test_a_window_with_no_untapped_card_reads_nothing_again() -> None:
    """Every turn's reminder pass read the chat's last four messages again in finalize, one
    database round trip before the reply settled, though the turn had just read them."""
    session = _CountingSession()
    window = [
        SimpleNamespace(role="user", content="What's the capital of France?"),
        SimpleNamespace(role="assistant", content="Paris."),
        SimpleNamespace(role="user", content="actually make it 8"),
    ]
    for rows in (window, window[2:], [*window[:2], *window[:2], window[2]]):
        retimed = await retime_untapped_card(
            session,  # type: ignore[arg-type]
            uuid4(),
            "actually make it 8",
            user_timezone=_TZ,
            window=rows,
        )
        assert retimed is None
    assert session.reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "saved"])
async def test_a_window_with_an_untapped_card_reads_the_chat_as_saved(
    status: str | None, db_session: Any
) -> None:
    """The window shows the card untapped; a tap may have saved it since: the saved chat
    decides, as it did before the window was passed."""
    user, chat = await _user_and_chat(db_session)
    for role, content in (
        ("user", "remind me to study bio at 7pm"),
        ("assistant", _card_fence(status=status)),
        ("user", "actually make it 8"),
    ):
        await messages_repo.create(
            db_session, chat_id=chat.id, user_id=user.id, role=role, content=content
        )
    window = [
        SimpleNamespace(role="assistant", content=_card_fence()),
        SimpleNamespace(role="user", content="actually make it 8"),
    ]
    retimed = await retime_untapped_card(
        db_session, chat.id, "actually make it 8", user_timezone=_TZ, window=window
    )
    assert (retimed is None) is (status == "saved")


@pytest.mark.asyncio
async def test_make_it_8_re_offers_the_card_and_moves_nothing_else(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    other = await _saved(db_session, user, "Take chicken out of freezer")
    asked = "remind me tomorrow at 6pm to call mom"
    await messages_repo.create(
        db_session, chat_id=chat.id, user_id=user.id, role="user", content=asked
    )
    first = _card(await _turn(db_session, fake_redis, user, chat, asked, "Sure."))
    assert first["items"][0]["action"] == "add"
    await messages_repo.create(
        db_session, chat_id=chat.id, user_id=user.id, role="user", content="actually make it 8"
    )
    # Live, the model's own fence moved the latest saved reminder.
    wrong = (
        '```reminder\n{"action":"set_due","title":"Take chicken out of freezer",'
        '"due_at":"2026-10-23T20:00:00"}\n```'
    )
    card = _card(await _turn(db_session, fake_redis, user, chat, "actually make it 8", wrong))
    [item] = card["items"]
    assert item["action"] == "add"
    assert item["title"].lower() == "call mom"
    due = datetime.fromisoformat(item["due_at"]).astimezone(UTC)
    assert (due.date(), due.hour) == (
        datetime.fromisoformat(first["items"][0]["due_at"]).astimezone(UTC).date(),
        20,
    )
    [row] = await _rows(db_session, user.id)
    assert row.id == other.id and row.due_at == other.due_at
