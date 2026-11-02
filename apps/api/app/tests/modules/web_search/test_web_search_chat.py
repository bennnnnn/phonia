from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.prompt_builder import build_prompt_messages
from app.modules.conversation import chats_repository, messages_repository
from app.modules.web_search.formatting import WEB_SEARCH_HINT
from app.tests.modules.chat.chat_test_support import system_prompt


@pytest.mark.asyncio
async def test_build_prompt_includes_web_search_hint():
    user = MagicMock()
    user.memory_enabled = True
    user.locale = "en"
    user.timezone = "UTC"
    user.location = None
    user.response_tone = "funny"

    with (
        patch(
            "app.modules.memory.retrieval.get_memory_block",
            AsyncMock(return_value=""),
        ),
        patch.object(messages_repository, "list_recent", return_value=[]),
        patch(
            "app.modules.todos.build_todos_system_section",
            AsyncMock(return_value=None),
        ),
        patch.object(
            chats_repository,
            "get_by_id",
            AsyncMock(return_value=None),
        ),
    ):
        messages = await build_prompt_messages(user, uuid4(), Settings())

    assert WEB_SEARCH_HINT in system_prompt(messages)
