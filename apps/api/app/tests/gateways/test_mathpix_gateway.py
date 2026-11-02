from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.gateways import mathpix_gateway


def test_mathpix_not_configured_without_keys():
    assert not mathpix_gateway.is_configured(Settings())


def test_mathpix_configured_when_keys_present():
    settings = Settings(mathpix_enabled=True, mathpix_app_id="id", mathpix_app_key="key")
    assert mathpix_gateway.is_configured(settings)


@pytest.mark.asyncio
async def test_ocr_image_returns_none_when_unconfigured():
    result = await mathpix_gateway.ocr_image(Settings(), content_type="image/jpeg", data=b"fake")
    assert result is None


@pytest.mark.asyncio
async def test_ocr_image_always_sends_improve_mathpix_false():
    settings = Settings(
        mathpix_enabled=True,
        mathpix_app_id="id",
        mathpix_app_key="key",
        mathpix_timeout_seconds=2.0,
    )
    response = MagicMock()
    response.json.return_value = {
        "text": "2x+7=15",
        "latex_styled": "2x+7=15",
        "confidence": 0.91,
    }
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.gateways.mathpix_gateway.get_pooled_client", return_value=client):
        result = await mathpix_gateway.ocr_image(settings, content_type="image/jpeg", data=b"fake")

    assert result is not None
    assert result.text == "2x+7=15"
    assert result.confidence == 0.91
    payload = client.post.await_args.kwargs["json"]
    assert payload["metadata"]["improve_mathpix"] is False
    headers = client.post.await_args.kwargs["headers"]
    assert headers["app_id"] == "id"
    assert headers["app_key"] == "key"
