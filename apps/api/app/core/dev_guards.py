"""Shared gates for dangerous DEV_AUTH-only HTTP helpers.

``/auth/dev`` already requires loopback (unless ``DEV_AUTH_ALLOW_REMOTE``).
Privilege helpers like Pro upgrade and quota reset must use the same bar —
any JWT + ``DEV_AUTH_ENABLED`` alone is not enough on a shared staging host.
"""

from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request, status

from app.core.config import Settings
from app.models.orm import User


def is_loopback_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_loopback


def require_dev_auth_enabled(settings: Settings) -> None:
    if not settings.dev_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev helpers disabled",
        )


def require_dev_privilege_access(
    request: Request,
    settings: Settings,
    user: User,
) -> None:
    """Fail closed for remote callers unless DEV_AUTH_ALLOW_REMOTE is set.

    Optionally allowlisted ``ADMIN_USER_IDS`` may call from non-loopback when
    remote is enabled; when remote is off, only loopback is accepted (same as
    ``POST /auth/dev``).
    """
    require_dev_auth_enabled(settings)
    # Use the raw TCP peer — not client_ip() — so a spoofed Fly-Client-IP /
    # X-Forwarded-For of 127.0.0.1 cannot bypass the loopback guard behind a
    # pass-through proxy (same rule as POST /auth/dev).
    peer = request.client.host if request.client is not None else ""
    if is_loopback_ip(peer):
        return
    if not settings.dev_auth_allow_remote:
        # Hide the endpoint from the public internet (same 404 as /auth/dev).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    allowed = {value.strip() for value in settings.admin_user_ids.split(",") if value.strip()}
    if allowed and str(user.id) in allowed:
        return
    if not allowed:
        # Remote opted in but no admin allowlist — still require admin config
        # so any JWT can't self-grant Pro on a shared staging box.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is not configured. Set ADMIN_USER_IDS.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required.",
    )
