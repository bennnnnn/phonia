"""Profile helpers — pure normalize wrappers and the user's own switches."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.core.config import Settings
from app.core.validation import normalize_display_name as normalize_display_name
from app.models.orm import User


def settings_for_user(settings: Settings, user: User | None) -> Settings:
    """The server's switches narrowed by the user's own, for one of their turns.

    Every search path (forced search, the web_search tool, photo lookups, a photo
    above an answer) already reads these two server switches, so a user
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
