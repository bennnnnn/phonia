"""Validate the normalized query at the HTTP boundary."""

# Two characters is too short: a trigram index cannot narrow it.
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.db import get_db
from app.core.deps import get_current_user
from app.main import create_app
from app.tests.api_support import api_user, app_with_user


@pytest.mark.parametrize("query", ["  ", "\t\n", " a ", " ab ", "x" * 201])
def test_search_rejects_invalid_normalized_query(query):
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=uuid4())
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    with patch(
        "app.modules.search.service.search_conversations", AsyncMock(return_value=([], None))
    ) as search:
        response = TestClient(app).get("/search", params={"q": query})

    assert response.status_code == 422
    search.assert_not_awaited()


@pytest.mark.parametrize("query", ["  hello\t", " " * 201 + "oak" + " " * 201])
def test_search_passes_normalized_query(query):
    app = create_app()
    user_id = uuid4()
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=user_id)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    with patch(
        "app.modules.search.service.search_conversations", AsyncMock(return_value=([], None))
    ) as search:
        response = TestClient(app).get("/search", params={"q": query})

    assert response.status_code == 200
    assert search.await_args.args[1] == user_id
    assert search.await_args.kwargs["query"] == query.strip()


# ── search router ───────────────────────────────────────────────────────────


def test_search_returns_results():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    fake_results = [
        {
            "match_type": "message",
            "message_id": uuid4(),
            "chat_id": uuid4(),
            "chat_title": "Test Chat",
            "content": "…hello world…",
            "role": "user",
            "created_at": datetime.now(UTC),
        }
    ]
    with patch(
        "app.modules.search.api.search_service.search_conversations",
        AsyncMock(return_value=(fake_results, None)),
    ):
        client = TestClient(app)
        r = client.get(
            "/search?q=hello",
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["next_cursor"] is None
    assert len(data["items"]) == 1
    assert data["items"][0]["chat_title"] == "Test Chat"


def test_search_returns_empty():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    with patch(
        "app.modules.search.api.search_service.search_conversations",
        AsyncMock(return_value=([], None)),
    ):
        client = TestClient(app)
        r = client.get(
            "/search?q=nonexistent",
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["next_cursor"] is None
    assert data["items"] == []


def test_search_empty_query_fails():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    client = TestClient(app)
    r = client.get("/search?q=", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 422


@pytest.mark.parametrize("query", ["a", "ab"])
def test_search_short_query_fails(query):
    """Queries under three characters defeat the trigram index."""
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    client = TestClient(app)
    r = client.get(f"/search?q={query}", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 422


def test_search_respects_limit():
    from fastapi.testclient import TestClient

    user = api_user()
    app = app_with_user(user)
    fake_results = [
        {
            "match_type": "message",
            "message_id": uuid4(),
            "chat_id": uuid4(),
            "chat_title": "Chat",
            "content": "…x…",
            "role": "assistant",
            "created_at": datetime.now(UTC),
        }
        for _ in range(5)
    ]
    with patch(
        "app.modules.search.api.search_service.search_conversations",
        AsyncMock(return_value=(fake_results, "next-page")),
    ):
        client = TestClient(app)
        r = client.get(
            "/search?q=xyz&limit=5",
            headers={"Authorization": "Bearer tok"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["next_cursor"] == "next-page"
    assert len(data["items"]) == 5
