import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.production_checks import service_url_errors, trusted_proxy_cidrs_ipv4_only
from app.core.settings.attachments import AttachmentSettings
from app.core.settings.auth import AuthSettings
from app.core.settings.billing import BillingSettings
from app.core.settings.chat import ChatContextSettings
from app.core.settings.edge import EdgeSettings
from app.core.settings.infrastructure import InfrastructureSettings
from app.core.settings.llm import LlmSettings
from app.core.settings.media import MediaSettings
from app.core.settings.memory import MemorySettings
from app.core.settings.money import MoneySettings
from app.core.settings.notifications import NotificationSettings
from app.core.settings.plans import PlanAllowanceSettings
from app.core.settings.search import SearchSettings
from app.core.settings.stem import StemSettings
from app.core.settings.worker import WorkerSettings

logger = logging.getLogger(__name__)


class Settings(
    InfrastructureSettings,
    EdgeSettings,
    AuthSettings,
    LlmSettings,
    ChatContextSettings,
    MemorySettings,
    AttachmentSettings,
    StemSettings,
    SearchSettings,
    MoneySettings,
    MediaSettings,
    PlanAllowanceSettings,
    WorkerSettings,
    NotificationSettings,
    BillingSettings,
    BaseSettings,
):
    """Every setting, each read from the environment (or ``.env``) by its upper-case name.

    The fields live in purpose-named sections under ``core/settings/``; this
    class only joins them, so ``settings.<field>`` reads any of them.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def apple_revoke_configured(settings: Settings) -> bool:
    keys = (settings.apple_team_id, settings.apple_key_id, settings.apple_private_key)
    return all(value.strip() for value in keys)


def _warn_proxy_trust_misconfig(settings: Settings) -> None:
    if not settings.trust_x_forwarded_for:
        if settings.environment == "production":
            logger.warning(
                "TRUST_X_FORWARDED_FOR=false in production — behind Fly (or any "
                "proxy) every per-IP rate limit (sign-in, WebSocket handshake, "
                "anonymous REST) keys on the proxy address and becomes one "
                "global bucket. Set TRUST_X_FORWARDED_FOR=true (fly.toml [env])."
            )
        return
    if not settings.trusted_proxy_cidrs.strip():
        logger.warning(
            "TRUST_X_FORWARDED_FOR=true but TRUSTED_PROXY_CIDRS is empty — "
            "client IPs will not use XFF / Fly-Client-IP."
        )
        return
    if trusted_proxy_cidrs_ipv4_only(settings.trusted_proxy_cidrs):
        logger.warning(
            "TRUST_X_FORWARDED_FOR=true with IPv4-only TRUSTED_PROXY_CIDRS — "
            "Fly 6PN peers (fdaa::/16) will not be trusted; per-IP rate limits "
            "may collapse. Add fdaa::/16 (included in the default)."
        )


def validate_production_settings(settings: Settings) -> None:
    if settings.environment == "development":
        # Don't fully fail-closed in dev, but surface dangerous combos so a
        # dev config accidentally exposed publicly is visible in the logs.
        # The hard protection is the loopback guard on /auth/dev (core/dev_guards.py,
        # applied in modules/account/api.py) — this warning is defense-in-depth visibility.
        if settings.dev_auth_enabled and settings.dev_auth_allow_remote:
            logger.warning(
                "DEV_AUTH_ALLOW_REMOTE=true with dev auth enabled — /auth/dev "
                "will mint accounts for non-loopback callers. Never set on a "
                "shared/hosted host."
            )
        if settings.dev_allow_unauthed_webhooks:
            logger.warning(
                "DEV_ALLOW_UNAUTHED_WEBHOOKS=true — RevenueCat webhooks will be "
                "accepted with no shared secret. Local testing only."
            )
        _warn_proxy_trust_misconfig(settings)
        return

    _warn_proxy_trust_misconfig(settings)
    if not apple_revoke_configured(settings):  # delete still works; the grant outlives it
        logger.warning("APPLE_* key unset: account delete cannot revoke Sign in with Apple tokens")

    errors: list[str] = []
    if settings.dev_auth_enabled:
        errors.append("DEV_AUTH_ENABLED must be false in production")
    if settings.mock_llm_enabled:
        errors.append("MOCK_LLM_ENABLED must be false in production")
    if settings.jwt_secret == "dev-secret-change-me" or len(settings.jwt_secret) < 32:
        errors.append("JWT_SECRET must be a strong secret in production")
    errors.extend(service_url_errors(settings.database_url, settings.redis_url))
    if not settings.google_client_id:
        errors.append("GOOGLE_CLIENT_ID is required in production")
    # CORS must be explicit in production — empty CORS_ORIGINS makes
    # cors_allow_origins() fall back to ["*"], which is unsafe once a web
    # client exists. Keep the fallback and this guard in the same module.
    if not settings.cors_origins.strip():
        errors.append("CORS_ORIGINS must be set to an explicit origin list in production")
    elif any(origin.strip() == "*" for origin in settings.cors_origins.split(",")):
        errors.append("CORS_ORIGINS must not include wildcard (*) in production")
    # Without a real model key the app boots but every chat call fails at runtime
    # with a generic ModelUnavailableError — fail fast at startup instead.
    if not settings.openrouter_api_key:
        errors.append("OPENROUTER_API_KEY is required in production (chat would otherwise fail)")
    if settings.daily_global_spend_usd <= 0:
        errors.append(
            "DAILY_GLOBAL_SPEND_USD must be > 0 in production "
            "(UTC-day OpenRouter spend kill-switch)"
        )
    # Unsigned RevenueCat webhooks would let anyone grant themselves Pro.
    if not settings.revenuecat_webhook_auth:
        errors.append("REVENUECAT_WEBHOOK_AUTH is required in production")
    # TRANSFER (and POST /auth/me/sync-subscription) resolve plan via the REST
    # API. Missing the secret makes every transfer a durable source-downgrade
    # with no target upgrade.
    if not settings.revenuecat_secret_key.strip():
        errors.append(
            "REVENUECAT_SECRET_KEY is required in production "
            "(TRANSFER webhooks sync entitlements via the REST API)"
        )
    # PROCESS_ROLE=all runs the job worker + schedulers inside the API
    # process. In production the worker runs as a separate Fly process
    # (worker_main.py); an API instance that also starts a consumer would
    # join the same Redis Stream consumer group and double-process every
    # job (duplicate titles, memory extraction, emails). Force the split.
    if settings.process_role.strip().lower() not in ("api", "worker"):
        errors.append(
            "PROCESS_ROLE must be 'api' or 'worker' in production "
            "(not 'all' — the worker runs as a separate process)"
        )
    if settings.storage_backend.strip().lower() != "r2":
        errors.append("STORAGE_BACKEND must be r2 in production (local disk is ephemeral on Fly)")
    elif not all(
        [
            settings.r2_account_id.strip(),
            settings.r2_access_key_id.strip(),
            settings.r2_secret_access_key.strip(),
            settings.r2_bucket.strip(),
        ]
    ):
        errors.append(
            "R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, and R2_BUCKET "
            "are required when STORAGE_BACKEND=r2"
        )

    if errors:
        raise RuntimeError("Invalid production configuration: " + "; ".join(errors))


def cors_allow_origins(settings: Settings) -> list[str]:
    """Origins for CORSMiddleware.

    Empty ``CORS_ORIGINS`` falls back to ``["*"]`` for local dev. Production
    forbids empty and wildcard via :func:`validate_production_settings`.
    """
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    return origins or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
