from pathlib import Path

import pytest

from app.core.config import Settings, validate_production_settings
from app.core.production_checks import service_url_errors
from app.core.rate_limit import allow_request

# Production service URLs that pass the boot rules (not localhost, Redis over TLS).
PROD_URLS = dict(
    database_url="postgresql+asyncpg://app:pw@ep-calm-1.us-east-2.aws.neon.tech/neondb",
    redis_url="rediss://default:pw@relaxed-1.upstash.io:6379",
)


def test_example_env_keeps_long_response_ceiling_in_sync():
    example = (Path(__file__).resolve().parents[3] / ".env.example").read_text()
    configured = next(
        line.split("=", 1)[1]
        for line in example.splitlines()
        if line.startswith("MAX_OUTPUT_TOKENS=")
    )

    assert int(configured) == Settings.model_fields["max_output_tokens"].default == 8192


def test_validate_production_settings_ok():
    validate_production_settings(
        Settings(
            **PROD_URLS,
            environment="production",
            dev_auth_enabled=False,
            mock_llm_enabled=False,
            jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
            google_client_id="client-id",
            cors_origins="https://app.recall.app",
            openrouter_api_key="sk-or-xxx",
            revenuecat_webhook_auth="whsec-xxx",
            revenuecat_secret_key="sk_rc_xxx",
            storage_backend="r2",
            r2_account_id="acct",
            r2_access_key_id="key",
            r2_secret_access_key="secret",
            r2_bucket="recall",
            daily_global_spend_usd=100.0,
            process_role="api",
        )
    )


def test_validate_production_settings_rejects_process_role_all():
    # PROCESS_ROLE=all runs the worker inside the API process; in prod the
    # worker is a separate Fly process, so "all" would double-process every
    # job (duplicate titles, memory extraction, emails). Force the split.
    base = dict(
        **PROD_URLS,
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        revenuecat_secret_key="sk_rc_xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
        daily_global_spend_usd=100.0,
    )
    with pytest.raises(RuntimeError, match="PROCESS_ROLE"):
        validate_production_settings(Settings(**base, process_role="all"))
    # 'api' and 'worker' are both accepted in production.
    validate_production_settings(Settings(**base, process_role="api"))
    validate_production_settings(Settings(**base, process_role="worker"))


def test_default_trusted_proxy_cidrs_include_fly_6pn():
    assert "fdaa::/16" in Settings().trusted_proxy_cidrs


def test_warns_when_trusted_proxy_cidrs_ipv4_only(caplog):
    import logging

    from app.core.config import _warn_proxy_trust_misconfig

    with caplog.at_level(logging.WARNING):
        _warn_proxy_trust_misconfig(
            Settings(
                trust_x_forwarded_for=True,
                trusted_proxy_cidrs="10.0.0.0/8,127.0.0.1/32",
            )
        )
    assert any("fdaa::/16" in r.message for r in caplog.records)


def test_validate_production_settings_rejects_dev_flags():
    with pytest.raises(RuntimeError, match="DEV_AUTH_ENABLED"):
        validate_production_settings(
            Settings(
                environment="production",
                dev_auth_enabled=True,
                mock_llm_enabled=False,
                jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
                google_client_id="client-id",
                cors_origins="https://app.recall.app",
                openrouter_api_key="sk-or-xxx",
                revenuecat_webhook_auth="whsec-xxx",
            )
        )


def test_validate_production_settings_rejects_empty_cors_and_missing_secrets():
    base = dict(
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
    )
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        validate_production_settings(
            Settings(
                **base,
                cors_origins="",
                openrouter_api_key="sk-or-xxx",
                revenuecat_webhook_auth="whsec-xxx",
            )
        )
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        validate_production_settings(
            Settings(
                **base,
                cors_origins="https://app.recall.app",
                openrouter_api_key="",
                revenuecat_webhook_auth="whsec-xxx",
            )
        )
    with pytest.raises(RuntimeError, match="REVENUECAT_WEBHOOK_AUTH"):
        validate_production_settings(
            Settings(
                **base,
                cors_origins="https://app.recall.app",
                openrouter_api_key="sk-or-xxx",
                revenuecat_webhook_auth="",
            )
        )
    with pytest.raises(RuntimeError, match="REVENUECAT_SECRET_KEY"):
        validate_production_settings(
            Settings(
                **base,
                cors_origins="https://app.recall.app",
                openrouter_api_key="sk-or-xxx",
                revenuecat_webhook_auth="whsec-xxx",
                revenuecat_secret_key="",
            )
        )


def test_validate_production_settings_requires_r2():
    base = dict(
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
    )
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND"):
        validate_production_settings(Settings(**base, storage_backend="local"))
    with pytest.raises(RuntimeError, match="R2_ACCOUNT_ID"):
        validate_production_settings(
            Settings(**base, storage_backend="r2", r2_account_id="", r2_bucket="b")
        )


def test_validate_production_settings_skips_in_development():
    validate_production_settings(
        Settings(
            environment="development",
            dev_auth_enabled=True,
            mock_llm_enabled=True,
            jwt_secret="dev-secret-change-me",
        )
    )


def test_validate_production_settings_rejects_mock_llm_and_weak_jwt():
    base = dict(
        environment="production",
        dev_auth_enabled=False,
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
    )
    with pytest.raises(RuntimeError, match="MOCK_LLM_ENABLED"):
        validate_production_settings(
            Settings(
                **base,
                mock_llm_enabled=True,
                jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
            )
        )
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_production_settings(Settings(**base, mock_llm_enabled=False, jwt_secret="short"))


def test_validate_production_settings_rejects_missing_core_urls():
    base = dict(
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_production_settings(Settings(**base, database_url=""))
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        validate_production_settings(Settings(**base, redis_url=""))
    no_google = {k: v for k, v in base.items() if k != "google_client_id"}
    with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID"):
        validate_production_settings(Settings(**no_google, google_client_id=""))


def test_validate_production_settings_rejects_cors_wildcard():
    base = dict(
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
    )
    with pytest.raises(RuntimeError, match="wildcard"):
        validate_production_settings(Settings(**base, cors_origins="*"))


def test_validate_production_settings_requires_global_spend_cap():
    with pytest.raises(RuntimeError, match="DAILY_GLOBAL_SPEND_USD"):
        validate_production_settings(
            Settings(
                environment="production",
                dev_auth_enabled=False,
                mock_llm_enabled=False,
                jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
                google_client_id="client-id",
                cors_origins="https://app.recall.app",
                openrouter_api_key="sk-or-xxx",
                revenuecat_webhook_auth="whsec-xxx",
                revenuecat_secret_key="sk_rc_xxx",
                storage_backend="r2",
                r2_account_id="acct",
                r2_access_key_id="key",
                r2_secret_access_key="secret",
                r2_bucket="recall",
                daily_global_spend_usd=0,
            )
        )


@pytest.mark.parametrize(
    "database_url, redis_url, expected",
    [
        (PROD_URLS["database_url"], PROD_URLS["redis_url"], []),
        # The Settings defaults: an unset secret used to pass every check.
        (
            "postgresql+asyncpg://postgres:dev@localhost:5432/recall",
            "redis://localhost:6379",
            ["DATABASE_URL points at localhost", "REDIS_URL points at localhost"],
        ),
        (PROD_URLS["database_url"], "redis://127.0.0.1:6379/0", ["REDIS_URL points at localhost"]),
        (PROD_URLS["database_url"], "redis://cache.example.com:6379", ["rediss://"]),
        ("", "", ["DATABASE_URL is required", "REDIS_URL is required"]),
        ("postgresql://u:p@[::1]:5432/db", PROD_URLS["redis_url"], ["DATABASE_URL points"]),
    ],
)
def test_service_url_errors(database_url, redis_url, expected):
    errors = service_url_errors(database_url, redis_url)
    assert len(errors) == len(expected)
    for error, fragment in zip(errors, expected, strict=True):
        assert fragment in error


def test_validate_production_settings_rejects_the_default_redis_url():
    """A missing REDIS_URL left the localhost default: the API booted and
    answered every authenticated request with 503."""
    good = dict(
        **PROD_URLS,
        environment="production",
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="super-secret-key-that-is-at-least-32-chars!!",
        google_client_id="client-id",
        cors_origins="https://app.recall.app",
        openrouter_api_key="sk-or-xxx",
        revenuecat_webhook_auth="whsec-xxx",
        revenuecat_secret_key="sk_rc_xxx",
        storage_backend="r2",
        r2_account_id="acct",
        r2_access_key_id="key",
        r2_secret_access_key="secret",
        r2_bucket="recall",
        daily_global_spend_usd=100.0,
        process_role="worker",
    )
    validate_production_settings(Settings(**good))
    default_redis = Settings.model_fields["redis_url"].default
    with pytest.raises(RuntimeError, match="REDIS_URL points at localhost"):
        validate_production_settings(Settings(**{**good, "redis_url": default_redis}))


@pytest.mark.asyncio
async def test_allow_request(fake_redis):
    assert await allow_request(fake_redis, "rate:test", limit=2, window_seconds=60) is True
    assert await allow_request(fake_redis, "rate:test", limit=2, window_seconds=60) is True
    assert await allow_request(fake_redis, "rate:test", limit=2, window_seconds=60) is False


@pytest.mark.asyncio
async def test_allow_request_sets_ttl_on_first_hit(fake_redis):
    assert await allow_request(fake_redis, "rate:ttl", limit=5, window_seconds=90) is True
    assert await fake_redis.ttl("rate:ttl") == 90
    assert await allow_request(fake_redis, "rate:ttl", limit=5, window_seconds=90) is True
    # Subsequent hits must not refresh the window (EXPIRE NX).
    assert await fake_redis.ttl("rate:ttl") == 90


def _env_value(name: str, annotation: object, default: object, index: int) -> tuple[str, object]:
    """A value unlike the default for one field: its env text and what it must parse to."""
    if annotation is bool:
        return ("false" if default else "true"), not default
    if annotation is int:
        return str(1000 + index), 1000 + index
    if annotation is float:
        return f"{index}.25", float(f"{index}.25")
    assert annotation is str, f"{name}: add a case for {annotation!r}"
    return f"value-{name}", f"value-{name}"


def test_every_setting_loads_from_its_upper_case_env_name(monkeypatch):
    """The sections in core/settings/ keep the flat env names (``DAILY_TOKEN_LIMIT``…)."""
    expected: dict[str, object] = {}
    for index, (name, field) in enumerate(sorted(Settings.model_fields.items())):
        raw, parsed = _env_value(name, field.annotation, field.default, index)
        monkeypatch.setenv(name.upper(), raw)
        expected[name] = parsed

    loaded = Settings(_env_file=None)

    assert loaded.model_dump() == expected


def test_each_setting_is_declared_in_exactly_one_section():
    from pydantic import BaseModel

    sections = [
        base
        for base in Settings.__mro__[1:]
        if issubclass(base, BaseModel) and base.__module__.startswith("app.core.settings.")
    ]
    declared = [name for section in sections for name in section.model_fields]

    assert len(sections) >= 10
    assert len(declared) == len(set(declared)), "a setting is declared in two sections"
    assert set(declared) == set(Settings.model_fields), "every setting lives in a section"
