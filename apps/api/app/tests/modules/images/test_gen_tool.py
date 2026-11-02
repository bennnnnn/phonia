"""Tests for the model-callable generate_image MCP adapter."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.images.gen_tool import ImageGenAdapter
from app.modules.images.generation import ImageGenerationError
from app.tests.tool_context import tool_context


def _settings(**kwargs: object) -> Settings:
    s = Settings()
    for key, value in kwargs.items():
        setattr(s, key, value)
    return s


@pytest.mark.asyncio
@pytest.mark.parametrize("has_user, has_chat", [(False, False), (False, True), (True, False)])
async def test_invoke_without_user_or_chat_is_unavailable(has_user, has_chat):
    adapter = ImageGenAdapter(_settings(image_generation_enabled=True))
    ctx = tool_context(
        user=MagicMock() if has_user else None, chat_id=uuid4() if has_chat else None
    )
    result = await adapter.invoke({"prompt": "a cat"}, ctx)
    assert "unavailable" in result.content.lower()


@pytest.mark.asyncio
async def test_invoke_rejects_non_pro():
    adapter = ImageGenAdapter(_settings(image_generation_enabled=True))
    ctx = tool_context(user=MagicMock(), redis=MagicMock(), chat_id=uuid4())
    with patch(
        "app.modules.images.gen_tool.can_use",
        return_value=False,
    ):
        result = await adapter.invoke({"prompt": "a cat"}, ctx)
    assert "not part of this user's plan" in result.content


@pytest.mark.asyncio
async def test_invoke_persists_and_returns_terminal_marker():
    adapter = ImageGenAdapter(_settings(image_generation_enabled=True))
    user = MagicMock()
    chat_id = uuid4()
    asst_id = uuid4()
    marker = f"[Image: /attachments/{uuid4()}/file]"
    asst = MagicMock(id=asst_id, content=marker, model="image-gen-model")
    generate = AsyncMock(return_value=(MagicMock(), asst))
    ctx = tool_context(user=user, redis=MagicMock(), chat_id=chat_id)

    with (
        patch(
            "app.modules.images.gen_tool.can_use",
            return_value=True,
        ),
        patch(
            "app.modules.images.gen_tool.image_generation_service.generate_for_chat",
            generate,
        ),
    ):
        result = await adapter.invoke({"prompt": "watercolor fox", "aspect_ratio": "1:1"}, ctx)

    generate.assert_awaited_once()
    kwargs = generate.await_args.kwargs
    # The turn's user and chat come from the context.
    assert kwargs["user"] is user
    assert kwargs["chat_id"] == chat_id
    assert kwargs["create_user_message"] is False
    assert kwargs["prompt"] == "watercolor fox"
    assert kwargs["aspect_ratio"] == "1:1"
    assert result.data is not None
    assert result.data["terminal"] is True
    assert result.data["image_marker"] == marker
    assert result.data["assistant_message_id"] == str(asst_id)


@pytest.mark.asyncio
async def test_invoke_surfaces_generation_error():
    adapter = ImageGenAdapter(_settings(image_generation_enabled=True))
    ctx = tool_context(user=MagicMock(), redis=MagicMock(), chat_id=uuid4())
    with (
        patch(
            "app.modules.images.gen_tool.can_use",
            return_value=True,
        ),
        patch(
            "app.modules.images.gen_tool.image_generation_service.generate_for_chat",
            AsyncMock(side_effect=ImageGenerationError("quota", status_code=429)),
        ),
    ):
        result = await adapter.invoke({"prompt": "a cat"}, ctx)
    assert "failed" in result.content.lower()
