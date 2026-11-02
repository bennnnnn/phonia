"""A standing teaching preference gets an acknowledgement and the plan, never a photo.

"When teaching me, explain one concept at a time…" used to get "I can't see the
image you're referring to": nothing in the prompt said it was a preference, and the
photo hint was the only instruction that seemed to fit.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.chat.prompt_constants import (
    ANSWER_PHOTO_HINT,
    EXAMPLE_PERSONALIZE_HINT,
    PERSONAL_DISCLOSURE_HINT,
    STANDING_PREFERENCE_HINT,
    TEACHING_HINT,
)
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.conversation import chats_repository, messages_repository
from app.modules.turn_reading.teaching import is_standing_preference, is_teaching_request
from app.tests.modules.chat.chat_test_support import system_prompt

TEACHING_PREFERENCE = (
    "When teaching me, explain one concept at a time, use practical examples, and ask me to "
    "solve a short exercise before moving on."
)


def _hints(text: str) -> list[str]:
    return _style_format_hints(
        query_text=text,
        is_day_plan=False,
        minimal_personal_context=False,
        image_search_enabled=True,
    )


@pytest.mark.parametrize(
    "text",
    [
        TEACHING_PREFERENCE,
        "From now on, always give me a practical example before the theory.",
        "From now on, explain things simply.",
        "From now on I want you to quiz me after every lesson.",
        "Going forward, your answers should be shorter.",
        "Use simple words from now on.",
        "be more concise from now on",
        "Always explain your reasoning step by step.",
        "Can you always include a code example?",
        "I learn best when you quiz me after each step.",
        "I learn best by doing.",
        "I'm a visual learner.",
        "I prefer short answers.",
        "I want you to explain one concept at a time.",
        "Please teach me by asking questions instead of lecturing.",
        "Teach me one concept at a time.",
        "When you explain things to me, use analogies.",
        "When you teach me something new, start with a real example.",
        "When I ask for code, always add comments.",
        "Don't give me the answer, give me hints.",
        "Only give me hints.",
        "I'm a beginner. When teaching me, go slowly.",
    ],
)
def test_is_standing_preference_reads_how_to_teach(text: str) -> None:
    assert is_standing_preference(text)


@pytest.mark.parametrize(
    "text",
    [
        "When teaching me yesterday you used a great example, can you show it again?",
        "When teaching me yesterday you said lists start at 0",
        "from now on I'll wake at 6",
        "From now on I will study every day.",
        "always remind me to drink water",
        "Remind me to study every day from now on",
        "for future chats keep in mind that i'm vegetarian",
        "Please remember that I learn best with examples",
        "teach me python",
        "teach me python by building projects",
        "Teach me by examples about cooking",
        "When teaching me, go slowly. Teach me Python.",
        "From now on, explain things simply. What is photosynthesis?",
        "Don't give me the answer to 2x + 3 = 7, just a hint",
        "From now on call me Bini",
        "I want examples of renewable energy",
        "I prefer tea over coffee",
        "When is the best time to study?",
        "explain the code of conduct",
        "what is a capybara",
    ],
)
def test_is_standing_preference_skips_lookalikes(text: str) -> None:
    assert not is_standing_preference(text)


def test_a_teach_by_preference_is_not_a_lesson_request() -> None:
    assert not is_teaching_request("Please teach me by asking questions instead of lecturing.")
    assert is_teaching_request("teach me python")
    assert is_teaching_request("teach me python by building projects")


def test_teaching_preference_gets_an_acknowledgement_not_a_photo() -> None:
    parts = _hints(TEACHING_PREFERENCE)
    assert STANDING_PREFERENCE_HINT in parts
    for absent in (ANSWER_PHOTO_HINT, TEACHING_HINT, PERSONAL_DISCLOSURE_HINT):
        assert absent not in parts


def test_learner_statement_is_a_preference_not_a_disclosure() -> None:
    parts = _hints("I learn best when you quiz me after each step.")
    assert STANDING_PREFERENCE_HINT in parts
    assert PERSONAL_DISCLOSURE_HINT not in parts


def test_preference_hint_restates_the_plan_and_asks_what_to_learn() -> None:
    assert "one concept at a time" in STANDING_PREFERENCE_HINT
    assert "what they want to learn first" in STANDING_PREFERENCE_HINT
    assert "photos, images" in STANDING_PREFERENCE_HINT


def _user() -> User:
    user = MagicMock()
    user.id = uuid4()
    user.name = "Bini"
    user.email = "bini@example.com"
    user.location = None
    user.response_tone = None
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = None
    user.custom_instructions = None
    return cast(User, user)


async def _system_prompt(query: str, *, memory: str = "", advice_memory: bool = False) -> str:
    current = SimpleNamespace(id=uuid4(), role="user", content=query)
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value=memory)),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[current])),
    ):
        messages = await build_prompt_messages(
            _user(),
            uuid4(),
            Settings(attachment_rag_enabled=False, chat_history_rag_enabled=False),
            query_text=query,
            rich_context=False,
            advice_memory=advice_memory,
            current_user_message_id=current.id,
        )
    return system_prompt(messages)


@pytest.mark.asyncio
async def test_preference_turn_gets_no_disclosure_or_photo_hint() -> None:
    system = await _system_prompt("I learn best when you quiz me after each step.")
    assert STANDING_PREFERENCE_HINT in system
    assert PERSONAL_DISCLOSURE_HINT not in system
    assert ANSWER_PHOTO_HINT not in system


@pytest.mark.asyncio
async def test_a_later_lesson_reads_the_stored_teaching_preference() -> None:
    # "teach me python" loads memory (turn mode sets advice_memory for a lesson), so
    # the preference saved from an earlier chat shapes the lesson.
    stored = (
        "Known facts about the user:\n\n## Preferences\n- User wants lessons one concept "
        "at a time, with a short exercise before moving on."
    )
    system = await _system_prompt("teach me python", memory=stored, advice_memory=True)
    assert "one concept at a time, with a short exercise" in system
    assert EXAMPLE_PERSONALIZE_HINT in system
    assert "how they like to be taught" in EXAMPLE_PERSONALIZE_HINT
    assert TEACHING_HINT in system
