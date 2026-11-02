"""Tests for DEV_AUTH privilege gates."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.dev_guards import require_dev_privilege_access


def _request(ip: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    return req


def _user(user_id: str = "11111111-1111-1111-1111-111111111111") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def test_require_dev_privilege_disabled():
    settings = Settings(dev_auth_enabled=False, environment="development")
    with pytest.raises(HTTPException) as exc:
        require_dev_privilege_access(_request(), settings, _user())
    assert exc.value.status_code == 403


def test_require_dev_privilege_loopback_ok():
    settings = Settings(dev_auth_enabled=True, environment="development")
    require_dev_privilege_access(_request("127.0.0.1"), settings, _user())


def test_require_dev_privilege_remote_hidden_without_allow():
    settings = Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=False,
        environment="development",
    )
    with pytest.raises(HTTPException) as exc:
        require_dev_privilege_access(_request("8.8.8.8"), settings, _user())
    assert exc.value.status_code == 404


def test_require_dev_privilege_ignores_spoofed_forwarded_loopback():
    """Spoofed Fly-Client-IP / XFF must not unlock Pro/quota helpers."""
    settings = Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=False,
        trust_x_forwarded_for=True,
        trusted_proxy_cidrs="0.0.0.0/0",
        environment="development",
    )
    req = _request("8.8.8.8")
    req.headers = {
        "fly-client-ip": "127.0.0.1",
        "x-forwarded-for": "127.0.0.1",
    }
    with pytest.raises(HTTPException) as exc:
        require_dev_privilege_access(req, settings, _user())
    assert exc.value.status_code == 404


def test_require_dev_privilege_remote_requires_admin_allowlist():
    settings = Settings(
        dev_auth_enabled=True,
        dev_auth_allow_remote=True,
        admin_user_ids="",
        environment="development",
    )
    with pytest.raises(HTTPException) as exc:
        require_dev_privilege_access(_request("8.8.8.8"), settings, _user())
    assert exc.value.status_code == 403
