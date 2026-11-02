"""Deleting an Apple-linked account revokes its Apple grant, best effort, last."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, validate_production_settings
from app.main import create_app
from app.modules.account import lifecycle


def _user(*, apple_sub: str | None) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.email = "t@recall.local"
    user.apple_sub = apple_sub
    user.created_at = datetime(2024, 1, 1)
    return user


@pytest.fixture
def delete_steps() -> Iterator[list[str]]:
    """The delete's own steps, recorded in order, with every store mocked."""
    order: list[str] = []

    def step(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *_a, **_k: order.append(name))

    with ExitStack() as stack:
        for target, name in (
            ("schedule_job", "backstop_sweep"),
            ("users_repo.delete_user", "delete_user"),
            ("tokens_service.purge_user_sessions", "purge_sessions"),
            ("attachments_service.delete_account_files", "delete_files"),
            ("enqueue", "enqueue_sweep"),
            ("apple_revoke.revoke_authorization_code", "revoke_apple"),
        ):
            stack.enter_context(patch(f"app.modules.account.lifecycle.{target}", step(name)))
        for target in (
            "chats_service.follow_up_reply_ids",
            "attachments_service.delete_user_rows",
        ):
            stack.enter_context(
                patch(f"app.modules.account.lifecycle.{target}", AsyncMock(return_value=[]))
            )
        stack.enter_context(
            patch("app.modules.account.lifecycle.quota_carryover.save_on_delete", AsyncMock())
        )
        yield order


@pytest.mark.asyncio
async def test_delete_revokes_the_apple_grant_after_the_account_is_gone(delete_steps):
    user = _user(apple_sub="apple-sub")
    settings = Settings()
    await lifecycle.delete_account(
        AsyncMock(), AsyncMock(), settings, user, apple_authorization_code="code-1"
    )
    assert delete_steps == [
        "backstop_sweep",
        "delete_user",
        "purge_sessions",
        "delete_files",
        "enqueue_sweep",
        "revoke_apple",
    ]
    lifecycle.apple_revoke.revoke_authorization_code.assert_awaited_once_with(
        settings, "code-1", expected_sub="apple-sub"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "apple_sub, code",
    [("apple-sub", None), (None, "code-1"), (None, None)],
    ids=["older-app-sent-no-code", "google-only-account", "neither"],
)
async def test_delete_without_an_apple_link_or_code_skips_the_revoke(delete_steps, apple_sub, code):
    await lifecycle.delete_account(
        AsyncMock(),
        AsyncMock(),
        Settings(),
        _user(apple_sub=apple_sub),
        apple_authorization_code=code,
    )
    assert "revoke_apple" not in delete_steps
    assert delete_steps[-1] == "enqueue_sweep"


def _client(user: MagicMock) -> TestClient:
    from app.core.deps import get_current_user, get_settings_dep

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings_dep] = lambda: Settings()
    return TestClient(app)


@pytest.mark.parametrize(
    "body, code",
    [({"apple_authorization_code": "code-1"}, "code-1"), (None, None), ({}, None)],
    ids=["with-code", "no-body", "empty-body"],
)
def test_delete_me_passes_the_apple_code_through(body, code):
    user = _user(apple_sub="apple-sub")
    delete = AsyncMock()
    with patch("app.modules.account.api.account_lifecycle.delete_account", delete):
        response = _client(user).request(
            "DELETE", "/auth/me", json=body, headers={"Authorization": "Bearer tok"}
        )
    assert response.status_code == 204
    assert delete.await_args.kwargs == {"apple_authorization_code": code}


def test_delete_me_rejects_an_oversized_apple_code():
    with patch("app.modules.account.api.account_lifecycle.delete_account", AsyncMock()) as delete:
        response = _client(_user(apple_sub="apple-sub")).request(
            "DELETE",
            "/auth/me",
            json={"apple_authorization_code": "x" * 5000},
            headers={"Authorization": "Bearer tok"},
        )
    assert response.status_code == 422
    delete.assert_not_awaited()


def test_user_out_says_whether_apple_signs_in():
    from app.models.schemas import UserOut

    base = {
        "id": uuid4(),
        "email": "t@recall.local",
        "name": None,
        "avatar_url": None,
        "default_model": "free-chat",
        "memory_enabled": True,
        "created_at": datetime(2024, 1, 1),
    }
    linked = UserOut(**base, google_sub="g", apple_sub="a").model_dump()
    assert linked["apple_linked"] is True
    assert linked["sign_in_provider"] == "google"
    assert "apple_sub" not in linked
    assert UserOut(**base, google_sub="g").model_dump()["apple_linked"] is False


def _production(**overrides: str) -> Settings:
    production = Settings(
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        revenuecat_secret_key="sk_rc_xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
        daily_global_spend_usd=100.0,
        process_role="api",
        database_url="postgresql+asyncpg://u:pw@ep-recall.us-east-2.aws.neon.tech/recall",
        redis_url="rediss://default:pw@relaxed-1.upstash.io:6379",
    )
    return production.model_copy(update=overrides)


def test_production_boot_warns_without_the_apple_key(caplog):
    with caplog.at_level(logging.WARNING):
        validate_production_settings(_production())
    assert "cannot revoke Sign in with Apple tokens" in caplog.text


def test_production_boot_is_quiet_with_the_apple_key(caplog):
    with caplog.at_level(logging.WARNING):
        validate_production_settings(
            _production(apple_team_id="T", apple_key_id="K", apple_private_key="P")
        )
    assert "Sign in with Apple" not in caplog.text
