""" "Web search off" in Settings: the reply says it cannot check, never offers to."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.chat.prompt_constants import WEB_SEARCH_OFF_HINT
from app.modules.conversation import chats_repository, messages_repository
from app.tests.modules.chat.chat_test_support import system_prompt


def _user(search_on: bool = True) -> User:
    user = MagicMock()
    user.web_search_enabled = search_on
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


async def _system_prompt(query: str, settings: Settings, search_on: bool = True) -> str:
    current = SimpleNamespace(id=uuid4(), role="user", content=query)
    with (
        patch.object(chats_repository, "get_by_id", AsyncMock(return_value=None)),
        patch("app.modules.memory.retrieval.get_memory_block", AsyncMock(return_value="")),
        patch("app.modules.todos.build_todos_system_section", AsyncMock(return_value="")),
        patch.object(messages_repository, "list_recent", AsyncMock(return_value=[current])),
    ):
        messages = await build_prompt_messages(
            _user(search_on),
            uuid4(),
            settings,
            query_text=query,
            rich_context=False,
            current_user_message_id=current.id,
        )
    return system_prompt(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_on, server_on, told",
    [
        (True, True, False),
        (False, True, True),
        # A server without search is not the user's choice: no "turn it on in Settings".
        (True, False, False),
    ],
)
async def test_only_a_user_who_turned_search_off_is_told_so(user_on, server_on, told):
    settings = Settings(
        attachment_rag_enabled=False, chat_history_rag_enabled=False, web_search_enabled=server_on
    )
    system = await _system_prompt("who is the president of Kenya", settings, user_on)
    assert (WEB_SEARCH_OFF_HINT in system) is told


def test_search_off_hint_points_to_the_setting_and_never_offers_a_search():
    assert "Settings, Data controls" in WEB_SEARCH_OFF_HINT
    assert "Never offer to search" in WEB_SEARCH_OFF_HINT  # safety phrase
