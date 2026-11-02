"""The resolver that spells out what "do a search" or "show me her image" refers to."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import Settings
from app.models.schemas import ConversationReference
from app.services import conversation_reference as ref


def _awaited(mock: AsyncMock) -> Any:
    """The last await of *mock*; fails the test when it was never awaited."""
    assert mock.await_args is not None
    return mock.await_args


_CALMENT = [
    ("user", "Has anyone ever lived for 123 years?"),
    ("assistant", "No. The longest documented lifespan is Jeanne Calment, 122 years 164 days."),
    ("user", "Where is she from"),
    ("assistant", "She was French, born in Arles, France."),
    ("user", "Show me her image"),
]


def _settings(**overrides) -> Settings:
    return Settings(mock_llm_enabled=False, **overrides)


@pytest.fixture
def no_spend_cap():
    with (
        patch.object(ref.quota_service, "global_spend_exceeded", AsyncMock(return_value=False)),
        patch.object(ref.quota_service, "record_global_spend", AsyncMock()) as record,
        patch.object(ref, "get_redis_client", return_value=object()),
    ):
        yield record


@pytest.mark.asyncio
async def test_resolver_sends_the_conversation_without_the_request(no_spend_cap) -> None:
    complete = AsyncMock(return_value=ConversationReference(text="Jeanne Calment"))
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="photo", request="Show me her image", turns=_CALMENT
        )

    assert out == "Jeanne Calment"
    kwargs = _awaited(complete).kwargs
    assert kwargs["model_alias"] == "memory-model"
    assert kwargs["schema"] is ConversationReference
    prompt = kwargs["messages"][1]["content"]
    assert "Assistant: No. The longest documented lifespan is Jeanne Calment" in prompt
    assert prompt.count("Show me her image") == 1
    assert prompt.rstrip().endswith("Latest message: Show me her image")
    # The gateway meters the call from its token usage (gateways/llm_spend).
    no_spend_cap.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_resolver_leaves_drawn_things_to_the_app(no_spend_cap) -> None:
    """ "can u show me both" after water and CO2 wants the molecules drawn, not photos."""
    complete = AsyncMock(return_value=ConversationReference(text=None))
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        await ref.resolve_reference(
            _settings(), kind="photo", request="can u show me both", turns=_CALMENT
        )

    instructions = _awaited(complete).kwargs["messages"][0]["content"]
    assert "molecule" in instructions
    assert '{"text": null}' in instructions


@pytest.mark.asyncio
async def test_resolver_renders_an_image_turn_as_text(no_spend_cap) -> None:
    complete = AsyncMock(return_value=ConversationReference(text="red car at night"))
    turns = [
        ("user", "Show me a red car"),
        ("assistant", "[Image: /attachments/abc/file]"),
    ]
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        await ref.resolve_reference(
            _settings(), kind="photo", request="show it at night", turns=turns
        )

    prompt = _awaited(complete).kwargs["messages"][1]["content"]
    assert "Assistant: (showed an image)" in prompt
    assert "/attachments/" not in prompt


@pytest.mark.parametrize("answer", [None, "null", "  ", "unknown"])
@pytest.mark.asyncio
async def test_resolver_returns_none_when_the_chat_does_not_say(no_spend_cap, answer) -> None:
    complete = AsyncMock(return_value=ConversationReference(text=answer))
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="search", request="do a search", turns=_CALMENT
        )
    assert out is None


@pytest.mark.asyncio
async def test_resolver_strips_quotes_from_the_answer(no_spend_cap) -> None:
    complete = AsyncMock(return_value=ConversationReference(text='"Bini name meaning".'))
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="search", request="do a search", turns=_CALMENT
        )
    assert out == "Bini name meaning"


@pytest.mark.asyncio
async def test_resolver_failure_is_best_effort(no_spend_cap) -> None:
    complete = AsyncMock(side_effect=RuntimeError("provider down"))
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="search", request="do a search", turns=_CALMENT
        )
    assert out is None
    no_spend_cap.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_skips_the_call_when_spend_is_capped() -> None:
    complete = AsyncMock()
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=False),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
        patch.object(ref.quota_service, "global_spend_exceeded", AsyncMock(return_value=True)),
        patch.object(ref, "get_redis_client", return_value=object()),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="photo", request="Show me her image", turns=_CALMENT
        )
    assert out is None
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_needs_a_conversation() -> None:
    complete = AsyncMock()
    with patch.object(ref.litellm_gateway, "complete_structured", complete):
        out = await ref.resolve_reference(
            _settings(), kind="search", request="do a search", turns=[("user", "do a search")]
        )
    assert out is None
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_is_off_with_the_mock_llm() -> None:
    complete = AsyncMock()
    with (
        patch.object(ref.mock_llm, "should_mock_llm", return_value=True),
        patch.object(ref.litellm_gateway, "complete_structured", complete),
    ):
        out = await ref.resolve_reference(
            _settings(), kind="photo", request="Show me her image", turns=_CALMENT
        )
    assert out is None
    complete.assert_not_awaited()


def test_turns_from_prompt_drops_system_blocks() -> None:
    messages = [
        {"role": "system", "content": "You are Recall."},
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "[BEGIN UNTRUSTED CONTENT — web search]"},
        {"role": "assistant", "content": "hello"},
    ]
    assert ref.turns_from_prompt(messages) == [("user", "hi"), ("assistant", "hello")]


def test_turns_from_rows_reads_message_rows() -> None:
    rows = [
        SimpleNamespace(role="user", content="Show me a car"),
        SimpleNamespace(role="assistant", content="[Image: /attachments/a/file]"),
        SimpleNamespace(role="system", content="summary"),
    ]
    assert ref.turns_from_rows(rows) == [
        ("user", "Show me a car"),
        ("assistant", "[Image: /attachments/a/file]"),
    ]
