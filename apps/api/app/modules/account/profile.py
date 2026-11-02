"""Profile helpers — pure normalize wrappers + user-facing location labels."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.validation import normalize_display_name as normalize_display_name
from app.models.orm import User


def user_location_label(user: User) -> str | None:
    """Device-synced city/region when the user has location enabled."""
    if not user.location_enabled:
        return None
    text = (user.location or "").strip()
    return text or None


def normalize_client_location(raw: str | None) -> str | None:
    """Trim and validate a one-shot location label from the client."""
    if raw is None:
        return None
    text = " ".join(str(raw).strip().split())
    if not text or len(text) > 200:
        return None
    return text


def normalize_client_coordinates(
    latitude: float | None,
    longitude: float | None,
) -> tuple[float, float] | None:
    """Validate paired GPS coordinates from the client."""
    if latitude is None and longitude is None:
        return None
    if latitude is None or longitude is None:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return latitude, longitude


def effective_location_label(user: User, client_location: str | None = None) -> str | None:
    """Fresh client GPS label when location is enabled; otherwise profile city."""
    if not user.location_enabled:
        return None
    normalized = normalize_client_location(client_location)
    if normalized:
        return normalized
    text = (user.location or "").strip()
    return text or None


def settings_for_user(settings: Settings, user: User | None) -> Settings:
    """The server's switches narrowed by the user's own, for one of their turns.

    Every search path (forced search, the web_search tool, photo lookups, a photo
    above an answer, live talk) already reads these two server switches, so a user
    who turned web search off is covered everywhere by this one copy.
    """
    # ``is not False``: a row not saved yet holds None, and the column's default is on.
    if user is None or user.web_search_enabled is not False:
        return settings
    return settings.model_copy(update={"web_search_enabled": False, "image_search_enabled": False})


def with_ai_data_consent(fields: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Profile fields to write, with the client's consent answer turned into its column.

    ``ai_data_consent: true`` stores ``now`` (the server's clock, never the client's),
    ``false`` withdraws the agreement, and an absent or null answer leaves it alone.
    """
    updated = {key: value for key, value in fields.items() if key != "ai_data_consent"}
    agreed = fields.get("ai_data_consent")
    if agreed is not None:
        updated["ai_data_consent_at"] = now if agreed else None
    return updated
