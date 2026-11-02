"""Tests for the model-callable search_image MCP adapter."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.gateways.mcp.base import ToolContext
from app.modules.images import search_tool as adapter_module
from app.modules.images.search import ImageSearchError
from app.modules.images.search_tool import ImageSearchAdapter
from app.tests.tool_context import tool_context


def _settings(**kwargs: object) -> Settings:
    s = Settings()
    for key, value in kwargs.items():
        setattr(s, key, value)
    return s


def _turn(*, user: object = None, chat_id: UUID | None = None) -> ToolContext:
    """A turn with a user and a chat, the way the tool loop builds one."""
    return tool_context(user=user or MagicMock(), redis=MagicMock(), chat_id=chat_id or uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize("has_user, has_chat", [(False, False), (False, True), (True, False)])
async def test_invoke_without_user_or_chat_is_unavailable(has_user, has_chat):
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    ctx = tool_context(
        user=MagicMock() if has_user else None, chat_id=uuid4() if has_chat else None
    )
    result = await adapter.invoke({"query": "an ear"}, ctx)
    assert "unavailable" in result.content.lower()


@pytest.mark.asyncio
async def test_invoke_missing_query():
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    result = await adapter.invoke({"query": "   "}, _turn())
    assert "missing query" in result.content.lower()


@pytest.mark.asyncio
async def test_invoke_disabled():
    adapter = ImageSearchAdapter(_settings(image_search_enabled=False))
    result = await adapter.invoke({"query": "an ear"}, _turn())
    assert "disabled" in result.content.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["water and carbon dioxide molecules", "graph of y = x^2"])
async def test_invoke_declines_what_the_app_draws(query: str):
    """A molecule or a graph is drawn by Recall; a stock photo of one is no answer."""
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    search = AsyncMock()
    with patch.object(adapter_module.image_search_service, "search_and_attach_for_chat", search):
        result = await adapter.invoke({"query": query}, _turn())

    search.assert_not_awaited()
    assert result.data is None
    assert "draws" in result.content


@pytest.mark.asyncio
async def test_invoke_persists_and_returns_terminal_marker():
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    user = MagicMock()
    chat_id = uuid4()
    asst_id = uuid4()
    marker = f"[Image: /attachments/{uuid4()}/file]"
    asst = MagicMock(id=asst_id, content=marker, model="image-search-model")
    search = AsyncMock(return_value=(MagicMock(), asst))

    with patch(
        "app.modules.images.search_tool.image_search_service.search_and_attach_for_chat",
        search,
    ):
        result = await adapter.invoke({"query": "an ear"}, _turn(user=user, chat_id=chat_id))

    search.assert_awaited_once()
    kwargs = search.await_args.kwargs
    # The turn's user and chat come from the context.
    assert kwargs["user"] is user
    assert kwargs["chat_id"] == chat_id
    assert kwargs["create_user_message"] is False
    assert kwargs["query"] == "an ear"
    assert result.data is not None
    assert result.data["terminal"] is True
    assert result.data["image_marker"] == marker
    assert result.data["assistant_message_id"] == str(asst_id)


@pytest.mark.asyncio
async def test_invoke_surfaces_search_error():
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    with patch(
        "app.modules.images.search_tool.image_search_service.search_and_attach_for_chat",
        AsyncMock(side_effect=ImageSearchError("no photo found", status_code=502)),
    ):
        result = await adapter.invoke({"query": "an ear"}, _turn())
    assert "failed" in result.content.lower()


@pytest.mark.asyncio
async def test_invoke_rejects_marker_without_image_prefix():
    adapter = ImageSearchAdapter(_settings(image_search_enabled=True))
    asst = MagicMock(id=uuid4(), content="oops not a marker")
    with patch(
        "app.modules.images.search_tool.image_search_service.search_and_attach_for_chat",
        AsyncMock(return_value=(MagicMock(), asst)),
    ):
        result = await adapter.invoke({"query": "an ear"}, _turn())
    assert "did not produce" in result.content.lower()
