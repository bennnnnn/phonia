"""A new sign-in joins an account by email only where its provider owns the address.

Otherwise a Workspace admin of the victim's domain, someone who registered the
victim's lapsed domain, or the holder of an old Google/Apple account on the
address could sign in as the victim.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.core.validation import claim_is_true
from app.models.schemas import AppleAuthRequest, GoogleAuthRequest
from app.modules.account import api as auth_router
from app.modules.account import service as auth_service
from app.modules.account.email_authority import (
    AccountExistsError,
    apple_owns_email,
    google_owns_email,
    previous_sign_in,
)
from app.tests.api_support import api_user
from app.tests.fakes import redis_mock

_SETTINGS = Settings(jwt_secret="x" * 32)


@pytest.mark.parametrize(
    "email, claims, owned",
    [
        ("someone@gmail.com", {}, True),
        ("Someone@GMail.com", {}, True),
        ("someone@googlemail.com", {}, True),
        ("ceo@victim.example", {"hd": "victim.example"}, True),
        ("ceo@victim.example", {"hd": "VICTIM.example"}, True),
        ("ceo@victim.example", {}, False),
        ("ceo@victim.example", {"hd": "attacker.example"}, False),
        ("ceo@sub.victim.example", {"hd": "victim.example"}, False),
        ("ceo@victim.example", {"hd": None}, False),
        ("ceo@victim.example", {"hd": ["victim.example"]}, False),
        ("someone@gmail.com.attacker.example", {}, False),
        ("no-at-sign", {}, False),
        ("", {}, False),
    ],
)
def test_google_owns_email(email: str, claims: dict[str, Any], owned: bool) -> None:
    assert google_owns_email(claims, email) is owned


@pytest.mark.parametrize(
    "email, claims, owned",
    [
        ("abc123@privaterelay.appleid.com", {"is_private_email": "true"}, True),
        ("abc123@privaterelay.appleid.com", {}, True),
        ("x@anything.example", {"is_private_email": True}, True),
        ("someone@icloud.com", {}, True),
        ("someone@ME.com", {"is_private_email": "false"}, True),
        ("someone@mac.com", {}, True),
        ("someone@gmail.com", {"is_private_email": "false"}, False),
        ("ceo@victim.example", {}, False),
        ("ceo@victim.example", {"is_private_email": "yes"}, False),
        ("", {"is_private_email": "true"}, False),
    ],
)
def test_apple_owns_email(email: str, claims: dict[str, Any], owned: bool) -> None:
    assert apple_owns_email(claims, email) is owned


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, True),
        ("true", True),
        (" TRUE ", True),
        (False, False),
        ("false", False),
        (None, False),
        (1, False),
        ("1", False),
    ],
)
def test_claim_is_true(value: object, expected: bool) -> None:
    assert claim_is_true(value) is expected


@pytest.mark.parametrize(
    "google_sub, apple_sub, attempted, expected",
    [
        (None, "apple-sub", "google", "apple"),
        ("google-sub", None, "google", "google"),
        ("google-sub", "apple-sub", "google", "apple"),
        ("google-sub", None, "apple", "google"),
        (None, "apple-sub", "apple", "apple"),
        ("google-sub", "apple-sub", "apple", "google"),
    ],
)
def test_previous_sign_in(google_sub, apple_sub, attempted, expected) -> None:
    existing = api_user(google_sub=google_sub, apple_sub=apple_sub)
    assert previous_sign_in(existing, attempted) == expected


@dataclass
class _Repo:
    create: AsyncMock
    update: AsyncMock


def _patch_login(stack: ExitStack, provider: str, payload: dict[str, Any], existing: Any) -> _Repo:
    repo = _Repo(create=AsyncMock(), update=AsyncMock(return_value=existing))
    service = "app.modules.account.service"
    for target, value in (
        (f"{service}.verify_{provider}_id_token", AsyncMock(return_value=payload)),
        (f"{service}.users_repo.get_by_{provider}_sub", AsyncMock(return_value=None)),
        (f"{service}.users_repo.get_by_email", AsyncMock(return_value=existing)),
        (f"{service}.users_repo.create", repo.create),
        (f"{service}.users_repo.update", repo.update),
        (f"{service}.users_repo.refresh_for_update", AsyncMock()),
        (f"{service}.quota_carryover.restore_for_new_account", AsyncMock()),
        (f"{service}.tokens_service.issue_token_pair", AsyncMock(return_value=("a", "r"))),
        (f"{service}.UserOut.model_validate", MagicMock()),
        (f"{service}.AuthResponse", MagicMock()),
    ):
        stack.enter_context(patch(target, value))
    return repo


async def _login(provider: str, payload: dict[str, Any], existing: Any) -> tuple[Any, _Repo]:
    """Run one sign-in; returns (its result or the refusal, the repository mocks)."""
    with ExitStack() as stack:
        repo = _patch_login(stack, provider, payload, existing)
        login = getattr(auth_service, f"login_with_{provider}")
        try:
            return await login(AsyncMock(), _SETTINGS, "id-token", redis_mock()), repo
        except AccountExistsError as exc:
            return exc, repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email, claims",
    [
        ("shared@gmail.com", {}),
        ("ceo@victim.example", {"hd": "victim.example"}),
    ],
)
async def test_google_sign_in_joins_the_account_when_google_owns_the_email(email, claims):
    existing = api_user(email=email, google_sub=None, apple_sub="apple-sub")
    payload = {"sub": "google-new", "email": email, "email_verified": True, **claims}
    result, repo = await _login("google", payload, existing)
    assert not isinstance(result, AccountExistsError)
    assert repo.update.call_args_list[0].kwargs == {"commit": False, "google_sub": "google-new"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [{}, {"hd": "attacker.example"}],
    ids=["no-hosted-domain", "other-hosted-domain"],
)
async def test_google_sign_in_on_an_address_google_does_not_own_is_refused(claims):
    existing = api_user(email="ceo@victim.example", google_sub=None, apple_sub="apple-sub")
    payload = {"sub": "attacker", "email": "ceo@victim.example", "email_verified": True, **claims}
    result, repo = await _login("google", payload, existing)
    assert isinstance(result, AccountExistsError)
    assert result.sign_in_with == "apple"
    assert "Sign in with Apple" in str(result)
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email, claims",
    [
        ("abc@privaterelay.appleid.com", {"is_private_email": "true"}),
        ("shared@icloud.com", {}),
        ("shared@me.com", {}),
        ("shared@mac.com", {}),
    ],
)
async def test_apple_sign_in_joins_the_account_when_apple_owns_the_email(email, claims):
    existing = api_user(email=email, google_sub="google-sub", apple_sub=None)
    payload = {"sub": "apple-new", "email": email, "email_verified": "true", **claims}
    result, repo = await _login("apple", payload, existing)
    assert not isinstance(result, AccountExistsError)
    assert repo.update.call_args_list[0].kwargs == {"commit": False, "apple_sub": "apple-new"}


@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["someone@gmail.com", "ceo@victim.example"])
async def test_apple_sign_in_on_an_address_apple_does_not_own_is_refused(email):
    existing = api_user(email=email, google_sub="google-sub", apple_sub=None)
    payload = {"sub": "apple-new", "email": email, "email_verified": "true"}
    result, repo = await _login("apple", payload, existing)
    assert isinstance(result, AccountExistsError)
    assert result.sign_in_with == "google"
    repo.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_new_email_still_creates_an_account():
    payload = {"sub": "google-new", "email": "new@victim.example", "email_verified": True}
    result, repo = await _login("google", payload, None)
    assert not isinstance(result, AccountExistsError)
    assert repo.create.await_args.kwargs["google_sub"] == "google-new"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider, body, service",
    [
        ("google", GoogleAuthRequest(id_token="id-token"), "login_with_google"),
        ("apple", AppleAuthRequest(id_token="id-token"), "login_with_apple"),
    ],
)
async def test_login_api_answers_409_naming_the_earlier_sign_in(provider, body, service):
    request = MagicMock()
    request.client.host = "127.0.0.1"
    with (
        patch("app.modules.account.signin_limit.address_allowed", AsyncMock(return_value=True)),
        patch(
            f"app.modules.account.api.auth_service.{service}",
            AsyncMock(side_effect=AccountExistsError("apple")),
        ),
    ):
        login = getattr(auth_router, f"{provider}_login")
        with pytest.raises(AccountExistsError) as caught:
            await login(body, request, session=AsyncMock(), settings=_SETTINGS, redis=redis_mock())
    assert caught.value.status_code == 409
    assert caught.value.body() == {
        "code": "account_exists",
        "sign_in_with": "apple",
        "message": (
            "This email already has a Recall account. "
            "Sign in with Apple, the way you signed in before."
        ),
    }
