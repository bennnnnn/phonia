"""A production setting has one value, its code default, unless it is listed here (audit CLAR-07).

fly.toml's ``[env]`` overrode four code defaults (the stream and embedding timeouts, the
search classifier) and ``.env.production.example`` repeated them, with its own
``TRUSTED_PROXY_CIDRS``. Development and the tests ran timeouts production did not, and
which proxy ranges production trusted depended on which file someone copied. A value in
either file now equals the code default, or is a deployment value listed with its reason.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from app.core.config import Settings
from app.tests.fakes import isolated_settings

_REPO = Path(__file__).resolve().parents[5]
# Deployment values that differ from the default on purpose, and why.
_DEPLOY_ONLY = {
    "PROCESS_ROLE": "each Fly group runs the api or the worker; one local process runs both",
    "TRUST_X_FORWARDED_FOR": "trusted only behind Fly's proxy; a direct client could forge it",
    "DEV_AUTH_ENABLED": "a development login, refused in production",
    "MOCK_LLM_ENABLED": "development without provider keys",
    "DATABASE_URL": "the deployment's own database",
    "REDIS_URL": "the deployment's own Redis",
    "CORS_ORIGINS": "the deployment's own web origin",
    "STORAGE_BACKEND": "R2 in production, local disk in development",
    "R2_BUCKET": "the deployment's own bucket",
    "DAILY_GLOBAL_SPEND_USD": "production caps outside-AI spend; 0, no cap, in development",
}


def _fly_env() -> dict[str, str]:
    data = tomllib.loads((_REPO / "fly.toml").read_text())
    return {key: str(value) for key, value in data.get("env", {}).items()}


def _production_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (_REPO / "apps" / "api" / ".env.production.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _same(raw: str, default: object) -> bool:
    if isinstance(default, bool):
        return raw.lower() == str(default).lower()
    if isinstance(default, int | float):
        return float(raw) == float(default)
    return raw == default


@pytest.mark.parametrize(
    ("source", "values"),
    [("fly.toml", _fly_env()), (".env.production.example", _production_example())],
)
def test_a_deployed_value_is_the_default_or_listed(source: str, values: dict[str, str]) -> None:
    fields = Settings.model_fields
    wrong: list[str] = []
    for key, raw in values.items():
        field = fields.get(key.lower())
        assert field is not None, f"{source}: {key} is no setting"
        if raw and key not in _DEPLOY_ONLY and not _same(raw, field.default):
            wrong.append(f"{key}={raw} (default {field.default!r})")
    assert wrong == [], (
        f"{source}: make the default production's value, or list the key with its reason"
    )


def test_every_listed_key_is_still_deployed() -> None:
    deployed = set(_fly_env()) | set(_production_example())
    assert set(_DEPLOY_ONLY) <= deployed, sorted(set(_DEPLOY_ONLY) - deployed)


def test_a_renamed_setting_still_reads_its_old_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # One release: MATH_SOLVE_TIMEOUT_SECONDS bounds every subject's solve now.
    for name in [key for key in os.environ if key.endswith("SOLVE_TIMEOUT_SECONDS")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("MATH_SOLVE_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("MATH_SCAN_READ_RATE_LIMIT_PER_HOUR", "9")
    settings = isolated_settings()
    assert settings.stem_solve_timeout_seconds == 7.0
    assert settings.scan_read_rate_limit_per_hour == 9
