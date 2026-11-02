"""Sign-in (Google, Apple, dev login), app JWTs and admin access."""

from pydantic import BaseModel


class AuthSettings(BaseModel):
    google_client_id: str = ""
    # Google sign-in fetches Google's signing certs when its kept copy runs out
    # (gateways/signing_keys.py). The google-auth default HTTP timeout is 120s; a
    # slow fetch now fails fast as a 503 instead of holding the sign-in (and a thread).
    google_auth_timeout_seconds: float = 10.0
    apple_client_id: str = "com.recall.app"
    # Sign in with Apple key (the .p8 contents): account delete revokes the Apple grant.
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""

    jwt_secret: str = "dev-secret-change-me"
    # 60m is intentional: jti + revoked_since cover logout/reuse; lower freely
    # via env without schema changes if you want a shorter window.
    jwt_expire_minutes: int = 60
    jwt_refresh_expire_days: int = 30
    # Comma-separated user UUIDs allowed to access /admin/* when dev_auth is on.
    admin_user_ids: str = ""

    # Dev placeholder — disable in production (validate_production_settings
    # refuses it there).
    dev_auth_enabled: bool = True
    # Dev auth mints accounts without a provider token. Even when
    # ENVIRONMENT=development is set on a host, /auth/dev refuses non-loopback
    # callers unless this is explicitly true — so a dev-config accidentally
    # deployed to a public host cannot be turned into an account-takeover
    # endpoint. Set true ONLY for local tunnel testing.
    dev_auth_allow_remote: bool = False
