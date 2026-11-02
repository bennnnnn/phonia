"""httpOnly refresh cookies for the web client (mobile stays Bearer + body).

Cookie auth is only applied when ``Origin`` is on the explicit CORS allow-list
(never ``*``). CSRF is a double-submit cookie plus ``X-CSRF-Token``.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core.config import Settings, cors_allow_origins
from app.exceptions import DomainError
from app.models.schemas import AuthResponse

REFRESH_COOKIE = "recall_refresh"
CSRF_COOKIE = "recall_csrf"
CSRF_HEADER = "x-csrf-token"


def cookie_value(request: Request, name: str) -> str | None:
    raw = request.cookies.get(name)
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    return stripped or None


def is_web_origin(request: Request, settings: Settings) -> bool:
    origin = (request.headers.get("origin") or "").strip()
    if not origin:
        return False
    allowed = cors_allow_origins(settings)
    if allowed == ["*"]:
        return False
    return origin in allowed


def _cookie_secure(settings: Settings) -> bool:
    return settings.environment.strip().lower() == "production"


def _refresh_max_age(settings: Settings) -> int:
    return max(1, settings.jwt_refresh_expire_days) * 86400


def set_web_session_cookies(
    response: Response,
    *,
    refresh_token: str,
    csrf_token: str,
    settings: Settings,
) -> None:
    secure = _cookie_secure(settings)
    max_age = _refresh_max_age(settings)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=max_age,
        path="/auth",
    )


def clear_web_session_cookies(response: Response, settings: Settings) -> None:
    secure = _cookie_secure(settings)
    response.delete_cookie(
        REFRESH_COOKIE, path="/auth", httponly=True, secure=secure, samesite="lax"
    )
    response.delete_cookie(CSRF_COOKIE, path="/auth", httponly=False, secure=secure, samesite="lax")


def require_web_csrf(request: Request) -> None:
    cookie = cookie_value(request, CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or ""
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise DomainError("CSRF check failed", status_code=403, code="csrf_failed")


def auth_json_response(
    request: Request,
    settings: Settings,
    auth: AuthResponse,
) -> JSONResponse:
    """Serialize login/refresh. Web origin gets httpOnly refresh + CSRF cookies.

    The user is sent whole, its nulls included: ``exclude_none`` dropped a new
    account's ``ai_data_consent_at: null``, the phone read the missing key as consent
    already given, and the sign-up went past the consent screen to the chat.
    """
    payload = auth.model_dump(
        mode="json", exclude={"csrf_token"} if auth.csrf_token is None else None
    )
    if not is_web_origin(request, settings):
        return JSONResponse(payload)
    csrf_token = secrets.token_urlsafe(32)
    payload["refresh_token"] = ""
    payload["csrf_token"] = csrf_token
    response = JSONResponse(payload)
    set_web_session_cookies(
        response,
        refresh_token=auth.refresh_token,
        csrf_token=csrf_token,
        settings=settings,
    )
    return response
