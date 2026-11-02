from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_db
from app.core.deps import (
    get_current_user,
    get_redis,
    get_settings_dep,
)
from app.core.dev_guards import is_loopback_ip, require_dev_privilege_access
from app.core.etag import conditional_json
from app.core.rate_limit import allow_request_unless_down
from app.core.redis_lock import acquire_lock, release_lock
from app.exceptions import AuthenticationError, DomainError, RateLimitedError
from app.models.orm import User
from app.models.schemas import (
    AccountDeleteRequest,
    AppleAuthRequest,
    AuthResponse,
    AuthSessionListOut,
    AuthSessionOut,
    DevAuthRequest,
    GoogleAuthRequest,
    LogoutRequest,
    RefreshRequest,
    SettingsConfirmOut,
    UserOut,
    UserUpdate,
)
from app.modules.account import export as export_service
from app.modules.account import lifecycle as account_lifecycle
from app.modules.account import profile as profile_service
from app.modules.account import refresh_limit, signin_limit, signin_refusals
from app.modules.account import service as auth_service
from app.modules.account import settings_proposal as settings_proposal_service
from app.modules.account import tokens as tokens_service
from app.modules.account import web_session as web_session
from app.modules.billing import subscription as subscription_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=AuthResponse)
async def google_login(
    body: GoogleAuthRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    with signin_refusals.refusals():
        # A per-IP backstop before the token is verified; per identity once it is (signin_limit).
        if not await signin_limit.address_allowed(redis, request, settings):
            raise signin_limit.SignInLimitedError()
        auth = await auth_service.login_with_google(
            session,
            settings,
            body.id_token,
            redis,
            device_label=body.device_label,
            platform=body.platform,
            ai_data_consent=body.ai_data_consent,
        )
    return web_session.auth_json_response(request, settings, auth)


@router.post("/apple", response_model=AuthResponse)
async def apple_login(
    body: AppleAuthRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    with signin_refusals.refusals():
        if not await signin_limit.address_allowed(redis, request, settings):
            raise signin_limit.SignInLimitedError()
        auth = await auth_service.login_with_apple(
            session,
            settings,
            body.id_token,
            redis,
            name=body.name,
            nonce=body.nonce,
            device_label=body.device_label,
            platform=body.platform,
            ai_data_consent=body.ai_data_consent,
        )
    return web_session.auth_json_response(request, settings, auth)


@router.post("/dev", response_model=AuthResponse)
async def dev_login(
    body: DevAuthRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    if not settings.dev_auth_enabled:
        raise signin_refusals.dev_disabled()
    with signin_refusals.refusals():
        # Dev auth bypasses provider token verification, so without a limit a
        # single client can mint arbitrary accounts or credential-stuff when dev
        # auth is on.
        if not await signin_limit.dev_address_allowed(redis, request, settings):
            raise signin_limit.SignInLimitedError()
        # Fail-closed against a dev config accidentally exposed on a public host:
        # refuse non-loopback callers unless the operator explicitly opted in with
        # DEV_AUTH_ALLOW_REMOTE. Use the raw TCP peer — not client_ip() — so a
        # spoofed Fly-Client-IP / X-Forwarded-For of 127.0.0.1 cannot bypass the
        # guard behind a pass-through proxy.
        peer = request.client.host if request.client is not None else ""
        if not settings.dev_auth_allow_remote and not is_loopback_ip(peer):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        auth = await auth_service.login_dev(
            session,
            settings,
            email=body.email,
            name=body.name,
            redis=redis,
            device_label=body.device_label,
            platform=body.platform,
            ai_data_consent=body.ai_data_consent,
        )
    return web_session.auth_json_response(request, settings, auth)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


def _refresh_refused() -> RateLimitedError:
    # Coded: the phone fails every request that needs a refresh with this refusal until
    # the wait ends, and each reader words ``rate_limited`` (the English alone named none).
    return RateLimitedError(
        "Too many refresh attempts. Try again shortly.",
        retry_after_seconds=refresh_limit.WINDOW_SECONDS,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_session(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    # Per account, read from the token, with a looser per-IP backstop (refresh_limit).
    if not await refresh_limit.address_allowed(redis, request, settings):
        raise _refresh_refused()
    cookie_refresh = web_session.cookie_value(request, web_session.REFRESH_COOKIE)
    presented = (body.refresh_token or "").strip() or cookie_refresh
    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )
    if cookie_refresh and not (body.refresh_token or "").strip():
        if not web_session.is_web_origin(request, settings):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing refresh token",
            )
        web_session.require_web_csrf(request)
    # After the web checks: a cross-site post cannot spend an account's refreshes.
    if not await refresh_limit.account_allowed(redis, presented):
        raise _refresh_refused()
    try:
        access_token, refresh_token, user = await tokens_service.refresh_token_pair(
            redis,
            presented,
            session,
            settings,
            device_label=body.device_label,
            platform=body.platform,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return web_session.auth_json_response(
        request,
        settings,
        AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user,
        ),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db),
) -> Response:
    cookie_refresh = web_session.cookie_value(request, web_session.REFRESH_COOKIE)
    refresh_token = body.refresh_token or cookie_refresh
    if cookie_refresh and not body.refresh_token:
        if not web_session.is_web_origin(request, settings):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing refresh token",
            )
        web_session.require_web_csrf(request)
    auth_header = request.headers.get("authorization", "")
    access_token: str | None = None
    if auth_header.lower().startswith("bearer "):
        access_token = auth_header[7:]
    try:
        await account_lifecycle.logout(
            session,
            redis,
            settings,
            access_token=access_token,
            refresh_token=refresh_token,
            expo_push_token=body.expo_push_token,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if web_session.is_web_origin(request, settings):
        web_session.clear_web_session_cookies(response, settings)
    return response


def _bearer_access_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        return token or None
    return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


@router.get("/sessions", response_model=AuthSessionListOut)
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> Response:
    access_token = _bearer_access_token(request)
    current_id = (
        tokens_service.session_id_from_access_token(access_token, settings)
        if access_token
        else None
    )
    rows = await tokens_service.list_sessions(redis, user.id, current_session_id=current_id)
    sessions = [
        AuthSessionOut(
            id=str(row["id"]),
            device_label=_optional_str(row.get("device_label")),
            platform=_optional_str(row.get("platform")),
            created_at=_optional_str(row.get("created_at")),
            last_seen_at=_optional_str(row.get("last_seen_at")),
            current=bool(row.get("current")),
        )
        for row in rows
    ]
    # Read on each Security visit: an unchanged list costs a 304 (core/etag.py).
    return conditional_json(request, AuthSessionListOut(sessions=sessions))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> None:
    access_token = _bearer_access_token(request)
    current_id = (
        tokens_service.session_id_from_access_token(access_token, settings)
        if access_token
        else None
    )
    try:
        await tokens_service.revoke_session(
            redis,
            user.id,
            session_id,
            current_session_id=current_id,
            settings=settings,
        )
    except tokens_service.CurrentSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except tokens_service.SessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    request: Request,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await account_lifecycle.logout_everywhere(
        session, redis, settings, user.id, access_token=_bearer_access_token(request)
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if web_session.is_web_origin(request, settings):
        web_session.clear_web_session_cookies(response, settings)
    return response


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> UserOut:
    fields = profile_service.with_ai_data_consent(
        body.model_dump(exclude_unset=True), now=datetime.now(UTC)
    )
    try:
        updated = await account_lifecycle.update_account(session, user, settings, fields)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return UserOut.model_validate(updated)


@router.post("/me/settings-proposals/{proposal_id}/confirm", response_model=SettingsConfirmOut)
async def confirm_settings_proposal(
    proposal_id: str,
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> SettingsConfirmOut:
    result = await settings_proposal_service.confirm_proposal(redis, user, proposal_id)
    return SettingsConfirmOut(
        user=UserOut.model_validate(result["user"]),
        appearance=result.get("appearance"),
        applied=result["applied"],
    )


@router.post("/me/pro-dev", response_model=UserOut)
async def dev_upgrade_pro(
    request: Request,
    plan: Literal["plus", "pro"] = "pro",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> UserOut:
    """Dev-only helper to simulate a paid subscription (``?plan=plus`` or ``pro``)."""
    require_dev_privilege_access(request, settings, user)
    updated = await account_lifecycle.upgrade_to_pro_for_dev(session, user, plan=plan)
    return UserOut.model_validate(updated)


@router.post("/me/sync-subscription", response_model=UserOut)
async def sync_subscription(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> UserOut:
    """Refresh plan from RevenueCat after a purchase or restore."""
    if not settings.revenuecat_secret_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Subscriptions are not configured on this server",
        )
    updated = await subscription_service.sync_user_plan_from_revenuecat(session, user, settings)
    return UserOut.model_validate(updated)


# One export at a time per user, and a few an hour: each reads up to a million rows.
_EXPORTS_PER_HOUR = 3
_EXPORT_LOCK_TTL_SECONDS = 600


@router.get("/me/export")
async def export_me(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    allowed = await allow_request_unless_down(
        redis, f"rate:export:{user.id}", limit=_EXPORTS_PER_HOUR, window_seconds=3600
    )
    lock_key = f"export:running:{user.id}"
    token = await acquire_lock(redis, lock_key, _EXPORT_LOCK_TTL_SECONDS) if allowed else None
    if token is None:
        raise DomainError(
            "An export is already running or was just made. Try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="export_busy",
        )

    async def body() -> AsyncIterator[str]:
        try:
            async for chunk in export_service.iter_export_json(user):
                yield chunk
        finally:
            await release_lock(redis, lock_key, token)

    return StreamingResponse(body(), media_type="application/json")


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    body: AccountDeleteRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> None:
    # Older apps send no body; an Apple-linked account then keeps its Apple grant.
    apple_code = body.apple_authorization_code if body is not None else None
    # Complete, or refused whole with the shared 503 ``unavailable`` (core/unavailable.py)
    # when Redis or the database fails before the rows commit: still signed in, so the
    # phone's retry deletes it (``account.lifecycle.delete_account``).
    await account_lifecycle.delete_account(
        session, redis, settings, user, apple_authorization_code=apple_code
    )
