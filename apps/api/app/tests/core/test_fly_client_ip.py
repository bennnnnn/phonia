"""Per-IP rate limits key on the real client behind Fly, not on Fly's proxy.

``TRUST_X_FORWARDED_FOR`` defaults to false and was set only in
``.env.production.example`` — not in ``fly.toml`` or the PRODUCTION.md
secrets table. Unset, every request's key is the proxy's private address,
so the per-IP sign-in limit (30/min per provider), the WebSocket handshake
limit (60/min) and the anonymous REST limit (240/min) become single global
buckets that one client can exhaust for everyone.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.client_ip import client_ip
from app.core.config import Settings, validate_production_settings

_FLY_TOML = Path(__file__).resolve().parents[5] / "fly.toml"


def _fly_env_settings() -> Settings:
    env = tomllib.loads(_FLY_TOML.read_text())["env"]
    trusted = str(env.get("TRUST_X_FORWARDED_FOR", "false")).strip().lower() == "true"
    return Settings(trust_x_forwarded_for=trusted)


@pytest.mark.parametrize(
    "proxy_peer, fly_client_ip",
    [
        ("172.16.3.2", "203.0.113.5"),
        ("fdaa:0:1:a7b:1::2", "198.51.100.7"),
    ],
)
def test_fly_deploy_keys_rate_limits_on_the_client_ip(proxy_peer: str, fly_client_ip: str) -> None:
    request = MagicMock()
    request.client.host = proxy_peer
    request.headers = {"fly-client-ip": fly_client_ip}
    assert client_ip(request, _fly_env_settings()) == fly_client_ip


def test_production_warns_when_forwarded_headers_are_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://app:pw@ep-calm-1.us-east-2.aws.neon.tech/neondb",
        redis_url="rediss://default:pw@relaxed-1.upstash.io:6379",
        trust_x_forwarded_for=False,
        dev_auth_enabled=False,
        mock_llm_enabled=False,
        jwt_secret="x" * 40,
        google_client_id="cid",
        cors_origins="https://app.example",
        openrouter_api_key="k",
        daily_global_spend_usd=10,
        revenuecat_webhook_auth="w",
        revenuecat_secret_key="r",
        process_role="api",
        storage_backend="r2",
        r2_account_id="a",
        r2_access_key_id="b",
        r2_secret_access_key="c",
        r2_bucket="d",
    )
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        validate_production_settings(settings)
    assert any("TRUST_X_FORWARDED_FOR" in record.getMessage() for record in caplog.records)
