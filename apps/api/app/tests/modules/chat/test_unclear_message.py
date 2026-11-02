""" "Bo" is not "hi": an unclear message gets noticed, not greeted past.

"Bo" got "Hey Bini! How's it going?". ChatGPT answered "Bo! Did you mean 'bo' in
Amharic, or are you starting to type something?" Every turn carries the rule; the
model, which sees the conversation, judges what is unclear.
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
from app.modules.chat.prompt_constants.unclear import UNCLEAR_MESSAGE_HINT
from app.modules.conversation import chats_repository, messages_repository
from app.tests.modules.chat.chat_test_support import system_prompt


def test_unclear_message_hint_guesses_instead_of_greeting() -> None:
    assert "do not guess silently or treat it as a greeting" in UNCLEAR_MESSAGE_HINT
    assert "a language they may speak" in UNCLEAR_MESSAGE_HINT
    assert "still typing" in UNCLEAR_MESSAGE_HINT
    # "Lk" got a greeting, a bold bullet list of guesses and a sign-off.
    assert "no greeting, no name, no list, no bold, no sign-off" in UNCLEAR_MESSAGE_HINT
    # "gd" after "How's it going?" is "good": context wins, no question back.
    assert "take that reading and reply; do not ask" in UNCLEAR_MESSAGE_HINT


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


async def _system_prompt(query: str) -> str:
    current = SimpleNamespace(id=uuid4(), role="user", content=query)
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value="")),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[current])),
    ):
        messages = await build_prompt_messages(
            _user(),
            uuid4(),
            Settings(attachment_rag_enabled=False, chat_history_rag_enabled=False),
            query_text=query,
            rich_context=False,
            current_user_message_id=current.id,
        )
    return system_prompt(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["Bo", "gd", "hi", "photosynthesis", "solve 2x=4"])
async def test_every_turn_lets_the_model_judge_an_unclear_message(query: str) -> None:
    # No word list or length gate: the model sees the conversation and decides.
    assert UNCLEAR_MESSAGE_HINT in await _system_prompt(query)
