"""Registering and removing a phone's push token over HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_db
from app.modules.notifications import api as push_api
from app.tests.api_support import api_user, app_with_user

_TOKEN = "ExponentPushToken[abc123_DEF-456]"


async def _call(method: str, body: dict[str, object]) -> tuple[int, AsyncMock, AsyncMock]:
    user = api_user()
    app = app_with_user(user)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    upsert, delete = AsyncMock(), AsyncMock()
    with (
        patch.object(push_api.push_repo, "upsert", upsert),
        patch.object(push_api.push_repo, "delete_token", delete),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.request(method, "/users/push-token", json=body)
    return response.status_code, upsert, delete


@pytest.mark.asyncio
async def test_turning_push_off_removes_the_token_with_only_the_token() -> None:
    # What the phone sends: no platform. It used to get a 422 and the token stayed.
    status, _, delete = await _call("DELETE", {"expo_push_token": _TOKEN})
    assert status == 204
    assert delete.await_args is not None and delete.await_args.args[2] == _TOKEN


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [_TOKEN, "ExpoPushToken[xyz]"])
async def test_a_real_push_token_registers(token: str) -> None:
    status, upsert, _ = await _call("POST", {"expo_push_token": token, "platform": "ios"})
    assert status == 204 and upsert.await_args is not None
    assert upsert.await_args.kwargs["expo_push_token"] == token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token", ["not-a-token", "ExponentPushToken[]", "ExponentPushToken[a b]", "Token[abc]x"]
)
async def test_something_that_is_not_a_push_token_is_refused(token: str) -> None:
    status, upsert, _ = await _call("POST", {"expo_push_token": token, "platform": "ios"})
    assert status == 422
    upsert.assert_not_awaited()
    status, _, delete = await _call("DELETE", {"expo_push_token": token})
    assert status == 422
    delete.assert_not_awaited()
