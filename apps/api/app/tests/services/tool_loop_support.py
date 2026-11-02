"""Settings helper shared by tool-loop tests."""

from __future__ import annotations

from app.core.config import Settings


def settings(**kwargs: object) -> Settings:
    configured = Settings()
    for key, value in kwargs.items():
        setattr(configured, key, value)
    return configured
