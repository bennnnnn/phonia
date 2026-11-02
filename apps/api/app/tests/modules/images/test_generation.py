"""Tests for app.modules.images.generation."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.modules.images.generation import generate_image, normalize_aspect_ratio


def test_normalize_aspect_ratio():
    assert normalize_aspect_ratio("16:9") == "16:9"
    assert normalize_aspect_ratio(" 1:1 ") == "1:1"
    assert normalize_aspect_ratio("2:1") is None
    assert normalize_aspect_ratio(None) is None


@pytest.mark.asyncio
async def test_generate_image_returns_mock_png():
    settings = Settings(mock_llm_enabled=True, image_generation_enabled=True)
    with patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=True):
        result = await generate_image(settings, prompt="a red cat")
    assert result is not None
    data, content_type = result
    assert content_type == "image/png"
    assert data.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_generate_image_disabled_returns_none():
    settings = Settings(image_generation_enabled=False)
    assert await generate_image(settings, prompt="hello") is None


@pytest.mark.asyncio
async def test_generate_image_rejects_empty_prompt():
    settings = Settings(mock_llm_enabled=True, image_generation_enabled=True)
    with patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=True):
        assert await generate_image(settings, prompt="   ") is None


@pytest.mark.asyncio
async def test_generate_image_openrouter_b64_json():
    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    import base64

    png = b"\x89PNG\r\n\x1a\n"
    payload = {"data": [{"b64_json": base64.b64encode(png).decode("ascii")}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=mock_client),
    ):
        result = await generate_image(settings, prompt="sunset over mountains", aspect_ratio="16:9")

    assert result == (png, "image/png")
    call_json = mock_client.post.await_args.kwargs["json"]
    assert call_json["aspect_ratio"] == "16:9"


def _mock_http_client(**kwargs):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    for name, value in kwargs.items():
        setattr(client, name, value)
    return client


def _streaming_get_client(body: bytes, content_type: str):
    """A fetch client whose GET streams ``body``: the download reads at most a byte past
    the size cap, so it streams instead of buffering the whole response."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {"content-type": content_type}
    response.request = httpx.Request("GET", "https://93.184.216.34/out.png")

    async def aiter_bytes():
        for start in range(0, len(body), 1 << 20):
            yield body[start : start + (1 << 20)]

    response.aiter_bytes = aiter_bytes

    class _Stream:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return None

    client = _mock_http_client(get=AsyncMock())
    client.stream = MagicMock(return_value=_Stream())
    return client


@pytest.mark.asyncio
async def test_edit_sends_real_reference_bytes():
    import base64

    png = b"\x89PNG\r\n\x1a\n"
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": [{"b64_json": base64.b64encode(png).decode()}]}
    client = _mock_http_client(post=AsyncMock(return_value=response))
    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=client),
    ):
        result = await generate_image(
            Settings(openrouter_api_key="test-key"),
            prompt="make it blue",
            reference_images=[(png, "image/png")],
        )
    assert result == (png, "image/png")
    reference = client.post.await_args.kwargs["json"]["input_references"][0]
    assert reference == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()},
    }


@pytest.mark.asyncio
async def test_reference_lookup_rejects_another_users_image_before_reading_storage():
    from uuid import uuid4

    from app.modules.images.generation import ImageGenerationError, load_reference_images

    gateway = AsyncMock()
    with patch(
        "app.modules.images.generation.attachments_service.get_by_ids", AsyncMock(return_value=[])
    ):
        with pytest.raises(ImageGenerationError, match="Reference image not found"):
            await load_reference_images(gateway, user_id=uuid4(), attachment_ids=[uuid4()])
    gateway.read_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_image_openrouter_url_response_is_fetched_ssrf_safely():
    """When OpenRouter returns a `url` instead of b64_json, the image bytes must be
    fetched through the shared SSRF-safe helper (DNS-pinned), not a plain GET."""
    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    payload = {"data": [{"url": "https://cdn.example.com/out.png"}]}
    post_response = MagicMock()
    post_response.status_code = 200
    post_response.json.return_value = payload
    post_response.raise_for_status = MagicMock()
    post_client = _mock_http_client(post=AsyncMock(return_value=post_response))

    png = b"\x89PNG\r\n\x1a\n"
    get_client = _streaming_get_client(png, "image/png")

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=post_client),
        patch("app.gateways.safe_fetch.fetch_client", return_value=get_client),
        patch(
            "app.gateways.safe_fetch.resolve_external_host",
            AsyncMock(return_value=("cdn.example.com", "93.184.216.34")),
        ),
    ):
        result = await generate_image(settings, prompt="sunset over mountains")

    assert result == (png, "image/png")
    get_client.get.assert_not_awaited()
    call = get_client.stream.call_args
    # The request must go out to the pinned IP, not the raw hostname.
    assert call.args[:2] == ("GET", "https://93.184.216.34/out.png")
    assert call.kwargs["headers"]["Host"] == "cdn.example.com"


@pytest.mark.asyncio
async def test_generate_image_openrouter_b64_json_rejects_oversized_payload():
    """BUG FIX: every other attachment path enforces MAX_ATTACHMENT_SIZE.
    A provider response bigger than that cap must be rejected, not written
    straight through to storage."""
    from app.modules.attachments.content import MAX_ATTACHMENT_SIZE

    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    import base64

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * MAX_ATTACHMENT_SIZE
    payload = {"data": [{"b64_json": base64.b64encode(oversized).decode("ascii")}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = payload
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=mock_client),
    ):
        result = await generate_image(settings, prompt="sunset over mountains")

    assert result is None


@pytest.mark.asyncio
async def test_generate_image_openrouter_url_response_rejects_oversized_payload():
    """Same size cap applied to the URL-fetch branch."""
    from app.modules.attachments.content import MAX_ATTACHMENT_SIZE

    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    payload = {"data": [{"url": "https://cdn.example.com/out.png"}]}
    post_response = MagicMock()
    post_response.status_code = 200
    post_response.json.return_value = payload
    post_response.raise_for_status = MagicMock()
    post_client = _mock_http_client(post=AsyncMock(return_value=post_response))

    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * MAX_ATTACHMENT_SIZE
    get_client = _streaming_get_client(oversized, "image/png")

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=post_client),
        patch("app.gateways.safe_fetch.fetch_client", return_value=get_client),
        patch(
            "app.gateways.safe_fetch.resolve_external_host",
            AsyncMock(return_value=("cdn.example.com", "93.184.216.34")),
        ),
    ):
        result = await generate_image(settings, prompt="sunset over mountains")

    assert result is None


@pytest.mark.asyncio
async def test_generate_image_openrouter_url_response_normalizes_content_type_casing():
    """A CDN returning a mixed-case Content-Type (valid per HTTP, case-
    insensitive by spec) must not break downstream signature matching."""
    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    payload = {"data": [{"url": "https://cdn.example.com/out.png"}]}
    post_response = MagicMock()
    post_response.status_code = 200
    post_response.json.return_value = payload
    post_response.raise_for_status = MagicMock()
    post_client = _mock_http_client(post=AsyncMock(return_value=post_response))

    png = b"\x89PNG\r\n\x1a\n"
    get_client = _streaming_get_client(png, "Image/PNG; charset=binary")

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=post_client),
        patch("app.gateways.safe_fetch.fetch_client", return_value=get_client),
        patch(
            "app.gateways.safe_fetch.resolve_external_host",
            AsyncMock(return_value=("cdn.example.com", "93.184.216.34")),
        ),
    ):
        result = await generate_image(settings, prompt="sunset over mountains")

    assert result == (png, "image/png")


@pytest.mark.asyncio
async def test_generate_image_openrouter_url_response_blocks_private_ip():
    """A provider-returned URL pointing at an internal address must be rejected,
    not fetched."""
    settings = Settings(
        openrouter_api_key="test-key",
        image_generation_enabled=True,
        image_generation_model="black-forest-labs/flux.2-klein-4b",
    )
    payload = {"data": [{"url": "http://169.254.169.254/latest/meta-data/"}]}
    post_response = MagicMock()
    post_response.status_code = 200
    post_response.json.return_value = payload
    post_response.raise_for_status = MagicMock()
    post_client = _mock_http_client(post=AsyncMock(return_value=post_response))

    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch("app.gateways.image_gateway.get_pooled_client", return_value=post_client),
    ):
        result = await generate_image(settings, prompt="sunset over mountains")

    assert result is None


def _refusing_client(status_code: int, body: str):
    response = MagicMock()
    response.status_code = status_code
    response.text = body
    response.raise_for_status = MagicMock(side_effect=RuntimeError(f"HTTP {status_code}"))
    return _mock_http_client(post=AsyncMock(return_value=response))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "body", "blocked"),
    [
        (400, '{"error":{"code":"content_policy_violation","message":"..."}}', True),
        (403, '{"error":{"message":"Your prompt was flagged by moderation"}}', True),
        (400, '{"error":{"message":"invalid aspect ratio"}}', False),
        (500, '{"error":{"message":"content_policy is down"}}', False),
    ],
)
async def test_a_content_refusal_is_told_apart_from_a_failure(
    status_code: int, body: str, blocked: bool
) -> None:
    """A provider's content refusal is said as one ("content_blocked"), not "couldn't make it"."""
    from app.gateways.image_gateway import ImageContentBlockedError

    settings = Settings(openrouter_api_key="test-key", image_generation_enabled=True)
    with (
        patch("app.modules.images.generation.mock_llm.should_mock_llm", return_value=False),
        patch(
            "app.gateways.image_gateway.get_pooled_client",
            return_value=_refusing_client(status_code, body),
        ),
    ):
        if blocked:
            with pytest.raises(ImageContentBlockedError):
                await generate_image(settings, prompt="a forbidden thing")
        else:
            assert await generate_image(settings, prompt="a cat") is None
