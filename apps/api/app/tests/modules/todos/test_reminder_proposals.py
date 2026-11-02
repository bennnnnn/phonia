"""A reminder change from chat waits for a tap on its card (Postgres + fake Redis)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.modules.conversation import chats_repository as chats_repo
from app.modules.conversation import messages_repository as messages_repo
from app.modules.todos import proposals, write_log
from app.modules.todos import repository as todos_repo
from app.modules.todos.models import TodoItem
from app.modules.todos.prompt_hint import TODO_HINT
from app.modules.todos.reminder_fences import materialize_reminder_fences
from app.repositories import users as users_repo

_CARD = re.compile(r"```reminder_proposal\n(.*?)\n```", re.DOTALL)


async def _user_and_chat(session: Any) -> tuple[Any, Any]:
    user = await users_repo.create(
        session,
        email=f"{uuid4()}@example.com",
        name="Test User",
        avatar_url=None,
        google_sub=str(uuid4()),
    )
    chat = await chats_repo.create(session, user_id=user.id, model="free-chat")
    return user, chat


# The morning turns' fixed clock: their tests assert exact due times and never tap a card.
_MORNING = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def _next_wednesday_morning() -> datetime:
    now = datetime.now(UTC)
    days = (2 - now.weekday()) % 7 or 7
    return (now + timedelta(days=days)).replace(hour=6, minute=0, second=0, microsecond=0)


# What the other turns read: on the real clock, "thursday at 5pm" asked on a Thursday
# evening was a time already gone, and CI failed on Thursdays. Next Wednesday's morning
# is always a Wednesday, and still ahead of the real clock a tap's check reads.
_NEXT_WEDNESDAY = _next_wednesday_morning()


async def _materialize(
    session: Any,
    redis: Any,
    user: Any,
    chat: Any,
    user_text: str,
    reply: str,
    *,
    user_timezone: str,
    clock: datetime,
) -> str:
    with patch("app.modules.todos.spoken_add._now", lambda tz: clock.astimezone(tz)):
        text, written = await materialize_reminder_fences(
            session,
            user_id=user.id,
            chat_id=chat.id,
            assistant_text=reply,
            user_timezone=user_timezone,
            user_text=user_text,
            redis=redis,
            confirm=True,
        )
    assert written == 0
    await messages_repo.create(
        session, chat_id=chat.id, user_id=user.id, role="assistant", content=text
    )
    return text


async def _turn(session: Any, redis: Any, user: Any, chat: Any, user_text: str, reply: str) -> str:
    return await _materialize(
        session, redis, user, chat, user_text, reply, user_timezone="UTC", clock=_NEXT_WEDNESDAY
    )


def _card(text: str) -> dict[str, Any]:
    match = _CARD.search(text)
    assert match, text
    return json.loads(match.group(1))


async def _rows(session: Any, user_id: UUID) -> list[Any]:
    # A plain id: a refused tap rolls back, which expires the loaded user.
    return await todos_repo.list_for_user(session, user_id, limit=50)


async def _saved(session: Any, user: Any, title: str) -> Any:
    return await todos_repo.create(
        session,
        user_id=user.id,
        content=title,
        topic="Reminders",
        due_at=datetime.now(UTC) + timedelta(days=2),
    )


@pytest.mark.asyncio
async def test_spoken_reminder_is_a_card_until_tapped(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    text = await _turn(
        db_session, fake_redis, user, chat, "remind me tomorrow at 6pm to call mom", "Sure."
    )

    card = _card(text)
    assert card["items"][0]["action"] == "add"
    assert card["items"][0]["title"].lower() == "call mom"
    assert card["items"][0]["when"]
    assert "Set:" not in text
    assert await _rows(db_session, user.id) == []

    confirmed = await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user.id, proposal_id=card["proposal_id"]
    )
    assert [item.action for item in confirmed.items] == ["add"]
    rows = await _rows(db_session, user.id)
    assert [row.content.lower() for row in rows] == ["call mom"]
    assert rows[0].due_at is not None and rows[0].due_at.hour == 18
    # The phone applies the saved row instead of reading its list again (NET-16).
    assert confirmed.rows is not None
    assert [row.id for row in confirmed.rows] == [rows[0].id]
    assert confirmed.deleted_ids == []


@pytest.mark.asyncio
async def test_second_tap_saves_once_and_the_chat_shows_it_saved(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    text = await _turn(
        db_session, fake_redis, user, chat, "remind me tomorrow at 9am to water the plants", "Ok."
    )
    proposal_id = _card(text)["proposal_id"]

    first = await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user.id, proposal_id=proposal_id
    )
    again = await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user.id, proposal_id=proposal_id
    )

    assert [item.title for item in again.items] == [item.title for item in first.items]
    # Already saved: the phone reads its list instead.
    assert again.rows is None
    assert len(await _rows(db_session, user.id)) == 1
    [message] = await messages_repo.list_recent(db_session, chat.id, limit=5)
    assert _card(message.content)["status"] == "saved"


def _dentist_fence(hour: int = 15) -> str:
    due = (datetime.now(UTC) + timedelta(days=1)).replace(hour=hour, minute=0, second=0)
    return "```reminder\n" + json.dumps({"title": "Dentist", "due_at": due.isoformat()}) + "\n```"


@pytest.mark.asyncio
async def test_model_fence_becomes_a_card_and_keeps_the_reply(db_session, fake_redis):
    """The model's own words stay above the card; a claim that it is already set does not."""
    user, chat = await _user_and_chat(db_session)
    reply = f"Here it is. Your reminder is set for 3 PM.\n{_dentist_fence()}"
    text = await _turn(
        db_session, fake_redis, user, chat, "add dentist tomorrow at 3pm to my reminders", reply
    )

    assert text.startswith("Here it is.")
    assert "is set for" not in text
    assert _card(text)["items"][0]["title"] == "Dentist"
    assert await _rows(db_session, user.id) == []


@pytest.mark.parametrize(
    "claim",
    [
        "Done! I've set a reminder to call the dentist tomorrow at 9 AM.",
        "All set! I'll remind you tomorrow at 9 AM.",
        "Reminder set for tomorrow at 9 AM.",
        "I've added the dentist to your reminders for tomorrow.",
    ],
)
@pytest.mark.parametrize("fenced", [True, False], ids=["model fence", "user's words"])
@pytest.mark.asyncio
async def test_an_untapped_card_carries_no_claim_it_was_set(db_session, fake_redis, claim, fenced):
    """F8.5: nothing is saved before the tap, so nothing above the card says it was."""
    user, chat = await _user_and_chat(db_session)
    reply = f"{claim}\n\n{_dentist_fence(9)}" if fenced else claim
    text = await _turn(
        db_session, fake_redis, user, chat, "remind me to call the dentist tomorrow at 9am", reply
    )

    assert _card(text)["items"][0]["action"] == "add"
    assert text.startswith("```reminder_proposal"), text
    for words in ("I've set", "I'll remind", "Reminder set", "your reminders", "Done!"):
        assert words not in text
    assert await _rows(db_session, user.id) == []


@pytest.mark.asyncio
async def test_a_card_keeps_what_the_user_said_was_set(db_session, fake_redis):
    """ "The meeting is set for Friday" repeats the user; it is not a reminder claim."""
    user, chat = await _user_and_chat(db_session)
    reply = (
        "The meeting is set for Friday, so Thursday evening is a good time to prep. "
        "I'll remind you Thursday at 5 PM."
    )
    text = await _turn(
        db_session,
        fake_redis,
        user,
        chat,
        "the meeting is set for friday. remind me to prep the slides on thursday at 5pm",
        reply,
    )

    assert text.startswith("The meeting is set for Friday, so Thursday evening is a good time")
    assert "I'll remind you" not in text
    assert _card(text)["items"][0]["title"] == "prep the slides"


@pytest.mark.parametrize(
    ("user_text", "action"),
    [
        ("mark call mom as done", "complete"),
        ("delete the call mom reminder", "delete"),
    ],
)
@pytest.mark.asyncio
async def test_a_change_to_a_saved_reminder_waits_for_the_tap(
    db_session, fake_redis, user_text, action
):
    user, chat = await _user_and_chat(db_session)
    saved = await _saved(db_session, user, "Call mom")

    text = await _turn(db_session, fake_redis, user, chat, user_text, "Ok.")
    card = _card(text)

    assert card["items"] == [{"action": action, "title": "Call mom"}]
    [row] = await _rows(db_session, user.id)
    assert row.id == saved.id and row.checked is False

    confirmed = await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user.id, proposal_id=card["proposal_id"]
    )
    rows = await _rows(db_session, user.id)
    if action == "delete":
        assert rows == []
        assert confirmed.deleted_ids == [saved.id]
        assert confirmed.rows == []
    else:
        assert rows[0].checked is True
        assert confirmed.rows is not None
        assert [(row.id, row.checked) for row in confirmed.rows] == [(saved.id, True)]


@pytest.mark.asyncio
async def test_a_reply_that_changes_nothing_has_no_card(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    text = await _turn(db_session, fake_redis, user, chat, "what is 3 + 3?", "3 + 3 = 6.")
    assert text == "3 + 3 = 6."
    assert await fake_redis.keys("todos:proposal:*") == []


@pytest.mark.asyncio
async def test_an_unknown_card_says_it_expired(db_session, fake_redis):
    user, _chat = await _user_and_chat(db_session)
    with pytest.raises(proposals.ProposalError) as caught:
        await proposals.confirm_proposal(
            db_session, fake_redis, user_id=user.id, proposal_id=str(uuid4())
        )
    assert caught.value.status_code == 410


@pytest.mark.asyncio
async def test_a_time_that_passed_before_the_tap_is_refused(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    user_id = user.id
    text = await _turn(
        db_session, fake_redis, user, chat, "remind me tomorrow at 6pm to call mom", "Sure."
    )
    proposal_id = _card(text)["proposal_id"]
    key = f"todos:proposal:{user.id}:{proposal_id}"
    stored = json.loads(await fake_redis.get(key))
    stored["writes"][0]["fields"]["due_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    await fake_redis.set(key, json.dumps(stored))

    with pytest.raises(proposals.ProposalError) as caught:
        await proposals.confirm_proposal(
            db_session, fake_redis, user_id=user_id, proposal_id=proposal_id
        )
    assert caught.value.status_code == 409
    assert await _rows(db_session, user_id) == []


@pytest.mark.asyncio
async def test_a_reminder_removed_before_the_tap_is_not_recreated(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    user_id = user.id
    saved = await _saved(db_session, user, "Call mom")
    text = await _turn(db_session, fake_redis, user, chat, "mark call mom as done", "Ok.")
    await todos_repo.delete_by_id(db_session, saved.id, user.id)

    with pytest.raises(proposals.ProposalError) as caught:
        await proposals.confirm_proposal(
            db_session, fake_redis, user_id=user_id, proposal_id=_card(text)["proposal_id"]
        )
    assert caught.value.status_code == 409
    assert await _rows(db_session, user_id) == []


@pytest.mark.asyncio
async def test_a_failed_save_leaves_the_card_to_tap_again(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    user_id = user.id
    text = await _turn(
        db_session, fake_redis, user, chat, "remind me tomorrow at 6pm to call mom", "Sure."
    )
    proposal_id = _card(text)["proposal_id"]

    with (
        patch.object(todos_repo, "create", side_effect=RuntimeError("db down")),
        pytest.raises(RuntimeError),
    ):
        await proposals.confirm_proposal(
            db_session, fake_redis, user_id=user_id, proposal_id=proposal_id
        )
    await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user_id, proposal_id=proposal_id
    )
    assert len(await _rows(db_session, user_id)) == 1


@pytest.mark.asyncio
async def test_without_confirm_the_reminder_is_saved_at_once(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    text, written = await materialize_reminder_fences(
        db_session,
        user_id=user.id,
        chat_id=chat.id,
        assistant_text="Sure.",
        user_timezone="UTC",
        user_text="remind me tomorrow at 6pm to call mom",
        redis=fake_redis,
        confirm=False,
    )
    assert written == 1
    assert text.startswith("Set:")
    assert len(await _rows(db_session, user.id)) == 1


def test_recorded_update_leaves_the_loaded_row_alone() -> None:
    row = TodoItem(id=uuid4(), content="Gym", checked=False, topic="Reminders")
    with write_log.recording() as writes:
        planned = write_log.plan_update(writes, row, {"checked": True})
    assert row.checked is False
    assert planned.checked is True
    assert [(w.kind, w.fields) for w in writes] == [("update", {"checked": True})]


def test_deleting_a_row_planned_this_turn_drops_its_create() -> None:
    todo = TodoItem(content="Gym", topic="Reminders")
    with write_log.recording() as writes:
        write_log.plan_create(writes, todo)
        assert write_log.plan_delete(writes, todo.id, None) is True
    assert writes == []


@pytest.mark.parametrize(
    ("kind", "fields", "action"),
    [
        ("create", {}, "add"),
        ("delete", {}, "delete"),
        ("update", {"checked": True}, "complete"),
        ("update", {"checked": False}, "uncheck"),
        ("update", {"topic": "Work"}, "move"),
        ("update", {"due_at": None, "recurrence_rule": None}, "clear_due"),
        ("update", {"due_at": datetime(2026, 1, 1, tzinfo=UTC)}, "set_due"),
        ("update", {"recurrence_rule": "daily"}, "set_due"),
    ],
)
def test_card_action_names_the_change(kind, fields, action) -> None:
    write = write_log.PlannedWrite(kind=kind, todo_id=uuid4(), title="Gym", fields=fields)
    assert proposals.card_action(write) == action


def test_mark_saved_marks_only_its_own_card() -> None:
    content = (
        'Hi\n```reminder_proposal\n{"proposal_id": "a", "items": []}\n```\n'
        '```reminder_proposal\n{"proposal_id": "b", "items": []}\n```'
    )
    marked = proposals.mark_saved(content, "b")
    cards = [json.loads(body) for body in _CARD.findall(marked)]
    assert cards == [
        {"proposal_id": "a", "items": []},
        {"proposal_id": "b", "items": [], "status": "saved"},
    ]


def _fence(card: dict[str, Any]) -> str:
    return f"```reminder_proposal\n{json.dumps(card)}\n```"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (
            None,
            "Card offered, not tapped, so nothing is saved — Set: Gym — Thursday, Oct 15, 6:00 PM.",
        ),
        ("saved", "Set: Gym — Thursday, Oct 15, 6:00 PM."),
    ],
)
def test_history_reads_a_card_as_its_result_line(status, expected) -> None:
    card: dict[str, Any] = {
        "proposal_id": "p",
        "items": [{"action": "add", "title": "Gym", "when": "Thursday, Oct 15, 6:00 PM"}],
    }
    if status:
        card["status"] = status
    text = proposals.reminder_cards_as_text(f"Sure.\n\n{_fence(card)}")
    assert text == f"Sure.\n\n{expected}"
    assert "proposal_id" not in text


def test_history_names_each_kind_of_change() -> None:
    card = {
        "proposal_id": "p",
        "status": "saved",
        "items": [
            {"action": "complete", "title": "Rent"},
            {"action": "delete", "title": "Gym"},
            {"action": "move", "title": "Walk", "topic": "Health"},
        ],
    }
    assert proposals.reminder_cards_as_text(_fence(card)) == (
        "Done: Rent.\nDeleted: Gym.\nMoved: Walk — to Health."
    )


@pytest.mark.asyncio
async def test_a_card_the_model_wrote_itself_is_dropped(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    fake = _fence({"proposal_id": "made-up", "items": [{"action": "add", "title": "Gym"}]})
    text = await _turn(db_session, fake_redis, user, chat, "thanks!", f"You're welcome.\n\n{fake}")
    assert "made-up" not in text
    assert text.startswith("You're welcome.")


# 21:13 in Nairobi: today's 7pm has passed.
_EVENING = datetime(2026, 10, 18, 18, 13, tzinfo=UTC)
_PAST_FENCE = '```reminder\n{"title":"Plate the dinner","due_at":"2026-10-18T19:00:00+03:00"}\n```'


async def _nairobi_turn(session: Any, redis: Any, user_text: str, reply: str) -> str:
    user, chat = await _user_and_chat(session)
    with patch("app.modules.todos.spoken_add._now", lambda tz: _EVENING.astimezone(tz)):
        text, written = await materialize_reminder_fences(
            session,
            user_id=user.id,
            chat_id=chat.id,
            assistant_text=reply,
            user_timezone="Africa/Nairobi",
            user_text=user_text,
            redis=redis,
            confirm=True,
        )
    assert written == 0
    return text


@pytest.mark.asyncio
async def test_a_bare_clock_already_past_is_offered_for_tomorrow(db_session, fake_redis):
    """ "Remind me to plate the dinner at 7pm" at 9pm: the model's fence said today
    at 7pm, nothing was saved, and the reply kept the raw fence."""
    text = await _nairobi_turn(
        db_session, fake_redis, "remind me to plate the dinner at 7pm", _PAST_FENCE
    )
    assert TODO_HINT not in text
    item = _card(text)["items"][0]
    assert item["title"] == "Plate the dinner"
    assert item["due_at"] == "2026-10-19T16:00:00Z"


@pytest.mark.asyncio
async def test_a_past_fence_with_no_clock_still_says_something(db_session, fake_redis):
    text = await _nairobi_turn(db_session, fake_redis, "remind me to plate the dinner", _PAST_FENCE)
    assert "```reminder" not in text
    assert text.strip()


# 09:00 in Nairobi on a Wednesday: 5pm today and Friday 9am are both ahead.
async def _morning_turn(
    session: Any, redis: Any, user: Any, chat: Any, user_text: str, reply: str
) -> str:
    await messages_repo.create(
        session, chat_id=chat.id, user_id=user.id, role="user", content=user_text
    )
    return await _materialize(
        session,
        redis,
        user,
        chat,
        user_text,
        reply,
        user_timezone="Africa/Nairobi",
        clock=_MORNING,
    )


@pytest.mark.asyncio
async def test_a_question_and_a_reminder_keep_the_answer_and_the_card(db_session, fake_redis):
    """I4: the answer was dropped and the card was titled "also buy milk"."""
    user, chat = await _user_and_chat(db_session)
    text = await _morning_turn(
        db_session,
        fake_redis,
        user,
        chat,
        "what is the boiling point of water? also remind me to buy milk tomorrow at 9am",
        "Water boils at **100 °C** (212 °F) at sea level.\n\nI'll remind you tomorrow at 9 am.",
    )

    assert text.startswith("Water boils at **100 °C** (212 °F) at sea level.")
    assert "I'll remind you" not in text
    [item] = _card(text)["items"]
    assert (item["title"], item["due_at"]) == ("buy milk", "2026-10-15T06:00:00Z")


@pytest.mark.asyncio
async def test_two_reminders_in_one_message_are_two_items_with_their_own_times(
    db_session, fake_redis
):
    """I4: one card, "call mom and to pay rent at 9am", on Friday at 5 PM."""
    user, chat = await _user_and_chat(db_session)
    text = await _morning_turn(
        db_session,
        fake_redis,
        user,
        chat,
        "remind me to call mom at 5pm and to pay rent on friday at 9am",
        "Sure! I'll remind you to call mom at 5 PM and to pay rent on Friday at 9 AM.",
    )

    items = _card(text)["items"]
    assert [(item["title"], item["due_at"]) for item in items] == [
        ("call mom", "2026-10-14T14:00:00Z"),
        ("pay rent", "2026-10-16T06:00:00Z"),
    ]
    assert text.startswith("```reminder_proposal")


@pytest.mark.asyncio
async def test_a_second_reminder_with_no_clock_is_asked_for_then_finished(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    first = await _morning_turn(
        db_session,
        fake_redis,
        user,
        chat,
        "remind me to call mom at 5pm and to pay rent on friday",
        "Okay.",
    )
    assert [item["title"] for item in _card(first)["items"]] == ["call mom"]
    assert first.startswith("When should I remind you to pay rent?")

    second = await _morning_turn(db_session, fake_redis, user, chat, "9am", "Got it.")
    [item] = _card(second)["items"]
    assert (item["title"], item["due_at"]) == ("pay rent", "2026-10-16T06:00:00Z")


@pytest.mark.asyncio
async def test_the_card_names_the_zone_its_time_was_read_in(db_session, fake_redis):
    """F8.4: the phone shows the card's time in this zone, and names it when the phone
    is somewhere else, so the card and the reply say the same 9:00 AM."""
    user, chat = await _user_and_chat(db_session)
    text = await _morning_turn(
        db_session, fake_redis, user, chat, "remind me to buy milk tomorrow at 9am", "Okay."
    )
    card = _card(text)
    assert card["tz"] == "Africa/Nairobi"
    assert card["items"][0]["due_at"] == "2026-10-15T06:00:00Z"
    assert card["items"][0]["when"] == "Thursday, Oct 15, 9:00 AM"


@pytest.mark.asyncio
async def test_tapping_done_on_a_repeating_reminder_keeps_the_series(db_session, fake_redis):
    user, chat = await _user_and_chat(db_session)
    due = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    saved = await todos_repo.create(
        db_session,
        user_id=user.id,
        content="Gym",
        topic="Reminders",
        due_at=due,
        recurrence_rule="weekly",
    )
    text = await _turn(db_session, fake_redis, user, chat, "mark gym as done", "Ok.")
    card = _card(text)
    assert card["items"] == [{"action": "complete", "title": "Gym"}]

    await proposals.confirm_proposal(
        db_session, fake_redis, user_id=user.id, proposal_id=card["proposal_id"]
    )
    [row] = await _rows(db_session, user.id)
    # Done for this week: still open, due next week, still weekly.
    assert row.id == saved.id and row.checked is False
    assert row.due_at == due + timedelta(days=7) and row.recurrence_rule == "weekly"
