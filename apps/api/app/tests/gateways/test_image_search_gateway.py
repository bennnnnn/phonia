"""Tests for app.gateways.image_search_gateway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways.image_search_gateway import ImageSearchHit, search_images


@pytest.mark.asyncio
async def test_search_images_disabled_returns_empty():
    settings = Settings(image_search_enabled=False, tavily_api_key="key")
    assert await search_images(settings, "an ear") == []


@pytest.mark.asyncio
async def test_search_images_no_key_falls_back_to_mock_when_enabled():
    settings = Settings(image_search_enabled=True, tavily_api_key="", mock_llm_enabled=True)
    hits = await search_images(settings, "an ear")
    assert len(hits) == 1
    assert hits[0].image_url.startswith("https://")


@pytest.mark.asyncio
async def test_search_images_no_key_no_mock_returns_empty():
    settings = Settings(image_search_enabled=True, tavily_api_key="", mock_llm_enabled=False)
    assert await search_images(settings, "an ear") == []


@pytest.mark.asyncio
async def test_search_images_with_a_key_searches_for_real_in_mock_mode():
    """Mock mode fakes photo search only without a key, like web search and the chat model."""
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key", mock_llm_enabled=True)
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "results": [{"url": "https://en.wikipedia.org/wiki/Ear", "title": "Ear"}],
        "images": ["https://en.wikipedia.org/ear.jpg"],
    }
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        hits = await search_images(settings, "an ear")
    client.post.assert_awaited_once()
    assert [hit.image_url for hit in hits] == ["https://en.wikipedia.org/ear.jpg"]


@pytest.mark.asyncio
async def test_search_images_parses_tavily_response():
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    payload = {
        "results": [{"url": "https://en.wikipedia.org/wiki/Ear", "title": "Ear - Wikipedia"}],
        "images": [
            {"url": "https://en.wikipedia.org/ear.jpg", "description": "Human ear anatomy"},
            "https://example.com/ear2.jpg",
        ],
    }
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        hits = await search_images(settings, "an ear", max_results=3)

    assert hits == [
        ImageSearchHit(
            image_url="https://en.wikipedia.org/ear.jpg",
            description="Human ear anatomy",
            source_url="https://en.wikipedia.org/wiki/Ear",
            source_title="Ear - Wikipedia",
        ),
        ImageSearchHit(
            image_url="https://example.com/ear2.jpg",
            description="",
            source_url="https://en.wikipedia.org/wiki/Ear",
            source_title="Ear - Wikipedia",
        ),
    ]
    call_json = client.post.await_args.kwargs["json"]
    assert call_json["include_images"] is True
    assert call_json["include_image_descriptions"] is True


@pytest.mark.asyncio
async def test_search_images_drops_non_https_urls():
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    payload = {"results": [], "images": ["http://insecure.example.com/ear.jpg"]}
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        hits = await search_images(settings, "an ear")
    assert hits == []


@pytest.mark.asyncio
async def test_search_images_skips_watermarked_stock_previews():
    """Live: a stock preview with "shutterstock.com · 2649692539" on it sat above an answer."""
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    payload = {
        "results": [{"url": "https://example.org/skeleton", "title": "Skeletons"}],
        "images": [
            "https://www.shutterstock.com/image-vector/cute-skeleton-260nw-2649692539.jpg",
            "https://media.gettyimages.com/id/1/skeleton.jpg",
            "https://t3.ftcdn.net/jpg/01/skeleton.jpg",
            "https://thumbs.dreamstime.com/b/skeleton.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/skeleton.png",
            # A name that only contains a stock word is not that host.
            "https://notshutterstock.com.example.org/skeleton.png",
        ],
    }
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        hits = await search_images(settings, "a cartoon skeleton", max_results=3)
    assert [hit.image_url for hit in hits] == [
        "https://upload.wikimedia.org/wikipedia/commons/skeleton.png",
        "https://notshutterstock.com.example.org/skeleton.png",
    ]


@pytest.mark.asyncio
async def test_search_images_respects_max_results():
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    payload = {
        "results": [],
        "images": [f"https://example.com/{i}.jpg" for i in range(5)],
    }
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        hits = await search_images(settings, "an ear", max_results=2)
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_search_images_provider_error_returns_empty():
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    client = AsyncMock()
    client.post = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.gateways.image_search_gateway.get_pooled_client", return_value=client):
        assert await search_images(settings, "an ear") == []


@pytest.mark.asyncio
async def test_search_images_rejects_empty_query():
    settings = Settings(image_search_enabled=True, tavily_api_key="test-key")
    assert await search_images(settings, "   ") == []
