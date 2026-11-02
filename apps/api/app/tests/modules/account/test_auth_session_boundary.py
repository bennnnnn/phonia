"""Identity linking and session failure behavior at sign-in boundaries."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.exceptions import AuthenticationError, RedisUnavailableError
from app.models.schemas import AppleAuthRequest, DevAuthRequest, GoogleAuthRequest
from app.modules.account import api as auth_router
from app.modules.account import service as auth_service
from app.modules.account.signin_refusals import SignInRefusedError
from app.tests.api_support import api_user
from app.tests.fakes import redis_mock


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "apple"])
async def test_email_match_cannot_replace_another_provider_identity(provider):
    # Even an address the provider owns cannot move the account to another id.
    email = "shared@gmail.com" if provider == "google" else "shared@icloud.com"
    existing = api_user(email=email, google_sub=None, apple_sub=None)
    setattr(existing, f"{provider}_sub", "existing-subject")
    payload = {"sub": "different-subject", "email": existing.email, "email_verified": True}
    with (
        patch(
            f"app.modules.account.service.verify_{provider}_id_token",
            AsyncMock(return_value=payload),
        ),
        patch(
            f"app.modules.account.service.users_repo.get_by_{provider}_sub",
            AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.account.service.users_repo.get_by_email", AsyncMock(return_value=existing)
        ),
        patch(
            "app.modules.account.service.users_repo.update", AsyncMock(return_value=existing)
        ) as update,
        patch(
            "app.modules.account.service.tokens_service.issue_token_pair",
            AsyncMock(return_value=("a", "r")),
        ) as issue,
    ):
        login = getattr(auth_service, f"login_with_{provider}")
        with pytest.raises(auth_service.AccountExistsError) as refused:
            await login(AsyncMock(), Settings(jwt_secret="x" * 32), "id-token", redis_mock())
    assert refused.value.sign_in_with == provider
    update.assert_not_awaited()
    issue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,body,service",
    [
        ("google", GoogleAuthRequest(id_token="id-token"), "login_with_google"),
        ("apple", AppleAuthRequest(id_token="id-token"), "login_with_apple"),
        ("dev", DevAuthRequest(email="dev@example.test", name="Dev"), "login_dev"),
    ],
)
async def test_login_session_store_outage_answers_sign_in_unavailable(provider, body, service):
    """503 + Retry-After with the code the login screen words (signin_refusals.py)."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    with (
        patch("app.modules.account.signin_limit.address_allowed", AsyncMock(return_value=True)),
        patch("app.modules.account.signin_limit.dev_address_allowed", AsyncMock(return_value=True)),
        patch(
            f"app.modules.account.api.auth_service.{service}",
            AsyncMock(side_effect=RedisUnavailableError()),
        ),
    ):
        login = getattr(auth_router, f"{provider}_login")
        with pytest.raises(SignInRefusedError) as refused:
            await login(
                body,
                request,
                session=AsyncMock(),
                settings=Settings(jwt_secret="x" * 32, dev_auth_enabled=True),
                redis=redis_mock(),
            )
    assert (refused.value.status_code, refused.value.code) == (503, "sign_in_unavailable")
    assert refused.value.headers == {"Retry-After": "5"}


@pytest.mark.asyncio
async def test_apple_login_hands_the_raw_nonce_to_token_verification():
    """The nonce from the app is what binds Apple's token to this sign-in."""
    request = MagicMock()
    request.client.host = "127.0.0.1"
    with (
        patch("app.modules.account.signin_limit.address_allowed", AsyncMock(return_value=True)),
        patch(
            "app.modules.account.service.verify_apple_id_token",
            AsyncMock(side_effect=AuthenticationError("Invalid Apple ID token")),
        ) as verify,
        pytest.raises(SignInRefusedError) as caught,
    ):
        await auth_router.apple_login(
            AppleAuthRequest(id_token="id-token", nonce="raw-nonce"),
            request,
            session=AsyncMock(),
            settings=Settings(jwt_secret="x" * 32),
            redis=redis_mock(),
        )
    assert (caught.value.status_code, caught.value.code) == (401, "sign_in_failed")
    assert verify.await_args.kwargs["nonce"] == "raw-nonce"
