"""Dev login: creates the user, or signs in the existing one."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.tests.fakes import redis_mock

# ── auth service ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_dev_creates_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    settings = Settings(dev_auth_enabled=True, jwt_secret="test-secret-long-enough-32-chars!!")
    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="dev@test.local",
        name="Dev",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    with (
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub", AsyncMock(return_value=None)
        ),
        patch("app.modules.account.service.users_repo.create", AsyncMock(return_value=MagicMock())),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_dev(
            AsyncMock(), settings, email="dev@test.local", name="Dev", redis=redis_mock()
        )
    assert result.access_token == "tok"
    assert result.user.email == "dev@test.local"


@pytest.mark.asyncio
async def test_login_dev_returns_existing_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    settings = Settings(dev_auth_enabled=True, jwt_secret="test-secret-long-enough-32-chars!!")
    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="existing@test.local",
        name="Old",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )

    with (
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_dev(
            AsyncMock(), settings, email="existing@test.local", name="Old", redis=redis_mock()
        )
    assert result.user.email == "existing@test.local"


@pytest.mark.asyncio
async def test_login_dev_updates_name_for_existing_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    settings = Settings(dev_auth_enabled=True, jwt_secret="test-secret-long-enough-32-chars!!")
    existing = MagicMock()
    existing.name = "Dev User"
    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="dev@recall.local",
        name="bini",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )

    with (
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub",
            AsyncMock(return_value=existing),
        ),
        patch(
            "app.modules.account.service.users_repo.update",
            AsyncMock(return_value=existing),
        ) as mock_update,
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_dev(
            AsyncMock(),
            settings,
            email="dev@recall.local",
            name="bini",
            redis=redis_mock(),
        )
    mock_update.assert_awaited_once()
    assert result.user.name == "bini"
