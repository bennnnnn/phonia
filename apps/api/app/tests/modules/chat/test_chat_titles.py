"""Tests for chat title normalization."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.models.schemas import ChatOut
from app.modules.chat.titles import (
    GREETING_CHAT_TITLE,
    finalize_generated_title,
    generate_title,
    is_casual_opener,
    normalize_chat_title,
    sanitize_manual_chat_title,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("New chat", None),
        ("  new chat  ", None),
        ("Untitled", None),
        ("Chat", None),
        ("Valid topic name", "Valid topic name"),
        ('"Quoted title"', "Quoted title"),
        ('"My Trip Plan".', "My Trip Plan"),
        ('"My Trip Plan"!', "My Trip Plan"),
        ("\u201cMy Trip Plan\u201d.", "My Trip Plan"),
        # Markdown emphasis the title model sometimes emits.
        ("**Document Summaries**", "Document Summaries"),
        ("**D**ocument** Summaries", "Document Summaries"),
        ("__Trip Plan__", "Trip Plan"),
        ("*Trip Plan*", "Trip Plan"),
        ("_Trip Plan_", "Trip Plan"),
        ('"**My Trip Plan**"', "My Trip Plan"),
        ("A *great* trip", "A great trip"),
        # Not emphasis: math and identifiers keep their characters.
        ("Solve x*2 = 10", "Solve x*2 = 10"),
        ("my_snake_case notes", "my_snake_case notes"),
        ("ab", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_chat_title(raw: str | None, expected: str | None):
    assert normalize_chat_title(raw) == expected


def test_needs_generated_title():
    from app.modules.chat.titles import needs_generated_title

    assert needs_generated_title(None) is True
    assert needs_generated_title("") is True
    assert needs_generated_title("Untitled") is True
    assert needs_generated_title("Homework") is False


def test_chat_out_preserves_user_chosen_generic_title():
    from datetime import UTC, datetime
    from uuid import uuid4

    out = ChatOut(
        id=uuid4(),
        title="New chat",
        model="auto",
        pinned=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert out.title == "New chat"


def test_chat_out_strips_markdown_emphasis_from_stored_title():
    """Already-persisted `**...**` titles render clean — no migration needed."""
    from datetime import UTC, datetime
    from uuid import uuid4

    out = ChatOut(
        id=uuid4(),
        title="**D**ocument** Summaries",
        model="auto",
        pinned=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert out.title == "Document Summaries"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ('  "Pinned note"  ', "Pinned note"),
        ('"My Trip Plan".', "My Trip Plan"),
        ("New chat", "New chat"),
        ("ab", "ab"),
        ("", None),
        ("x" * 81, None),
    ],
)
def test_sanitize_manual_chat_title(raw: str, expected: str | None):
    assert sanitize_manual_chat_title(raw) == expected


def test_search_result_sanitizes_chat_title():
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.models.schemas import SearchResultItem

    item = SearchResultItem(
        chat_id=uuid4(),
        chat_title='"My Trip Plan".',
        content="hi",
        role="user",
        created_at=datetime.now(UTC),
    )
    assert item.chat_title == "My Trip Plan"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("hi", True),
        ("Hi!", True),
        ("good morning", True),
        ("Good morning.", True),
        ("hello there", True),
        ("good morning, help me with physics", False),
        ("What's still open for me to finish tonight?", False),
        ("", False),
    ],
)
def test_is_casual_opener(raw: str, expected: bool):
    assert is_casual_opener(raw) is expected


@pytest.mark.parametrize(
    "raw, user, expected",
    [
        ("Anything", "hi", GREETING_CHAT_TITLE),
        ("Anything", "good morning", GREETING_CHAT_TITLE),
        ("Tonight leftovers", "What's still open?", "Tonight leftovers"),
        ("New chat", "What's still open?", None),
    ],
)
def test_finalize_generated_title(raw: str, user: str, expected: str | None):
    assert finalize_generated_title(raw, user) == expected


@pytest.mark.asyncio
async def test_generate_title_greeting_skips_model():
    settings = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")
    with patch(
        "app.modules.chat.titles.litellm_gateway.complete_text",
        new_callable=AsyncMock,
    ) as complete:
        title = await generate_title(settings, "good morning", "Hello!")
    assert title == GREETING_CHAT_TITLE
    complete.assert_not_called()
