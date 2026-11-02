"""One-off reminders, impossible fact pairs, and direct profile answers."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.chat.turn_prep.instant import _profile_reply
from app.modules.memory.fact_quality import FactView, is_one_off_schedule_fact, texts_to_drop
from app.modules.memory.pass_writes import writes_from_ops
from app.modules.memory.profile_reply import reply_for_profile_question
from app.modules.memory.schemas import MemoryFactOp
from app.modules.turn_reading.profile_ask import profile_question_to_answer

_NOW = datetime(2026, 10, 11, tzinfo=UTC)


def test_one_off_reminders_are_not_memory_and_routines_are():
    assert is_one_off_schedule_fact("User has a dentist appointment on Thursday at 4")
    assert is_one_off_schedule_fact("User has a weekly todo of walking at 7pm")
    assert is_one_off_schedule_fact("User has a reading task for tomorrow")
    assert is_one_off_schedule_fact("User's mom's flight lands on Thursday at 4 in the evening")
    assert not is_one_off_schedule_fact("User walks every evening at 7pm")
    assert not is_one_off_schedule_fact("User works on Monday")


def test_two_current_places_keep_the_newer_one():
    drops = texts_to_drop(
        [
            FactView("User is in Avon", _NOW - timedelta(days=2)),
            FactView("User is in Russia", _NOW),
            FactView("User is from Addis Ababa, Ethiopia", _NOW),
            FactView("User's first language is Amharic", _NOW),
            FactView("User's second language is English", _NOW),
        ]
    )
    assert drops == ["User is in Avon"]


def test_current_school_and_an_earlier_stage_keep_the_newer_one():
    drops = texts_to_drop(
        [
            FactView("User attended Debre Markos University", _NOW - timedelta(days=1)),
            FactView("User is in 12th grade", _NOW),
        ]
    )
    assert drops == ["User attended Debre Markos University"]


_FACTS = (
    "User's second language is English",
    "User's first language is Amharic",
    "User is from Addis Ababa, Ethiopia",
)


def test_second_language_is_read_from_the_profile():
    assert (
        reply_for_profile_question("My second langauge", _FACTS)
        == "Your second language is English."
    )
    assert reply_for_profile_question("What is my education level", _FACTS) == (
        "I don't have your education level saved."
    )


@pytest.mark.parametrize(
    ("facts", "location", "reply"),
    [
        # M15: a saved home is said, never "I don't have that saved".
        (("User lives in Addis Ababa",), None, "You live in Addis Ababa."),
        (("Bini is based in Nairobi, Kenya",), None, "You live in Nairobi, Kenya."),
        # Someone else's home is not the user's.
        (("User's sister lives in Nairobi suburbs",), None, "I don't have where you live saved."),
        (
            (),
            "Bole, Addis Ababa",
            "I don't have where you live saved, but your location is set to Bole, Addis Ababa.",
        ),
        ((), None, "I don't have where you live saved."),
    ],
)
def test_where_do_i_live_reads_the_saved_home(facts, location, reply):
    assert profile_question_to_answer("where do I live?", []) == "where do I live?"
    assert reply_for_profile_question("where do I live?", facts, location=location) == reply


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_on", [True, False])
async def test_instant_profile_reply_follows_the_memory_switch(memory_on):
    """M14: with memory off, "where am I from?" is not answered from saved facts."""
    user = SimpleNamespace(id=uuid4(), memory_enabled=memory_on, location_enabled=False)
    identity = SimpleNamespace(user=user)
    rows = AsyncMock(return_value=[SimpleNamespace(text="User is from Ethiopia")])
    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", _Session),
        patch("app.modules.memory.repository.list_for_user", rows),
    ):
        reply = await _profile_reply("where am I from?", identity)
    assert reply == ("You're from Ethiopia." if memory_on else None)


@pytest.mark.asyncio
async def test_instant_profile_reply_does_not_deny_on_a_failed_read():
    """M17: a failed read hands the turn to the model, which says memory didn't load."""
    identity = SimpleNamespace(user=SimpleNamespace(id=uuid4(), memory_enabled=True))
    with (
        patch("app.modules.chat.turn_prep.instant.SessionLocal", _Session),
        patch(
            "app.modules.memory.repository.list_for_user",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        assert await _profile_reply("where do I live?", identity) is None


class _Session:
    async def __aenter__(self):
        return AsyncMock()

    async def __aexit__(self, *_args):
        return None


def test_second_after_first_language_reads_the_other_fact():
    asked = profile_question_to_answer("Second", ["What is my first language"])
    assert asked == "what is my second language"
    assert reply_for_profile_question(asked or "", _FACTS) == "Your second language is English."


def test_you_tell_me_uses_the_earlier_language_question():
    asked = profile_question_to_answer(
        "You tell me",
        ["What is my education level", "My second langauge", "U don't know. It?"],
    )
    assert asked == "My second langauge"
    assert reply_for_profile_question(asked or "", _FACTS) == "Your second language is English."


def test_writes_skip_a_one_off_reminder():
    reminder = MemoryFactOp(
        op="add",
        type="fact",
        text="User has a dentist appointment on Thursday at 4",
        confidence=0.9,
        importance=0.5,
        topic="schedule",
    )
    home = MemoryFactOp(
        op="add",
        type="profile",
        text="User is from Addis Ababa, Ethiopia",
        confidence=0.9,
        importance=0.8,
        topic="profile",
    )
    writes, skipped = writes_from_ops(
        [reminder, home],
        chat_id=uuid4(),
        explicit_remember=False,
        include_sensitive=False,
        min_confidence=0.5,
        transcript="User: remind me about the dentist. I am from Addis Ababa.",
    )
    assert skipped == 1
    assert [write.text for write in writes] == ["User is from Addis Ababa, Ethiopia"]
