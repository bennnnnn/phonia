"""Dependency-neutral timezone normalization."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "UTC"


def resolve_timezone(tz: str | None) -> ZoneInfo:
    try:
        if not isinstance(tz, str):
            return ZoneInfo(DEFAULT_TIMEZONE)
        return ZoneInfo(tz.strip() or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)
