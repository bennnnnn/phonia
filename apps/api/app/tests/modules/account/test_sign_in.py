"""Sign in with Google or Apple: a new user, an existing one, and the email checks."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.tests.fakes import redis_mock

# ── auth service: login_with_google ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_with_google_creates_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="google@test.local",
        name="Google User",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {
        "sub": "google-sub-123",
        "email": "google@test.local",
        "name": "Google User",
        "picture": None,
    }

    with (
        patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub", AsyncMock(return_value=None)
        ),
        patch("app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=None)),
        patch("app.modules.account.service.users_repo.create", AsyncMock(return_value=MagicMock())),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("google-tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_google(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )
    assert result.access_token == "google-tok"
    assert result.user.email == "google@test.local"


@pytest.mark.asyncio
async def test_login_with_google_existing_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="existing@test.local",
        name="Existing",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "google-sub-456", "email": "existing@test.local"}

    with (
        patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("tok2", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_google(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )
    assert result.access_token == "tok2"


@pytest.mark.asyncio
async def test_login_with_google_rejects_missing_email_on_new_user():
    from app.exceptions import AuthenticationError
    from app.modules.account import service as auth_service

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "google-sub-no-email", "email": ""}

    with (
        patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub", AsyncMock(return_value=None)
        ),
    ):
        with pytest.raises(AuthenticationError, match="did not share an email"):
            await auth_service.login_with_google(
                AsyncMock(), settings_obj, "id-token", redis_mock()
            )


@pytest.mark.asyncio
async def test_login_with_google_links_existing_account_by_email():
    """Google signup after an Apple signup with the same Gmail address must link
    the accounts (set google_sub on the existing user) instead of creating a
    duplicate row, which would violate the unique(email) constraint. Addresses
    Google does not own are refused instead: test_email_authority.py."""
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="shared@gmail.com",
        name="Shared",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {
        "sub": "google-sub-new",
        "email": "shared@gmail.com",
        "name": "Shared",
        "picture": None,
    }
    existing = MagicMock(id=uid, email="shared@gmail.com", google_sub=None)

    create_mock = AsyncMock(return_value=MagicMock())
    update_mock = AsyncMock(return_value=existing)

    with (
        patch(
            "app.modules.account.service.verify_google_id_token", AsyncMock(return_value=payload)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_google_sub",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_email",
            AsyncMock(return_value=existing),
        ),
        patch("app.modules.account.service.users_repo.create", create_mock),
        patch("app.modules.account.service.users_repo.update", update_mock),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("linked-tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_google(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )

    # The existing account must be linked, not duplicated.
    create_mock.assert_not_called()
    # First update links google_sub; second refreshes email/name/avatar.
    assert update_mock.await_count >= 1
    first_call_kwargs = update_mock.call_args_list[0].kwargs
    assert first_call_kwargs.get("google_sub") == "google-sub-new"
    assert result.access_token == "linked-tok"


@pytest.mark.asyncio
async def test_login_with_apple_creates_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="apple@test.local",
        name="Apple User",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {
        "sub": "apple-sub-123",
        "email": "apple@test.local",
        "email_verified": True,
    }

    with (
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub", AsyncMock(return_value=None)
        ),
        patch("app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=None)),
        patch("app.modules.account.service.users_repo.create", AsyncMock(return_value=MagicMock())),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("apple-tok", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_apple(
            AsyncMock(), settings_obj, "id-token", redis_mock(), name="Apple User"
        )
    assert result.access_token == "apple-tok"
    assert result.user.email == "apple@test.local"


@pytest.mark.asyncio
async def test_login_with_apple_existing_user():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="apple-existing@test.local",
        name="Existing Apple",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {
        "sub": "apple-sub-456",
        "email": "apple-existing@test.local",
        "email_verified": True,
    }

    with (
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub",
            AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("tok-apple", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_apple(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )
    assert result.access_token == "tok-apple"


@pytest.mark.asyncio
async def test_login_with_apple_links_existing_account_by_email():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="shared-apple@icloud.com",
        name="Shared",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {
        "sub": "apple-sub-new",
        "email": "shared-apple@icloud.com",
        "email_verified": True,
    }
    existing = MagicMock(id=uid, email="shared-apple@icloud.com", apple_sub=None)
    create_mock = AsyncMock(return_value=MagicMock())
    update_mock = AsyncMock(return_value=existing)

    with (
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub", AsyncMock(return_value=None)
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=existing)
        ),
        patch("app.modules.account.service.users_repo.create", create_mock),
        patch("app.modules.account.service.users_repo.update", update_mock),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("linked-apple", "refresh")),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
    ):
        result = await auth_service.login_with_apple(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )

    create_mock.assert_not_called()
    assert update_mock.await_count >= 1
    first_call_kwargs = update_mock.call_args_list[0].kwargs
    assert first_call_kwargs.get("apple_sub") == "apple-sub-new"
    assert result.access_token == "linked-apple"


@pytest.mark.asyncio
async def test_login_with_apple_requires_email_on_first_sign_in():
    from app.exceptions import AuthenticationError
    from app.modules.account import service as auth_service

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "apple-sub-no-email", "email_verified": True}

    with (
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub", AsyncMock(return_value=None)
        ),
        patch("app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=None)),
    ):
        with pytest.raises(AuthenticationError, match="did not share an email"):
            await auth_service.login_with_apple(AsyncMock(), settings_obj, "id-token", redis_mock())


@pytest.mark.asyncio
async def test_login_with_apple_rejects_string_false_email_verified():
    # Apple ships `email_verified` as the string "false" (not a bool). The old
    # `is False` check let this through — an unverified identity could create
    # or link an account.
    from app.exceptions import AuthenticationError
    from app.modules.account import service as auth_service

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "apple-sub-unverified", "email": "u@x.com", "email_verified": "false"}

    with patch(
        "app.modules.account.service.verify_apple_id_token",
        AsyncMock(return_value=payload),
    ):
        with pytest.raises(AuthenticationError, match="not verified"):
            await auth_service.login_with_apple(AsyncMock(), settings_obj, "id-token", redis_mock())


@pytest.mark.asyncio
async def test_login_with_apple_rejects_missing_email_verified():
    # A missing claim must not silently pass as "verified".
    from app.exceptions import AuthenticationError
    from app.modules.account import service as auth_service

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "apple-sub-missing", "email": "m@x.com"}

    with patch(
        "app.modules.account.service.verify_apple_id_token",
        AsyncMock(return_value=payload),
    ):
        with pytest.raises(AuthenticationError, match="not verified"):
            await auth_service.login_with_apple(AsyncMock(), settings_obj, "id-token", redis_mock())


@pytest.mark.asyncio
async def test_login_with_apple_accepts_string_true_email_verified():
    from app.models.schemas import UserOut
    from app.modules.account import service as auth_service

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="strtrue@test.local",
        name="Str True",
        avatar_url=None,
        default_model="free-chat",
        memory_enabled=True,
        created_at="2024-01-01T00:00:00",
    )
    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!"
    )
    payload = {"sub": "apple-str-true", "email": "strtrue@test.local", "email_verified": "true"}

    with (
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_apple_sub", AsyncMock(return_value=None)
        ),
        patch("app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=None)),
        patch(
            "app.modules.account.service.users_repo.create",
            AsyncMock(return_value=MagicMock(id=uid)),
        ),
        patch("app.modules.account.service.UserOut.model_validate", return_value=fake_user_out),
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("a", "r")),
        ),
    ):
        result = await auth_service.login_with_apple(
            AsyncMock(), settings_obj, "id-token", redis_mock()
        )
    assert result.access_token == "a"


@pytest.mark.asyncio
async def test_verify_google_id_token_rejects_string_false_email_verified():
    # Google ships a bool, but a string "false" from an intermediary must
    # not be truthy.
    from app.exceptions import AuthenticationError
    from app.gateways.google_auth import _verify_google_id_token_sync

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        google_client_id="client-id"
    )
    with patch(
        "app.gateways.google_auth.id_token.verify_oauth2_token",
        return_value={"sub": "g", "email": "g@x.com", "email_verified": "false"},
    ):
        with pytest.raises(AuthenticationError, match="not verified"):
            _verify_google_id_token_sync("tok", settings_obj)


@pytest.mark.asyncio
async def test_login_dev_raises_when_disabled():
    from app.exceptions import AuthenticationError
    from app.modules.account import service as auth_service

    settings_obj = __import__("app.core.config", fromlist=["Settings"]).Settings(
        dev_auth_enabled=False
    )
    with pytest.raises(AuthenticationError):
        await auth_service.login_dev(
            AsyncMock(), settings_obj, email="x@x.com", name="X", redis=redis_mock()
        )
