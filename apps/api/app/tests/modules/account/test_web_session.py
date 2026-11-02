from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models.schemas import AuthResponse, UserOut
from app.modules.account import web_session as web_session


def _fake_auth() -> AuthResponse:
    return AuthResponse(
        access_token="access-1",
        refresh_token="refresh-1",
        user=UserOut(
            id=uuid4(),
            email="dev@recall.local",
            name="Dev",
            avatar_url=None,
            plan="free",
            enabled_models=None,
            memory_enabled=True,
            created_at=datetime(2024, 1, 1),
        ),
    )


def _web_app() -> tuple[object, Settings]:
    settings = Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=True,
        jwt_secret="test-secret-32-chars-long-enough!!",
        cors_origins="http://localhost:5173",
        environment="development",
    )
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: settings
    return app, settings


def test_is_web_origin_requires_explicit_cors_allowlist():
    request = type("Req", (), {"headers": {"origin": "http://localhost:5173"}})()
    wildcard = Settings(
        jwt_secret="test-secret-32-chars-long-enough!!",
        cors_origins="*",
    )
    allowed = Settings(
        jwt_secret="test-secret-32-chars-long-enough!!",
        cors_origins="http://localhost:5173",
    )
    assert web_session.is_web_origin(request, wildcard) is False
    assert web_session.is_web_origin(request, allowed) is True


def test_web_login_sets_httponly_refresh_and_omits_token_from_json():
    app, _settings = _web_app()
    fake = _fake_auth()
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock(return_value=fake)),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/auth/dev",
            json={"email": "dev@recall.local", "name": "Dev"},
            headers={"Origin": "http://localhost:5173"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] == "access-1"
    assert body["refresh_token"] == ""
    assert body["csrf_token"]
    assert web_session.REFRESH_COOKIE in r.cookies
    assert "httponly" in r.headers.get("set-cookie", "").lower()
    assert fake.refresh_token not in r.text


def test_mobile_login_keeps_refresh_token_in_json():
    app, _settings = _web_app()
    fake = _fake_auth()
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock(return_value=fake)),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app)
        r = client.post("/auth/dev", json={"email": "dev@recall.local", "name": "Dev"})
    assert r.status_code == 200
    assert r.json()["refresh_token"] == "refresh-1"
    assert r.json().get("csrf_token") is None
    assert web_session.REFRESH_COOKIE not in r.cookies


def test_a_new_account_s_sign_in_says_it_has_not_agreed_to_ai_data_use():
    """Live: the response dropped ``ai_data_consent_at: null``; the phone read the missing
    key as consent given, and a new account went past the consent screen to the chat."""
    app, _settings = _web_app()
    fake = _fake_auth()
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock(return_value=fake)),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        r = TestClient(app).post("/auth/dev", json={"email": "dev@recall.local", "name": "Dev"})
    user = r.json()["user"]
    assert "ai_data_consent_at" in user
    assert user["ai_data_consent_at"] is None
    # The mobile body still carries no CSRF token at all.
    assert "csrf_token" not in r.json()


def test_web_refresh_requires_csrf_when_using_cookie():
    app, _settings = _web_app()
    fake = _fake_auth()
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock(return_value=fake)),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
        patch(
            "app.modules.account.api.tokens_service.refresh_token_pair",
            AsyncMock(return_value=("access-2", "refresh-2", fake.user)),
        ),
    ):
        client = TestClient(app)
        login = client.post(
            "/auth/dev",
            json={"email": "dev@recall.local", "name": "Dev"},
            headers={"Origin": "http://localhost:5173"},
        )
        csrf = login.json()["csrf_token"]
        missing = client.post(
            "/auth/refresh",
            json={},
            headers={"Origin": "http://localhost:5173"},
        )
        ok = client.post(
            "/auth/refresh",
            json={},
            headers={
                "Origin": "http://localhost:5173",
                "X-CSRF-Token": csrf,
            },
        )
    assert missing.status_code == 403
    assert ok.status_code == 200
    assert ok.json()["access_token"] == "access-2"
    assert ok.json()["refresh_token"] == ""
    assert ok.json()["csrf_token"]
