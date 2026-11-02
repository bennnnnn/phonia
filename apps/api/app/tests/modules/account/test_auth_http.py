import pytest

"""/auth over HTTP: the signed-in profile, its settings, and dev login."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.tests.api_support import api_user, app_with_user

# ── auth /me ───────────────────────────────────────────────────────────────────


def test_me_returns_user():
    user = api_user()
    client = TestClient(app_with_user(user))
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["email"] == user.email


def test_me_patch_updates_user():
    user = api_user()
    app = app_with_user(user)

    with patch(
        "app.modules.account.lifecycle.users_repo.update",
        AsyncMock(return_value=user),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"response_tone": "professional"},
        )
    assert r.status_code == 200


@pytest.mark.parametrize("level", ["off", "some", "more"])
def test_me_patch_sets_how_many_emoji_replies_use(level: str):
    user = api_user()
    update = AsyncMock(return_value=user)

    with patch("app.modules.account.lifecycle.users_repo.update", update):
        r = TestClient(app_with_user(user)).patch(
            "/auth/me", headers={"Authorization": "Bearer tok"}, json={"emoji_use": level}
        )
    assert r.status_code == 200
    assert update.await_args is not None and update.await_args.kwargs["emoji_use"] == level
    assert r.json()["emoji_use"] == "some"


def test_me_patch_refuses_an_emoji_level_that_does_not_exist():
    r = TestClient(app_with_user(api_user())).patch(
        "/auth/me", headers={"Authorization": "Bearer tok"}, json={"emoji_use": "lots"}
    )
    assert r.status_code == 422


def test_emoji_use_starts_at_a_few_for_every_account():
    from app.models.orm import User

    column = User.__table__.c.emoji_use
    assert column.default.arg == "some" and column.server_default.arg == "some"


def test_me_patch_invalidates_memory_cache_on_toggle():
    user = api_user()
    user.memory_enabled = True
    app = app_with_user(user)
    invalidate_mock = AsyncMock()

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(return_value=user)),
        patch(
            "app.modules.memory.cache.invalidate_memory_block",
            invalidate_mock,
        ),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"memory_enabled": False},
        )

    assert r.status_code == 200
    invalidate_mock.assert_awaited_once_with(user.id)


def test_me_patch_skips_memory_invalidation_when_unchanged():
    user = api_user()
    user.memory_enabled = True
    app = app_with_user(user)
    invalidate_mock = AsyncMock()

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(return_value=user)),
        patch(
            "app.modules.memory.cache.invalidate_memory_block",
            invalidate_mock,
        ),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"memory_enabled": True},
        )

    assert r.status_code == 200
    invalidate_mock.assert_not_called()


def test_me_returns_ai_data_consent_time():
    agreed = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    client = TestClient(app_with_user(api_user(ai_data_consent_at=agreed)))
    r = client.get("/auth/me", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.json()["ai_data_consent_at"] == "2026-10-19T12:00:00Z"

    client = TestClient(app_with_user(api_user()))
    me = client.get("/auth/me", headers={"Authorization": "Bearer tok"}).json()
    assert me["ai_data_consent_at"] is None


def _patch_capturing_fields(body: dict[str, object]) -> tuple[int, dict[str, object]]:
    user = api_user()
    app = app_with_user(user)
    captured: dict[str, object] = {}

    async def capture(_session, _user, **fields):
        captured.update(fields)
        return user

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(side_effect=capture)),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        r = TestClient(app).patch("/auth/me", headers={"Authorization": "Bearer tok"}, json=body)
    return r.status_code, captured


def test_me_patch_records_ai_data_consent_at_the_server_clock():
    before = datetime.now(UTC)
    status, captured = _patch_capturing_fields({"ai_data_consent": True})
    assert status == 200
    assert "ai_data_consent" not in captured
    stored = captured["ai_data_consent_at"]
    assert isinstance(stored, datetime) and before <= stored <= datetime.now(UTC)


def test_me_patch_withdraws_ai_data_consent():
    status, captured = _patch_capturing_fields({"ai_data_consent": False})
    assert status == 200
    assert captured["ai_data_consent_at"] is None


def test_me_patch_ignores_a_client_supplied_consent_time():
    status, captured = _patch_capturing_fields(
        {"ai_data_consent_at": "2000-01-01T00:00:00Z", "name": "Ada"}
    )
    assert status == 200
    assert "ai_data_consent_at" not in captured
    assert captured["name"] == "Ada"


def test_me_patch_rejects_blank_name():
    user = api_user()
    client = TestClient(app_with_user(user))
    r = client.patch(
        "/auth/me",
        headers={"Authorization": "Bearer tok"},
        json={"name": "   "},
    )
    assert r.status_code == 422


def test_me_patch_persists_custom_instructions_and_blank_clears():
    user = api_user()
    app = app_with_user(user)
    captured: dict[str, object] = {}

    async def capture(_session, _user, **fields):
        captured.update(fields)
        return user

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(side_effect=capture)),
        # The global REST rate limiter reads the real Redis; disable it so this
        # test is deterministic regardless of local Redis state.
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"custom_instructions": "  Always answer in bullet points.  "},
        )
    assert r.status_code == 200
    assert captured["custom_instructions"] == "Always answer in bullet points."

    # An empty/whitespace value normalizes to None (clears the field).
    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(side_effect=capture)),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        r2 = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"custom_instructions": "   "},
        )
    assert r2.status_code == 200
    assert captured["custom_instructions"] is None


def test_me_patch_accepts_supported_locale_and_normalizes():
    user = api_user()
    app = app_with_user(user)
    captured: dict[str, object] = {}

    async def capture(_session, _user, **fields):
        captured.update(fields)
        return user

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(side_effect=capture)),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        client = TestClient(app)
        # "es-MX" normalizes to "es" (split on -, lowercased) — a supported code.
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"locale": "es-MX"},
        )
    assert r.status_code == 200
    assert captured["locale"] == "es"


def test_me_patch_rejects_unsupported_locale():
    user = api_user()
    app = app_with_user(user)

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock()) as update,
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"locale": "klingon"},
        )
    assert r.status_code == 422
    update.assert_not_awaited()
    assert "Unsupported locale" in r.text


def test_me_patch_treats_empty_locale_as_noop():
    """An empty/whitespace locale string is treated as unset (no change),
    matching the custom_instructions blank-clears behavior — not stored as ''."""
    user = api_user()
    app = app_with_user(user)
    captured: dict[str, object] = {}

    async def capture(_session, _user, **fields):
        captured.update(fields)
        return user

    with (
        patch("app.modules.account.lifecycle.users_repo.update", AsyncMock(side_effect=capture)),
        patch("app.core.rest_rate_limit.allow_request", AsyncMock(return_value=True)),
    ):
        client = TestClient(app)
        r = client.patch(
            "/auth/me",
            headers={"Authorization": "Bearer tok"},
            json={"locale": "   "},
        )
    assert r.status_code == 200
    # locale should not be passed through to the update (treated as no-change).
    assert "locale" not in captured or captured.get("locale") is None


# ── dev login ──────────────────────────────────────────────────────────────────


def test_dev_login():
    from app.models.schemas import AuthResponse, UserOut

    uid = uuid4()
    fake_user_out = UserOut(
        id=uid,
        email="dev@recall.local",
        name="Dev",
        avatar_url=None,
        default_model="auto",
        plan="free",
        enabled_models=None,
        memory_enabled=True,
        created_at=datetime(2024, 1, 1),
    )
    fake_resp = AuthResponse(
        access_token="fake-token",
        refresh_token="fake-refresh",
        user=fake_user_out,
    )

    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=True,
        jwt_secret="test-secret-32-chars-long-enough!!",
    )

    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock(return_value=fake_resp)),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/auth/dev",
            json={"email": "dev@recall.local", "name": "Dev"},
        )
    assert r.status_code == 200
    assert r.json()["access_token"] == "fake-token"


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "a b@c.com", "@x.com", ""])
def test_dev_login_refuses_what_is_not_an_email(email: str):
    """Dev login made an account for "not-an-email"; it takes only an address's shape."""
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(dev_auth_enabled=True)
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock()) as login,
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        r = TestClient(app).post("/auth/dev", json={"email": email, "name": "X"})
    assert r.status_code == 422
    login.assert_not_awaited()


def test_dev_login_disabled_returns_403():
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(dev_auth_enabled=False)
    client = TestClient(app)
    r = client.post("/auth/dev", json={"email": "x@x.com", "name": "X"})
    assert r.status_code == 403


def test_dev_login_rate_limited_returns_429():
    """Dev login shares the per-IP rate limit pattern of Google/Apple so a
    single client can't mint arbitrary accounts or credential-stuff when dev
    auth is on."""
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True, jwt_secret="test-secret-32-chars-long-enough!!"
    )
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock()),
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=False),
        ),
    ):
        client = TestClient(app)
        r = client.post("/auth/dev", json={"email": "x@x.com", "name": "X"})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "sign_in_rate_limited"


def test_dev_login_refuses_non_loopback_without_allow_remote():
    """A dev config accidentally exposed on a public host must not mint
    accounts for remote callers. /auth/dev returns 404 (not 403 — don't leak
    that the endpoint exists) unless DEV_AUTH_ALLOW_REMOTE is explicitly set.
    The TestClient's peer is "testclient", which is not loopback."""
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=False,
        jwt_secret="test-secret-32-chars-long-enough!!",
    )
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock()) as login_dev,
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app)
        r = client.post("/auth/dev", json={"email": "x@x.com", "name": "X"})
    assert r.status_code == 404
    # Account minting must never run for a refused remote request.
    login_dev.assert_not_called()


def test_dev_login_ignores_spoofed_loopback_forwarded_ip():
    """Fly-Client-IP / XFF must not bypass the peer loopback guard."""
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=False,
        trust_x_forwarded_for=True,
        trusted_proxy_cidrs="0.0.0.0/0",
        jwt_secret="test-secret-32-chars-long-enough!!",
    )
    with (
        patch("app.modules.account.api.auth_service.login_dev", AsyncMock()) as login_dev,
        patch(
            "app.modules.account.signin_limit.allow_request_unless_down",
            AsyncMock(return_value=True),
        ),
    ):
        client = TestClient(app)
        r = client.post(
            "/auth/dev",
            json={"email": "x@x.com", "name": "X"},
            headers={"Fly-Client-IP": "127.0.0.1", "X-Forwarded-For": "127.0.0.1"},
        )
    assert r.status_code == 404
    login_dev.assert_not_called()


def test_revenuecat_webhook_503_when_no_auth_and_no_dev_opt_in():
    """Webhook auth must never be skipped based on `environment` alone — a
    dev config on a public host would let anyone grant themselves Pro. With
    no shared secret and no explicit DEV_ALLOW_UNAUTHED_WEBHOOKS, return 503."""
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="",
        dev_allow_unauthed_webhooks=False,
    )
    client = TestClient(app)
    r = client.post("/webhooks/revenuecat", json={"event": {"type": "TEST"}})
    assert r.status_code == 503


def test_revenuecat_webhook_rejects_oversized_body():
    app = create_app()
    from app.core.deps import get_settings_dep

    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        environment="development",
        revenuecat_webhook_auth="whsec-secret",
        dev_allow_unauthed_webhooks=False,
    )
    client = TestClient(app)
    r = client.post(
        "/webhooks/revenuecat",
        content=b"x" * (65 * 1024),
        headers={
            "Authorization": "whsec-secret",
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 413
