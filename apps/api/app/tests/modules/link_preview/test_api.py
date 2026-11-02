"""``GET /link-preview``: scheme check, per-user rate limit, busy slots, and the card."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import create_app
from app.modules.link_preview.service import LinkPreviewBusyError

_API = "app.modules.link_preview.api"
_CARD = {
    "url": "https://example.com/a",
    "title": "Example",
    "description": "An example page",
    "domain": "example.com",
}


def _client(user_id):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=user_id)
    return TestClient(app)


@pytest.mark.parametrize("url", ["ftp://example.com/a", "javascript:alert(1)", "file:///etc/hosts"])
def test_link_preview_rejects_a_non_http_url(url):
    allow = AsyncMock(return_value=True)
    fetch = AsyncMock(return_value=_CARD)
    with (
        patch(f"{_API}.get_redis_client", return_value=MagicMock()),
        patch(f"{_API}.allow_request_unless_down", allow),
        patch(f"{_API}.fetch_link_preview_cached", fetch),
    ):
        response = _client(uuid4()).get("/link-preview", params={"url": url})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid URL"}
    allow.assert_not_awaited()
    fetch.assert_not_awaited()


def test_link_preview_returns_the_card_under_the_users_rate_key():
    user_id = uuid4()
    redis = MagicMock()
    allow = AsyncMock(return_value=True)
    fetch = AsyncMock(return_value=_CARD)
    with (
        patch(f"{_API}.get_redis_client", return_value=redis),
        patch(f"{_API}.allow_request_unless_down", allow),
        patch(f"{_API}.fetch_link_preview_cached", fetch),
    ):
        response = _client(user_id).get("/link-preview", params={"url": _CARD["url"]})

    assert response.status_code == 200
    assert response.json() == _CARD
    allow.assert_awaited_once_with(
        redis, f"rate:linkpreview:{user_id}", limit=20, window_seconds=60
    )
    assert fetch.await_args.args[1:] == (redis, _CARD["url"])
    assert fetch.await_args.kwargs == {"user_id": user_id}


def test_link_preview_rate_limited_is_429_without_a_fetch():
    fetch = AsyncMock(return_value=_CARD)
    with (
        patch(f"{_API}.get_redis_client", return_value=MagicMock()),
        patch(f"{_API}.allow_request_unless_down", AsyncMock(return_value=False)),
        patch(f"{_API}.fetch_link_preview_cached", fetch),
    ):
        response = _client(uuid4()).get("/link-preview", params={"url": _CARD["url"]})

    assert response.status_code == 429
    # Coded, as every limit is: the English alone named no code.
    assert response.json() == {
        "detail": {"code": "rate_limited", "message": "Too many requests. Try again shortly."}
    }
    assert response.headers["retry-after"] == "60"
    fetch.assert_not_awaited()


def test_link_preview_busy_is_429_with_retry_after():
    with (
        patch(f"{_API}.get_redis_client", return_value=MagicMock()),
        patch(f"{_API}.allow_request_unless_down", AsyncMock(return_value=True)),
        patch(
            f"{_API}.fetch_link_preview_cached",
            AsyncMock(side_effect=LinkPreviewBusyError()),
        ),
    ):
        response = _client(uuid4()).get("/link-preview", params={"url": _CARD["url"]})

    assert response.status_code == 429
    assert response.json() == {
        "detail": {
            "code": "link_preview_busy",
            "message": "Too many previews loading. Try again shortly.",
        }
    }
    assert response.headers["retry-after"] == "8"


@pytest.mark.parametrize("url", ["x" * 7, "https://" + "a" * 2041])
def test_link_preview_rejects_a_url_outside_its_length_bounds(url):
    with patch(f"{_API}.fetch_link_preview_cached", AsyncMock(return_value=_CARD)) as fetch:
        response = _client(uuid4()).get("/link-preview", params={"url": url})

    assert response.status_code == 422
    fetch.assert_not_awaited()
