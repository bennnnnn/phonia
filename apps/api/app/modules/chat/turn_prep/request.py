"""What one turn asks for, and who is asking.

``TurnRequest`` is what new turns and regenerate hand ``build_stream_prompt_context``.
``TurnIdentity`` is the user, chat and turn mode that turn runs as, with its geo and
clock already resolved; the instant replies, follow-ups and augmentation read it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.models.orm import Chat, User
from app.modules import web_search as web_search_service
from app.modules.account import profile as profile_service
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
    # Required, so a caller cannot drop the device's zone and position by
    # leaving them out: the turn would fall back to the profile's.
    client_timezone: str | None
    client_location: str | None
    client_latitude: float | None
    client_longitude: float | None
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
class ClientGeoContext:
    user_location: str | None
    client_lat: float | None
    client_lng: float | None
    has_geo_fix: bool
    geo_query: bool
    ambiguous_nearby: bool
    local_places: bool


@dataclass(frozen=True)
class TurnIdentity:
    user: User
    chat: Chat
    mode: _TurnMode
    geo: ClientGeoContext
    # Effective timezone: the client's current zone over the profile's.
    local_tz: str


def resolve_client_geo(
    user: User,
    content: str,
    *,
    client_location: str | None,
    client_latitude: float | None,
    client_longitude: float | None,
) -> ClientGeoContext:
    # Settings Location toggle is the opt-in. Ignore one-shot client geo when off
    # so a stale/malicious client cannot bypass the user's choice.
    if not user.location_enabled:
        client_location = None
        client_latitude = None
        client_longitude = None
    normalized_client_location = profile_service.normalize_client_location(client_location)
    client_coordinates = profile_service.normalize_client_coordinates(
        client_latitude, client_longitude
    )
    user_location = profile_service.effective_location_label(user, normalized_client_location)
    geo_query = web_search_service.is_geo_query(content)
    location_question = time_context_service.is_location_question(content)
    # "Where am I?" and nearby asks must use the fresh device fix, not a stale
    # profile city (or prior-chat place names).
    if geo_query or location_question:
        user_location = normalized_client_location
    client_lat = client_coordinates[0] if client_coordinates else None
    client_lng = client_coordinates[1] if client_coordinates else None
    has_geo_fix = bool(user_location) or client_coordinates is not None
    local_places = web_search_service.is_places_list_query(content)
    ambiguous_nearby = web_search_service.is_ambiguous_local_places_query(content)
    if ambiguous_nearby:
        local_places = False
    return ClientGeoContext(
        user_location=user_location,
        client_lat=client_lat,
        client_lng=client_lng,
        has_geo_fix=has_geo_fix,
        geo_query=geo_query or location_question,
        ambiguous_nearby=ambiguous_nearby,
        local_places=local_places,
    )
