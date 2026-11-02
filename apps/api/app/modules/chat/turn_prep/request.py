"""What one turn asks for, and who is asking.

``TurnRequest`` is what new turns and regenerate hand ``build_stream_prompt_context``.
``TurnIdentity`` is the user, chat and turn mode that turn runs as, with what it asks
about places and its clock already read; the instant replies, follow-ups and
augmentation read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.models.orm import Chat, User
from app.modules import web_search as web_search_service
from app.modules.chat.stream_status import StreamStatusFn
from app.modules.chat.turn_prep.mode import _TurnMode
from app.modules.chat.turn_timing import TurnTimingTracker
from app.services import time_context as time_context_service
from app.services.subjects.registry import MathImageExtract


@dataclass(frozen=True, kw_only=True)
class TurnRequest:
    user_id: UUID
    chat_id: UUID
    content: str
    model: str
    # Required, so a caller cannot drop the device's zone by leaving it out: the
    # turn would fall back to the profile's.
    client_timezone: str | None
    has_image_attachment: bool = False
    image_math_extract: MathImageExtract | None = None
    on_status: StreamStatusFn | None = None
    # Prepare and regenerate pass all three; one left out is read in a short
    # session (see ``_load_turn_identity``).
    user: User | None = None
    chat: Chat | None = None
    turn_mode: _TurnMode | None = None
    timing: TurnTimingTracker | None = None
    omit_message_ids: set[UUID] | None = None
    force_rich_context: bool = False
    probe_attachment_rag: bool = True
    recent_messages: list[Any] | None = None
    # Messages in the chat before this turn, counted when the window loaded (None:
    # the prompt's gap reader counts them).
    prior_count: int | None = None
    current_user_message_id: UUID | None = None
    # Models whose breaker is open and cooling down, as read when the turn
    # loaded; None reads model health again for the backups.
    unhealthy_models: frozenset[str] | None = None
    # Open models past their cool-down, read with ``unhealthy_models``.
    half_open_models: frozenset[str] = frozenset()


@dataclass
class GeoAsk:
    """What a message asks about places. The app does not know where the user is."""

    # Needs the user's position: "coffee near me", "how far is the airport", "weather".
    geo_query: bool
    ambiguous_nearby: bool
    local_places: bool


@dataclass(frozen=True)
class TurnIdentity:
    user: User
    chat: Chat
    mode: _TurnMode
    geo: GeoAsk
    # Effective timezone: the client's current zone over the profile's.
    local_tz: str


def read_geo_ask(content: str) -> GeoAsk:
    geo_query = web_search_service.is_geo_query(content)
    location_question = time_context_service.is_location_question(content)
    local_places = web_search_service.is_places_list_query(content)
    ambiguous_nearby = web_search_service.is_ambiguous_local_places_query(content)
    if ambiguous_nearby:
        local_places = False
    return GeoAsk(
        geo_query=geo_query or location_question,
        ambiguous_nearby=ambiguous_nearby,
        local_places=local_places,
    )
