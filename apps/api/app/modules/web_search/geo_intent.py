"""Geo / proximity / distance query classification."""

from __future__ import annotations

import re

from app.modules.web_search.distance_patterns import (
    _DISTANCE_INTENT,
    _FIXED_DISTANCE_FROM,
    _FROM_USER,
    _MOTION_HOMEWORK,
    _TIMETABLE,
    _UNIT_CONVERSION,
    distance_between_phrase,
    trip_how_many_phrase,
)
from app.modules.web_search.patterns import (
    _AMBIGUOUS_NEARBY_SUBJECT,
    _IMPLICIT_LOCAL,
    _NEARBY_INTENT,
    _PROXIMITY_PHRASES,
    _QUALIFIED_NEARBY,
    best_near_phrase,
    is_weather_request,
    non_geographic_nearest,
)
from app.modules.web_search.place_answer import LOCATION_ASK_OPENING
from app.modules.web_search.weather import around_the_user, is_worked_problem

_LOCATIONLESS_WEATHER = re.compile(
    r"^\s*(?:what(?:'s|\s+is)\s+(?:the\s+)?weather(?:\s+like)?"
    r"|weather(?:\s+(?:today|tomorrow|tonight|now))?"
    r"|(?:the\s+)?forecast(?:\s+(?:today|tomorrow|tonight))?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)


# "weather in Paris" names its place; "weather for the weekend" and "weather
# in my area" do not, so they use the user's location. "Weather on Mount Kenya"
# names its place too; "weather on Saturday" does not.
_WEATHER_PLACE = re.compile(
    r"\b(?:in|at|near|around|for)\s+"
    r"(?!(?:here|there|today|tomorrow|tonight|now|this|next|the\s+(?:weekend|week|day|morning"
    r"|afternoon|evening|night)|my\s+(?:area|location|city|town|place|neighbou?rhood))\b)"
    r"[^\W\d_]"
    r"|\bon\s+(?:the\s+)?(?:mount|mt\.?|lake|isle\s+of)\s+[^\W\d_]",
    re.IGNORECASE,
)


# "Best Ethiopian restaurant in DC", "directions to Bole airport from Piassa",
# "walk across the Brooklyn Bridge": the place is named, so the user's own
# location is not needed.
_NAMED_PLACE = re.compile(
    r"\b(?i:in|near|around|at|from|to|across|over|through|along)\s+(?:the\s+)?"
    r"[A-Z](?![\s'\u2019])"
)


def names_its_place(text: str) -> bool:
    """True when the question names a place by its proper name."""
    return _NAMED_PLACE.search(text) is not None


def is_local_weather_query(text: str) -> bool:
    """A weather question with no place named: answered for the user's location."""
    if _LOCATIONLESS_WEATHER.fullmatch(text) is not None:
        return True
    return is_weather_request(text) and _WEATHER_PLACE.search(text) is None


def _subject_without_proximity(cleaned: str) -> str:
    subject = cleaned.strip()
    for pattern in _PROXIMITY_PHRASES:
        subject = re.sub(pattern, " ", subject, flags=re.IGNORECASE)
    return " ".join(subject.split()).strip(" ?.!")


def is_proximity_query(text: str) -> bool:
    """Find something near the user — any category (restaurant, hospital, casino, …)."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if non_geographic_nearest(cleaned):
        return False
    # Places around the user outweigh a problem's numbers and subject: "Find coffee shops
    # near me within 2 km, max 5 km" lost its location (2026-11-01).
    if is_worked_problem(cleaned) and not around_the_user(cleaned):
        return False
    if _NEARBY_INTENT.search(cleaned):
        return True
    if _IMPLICIT_LOCAL.search(cleaned):
        return True
    return bool(best_near_phrase(cleaned) and "?" in cleaned)


def is_distance_query(text: str) -> bool:
    """Distance, travel time, or directions from the user's location."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if not (_DISTANCE_INTENT.search(cleaned) or trip_how_many_phrase(cleaned)):
        return False
    if _MOTION_HOMEWORK.search(cleaned):
        return False
    # An exercise asks "how far" and "how long to reach" too: a trip from the user only when
    # the line says so ("from my location").
    if is_worked_problem(cleaned) and not around_the_user(cleaned):
        return False
    if _TIMETABLE.search(cleaned) or _UNIT_CONVERSION.search(cleaned):
        return False
    if distance_between_phrase(cleaned) and not _FROM_USER.search(cleaned):
        return False
    if _FIXED_DISTANCE_FROM.search(cleaned) and not _FROM_USER.search(cleaned):
        return False
    return True


def is_geo_query(text: str) -> bool:
    """Any query that needs the user's location — places OR distance. Venue-agnostic.

    Each reader leaves a worked problem to its subject (``weather.is_worked_problem``).
    """
    return is_proximity_query(text) or is_distance_query(text) or is_local_weather_query(text)


def is_places_list_query(text: str) -> bool:
    """Render the native ```places card (find venues, not mileage-only answers)."""
    if is_ambiguous_local_places_query(text):
        return False
    return is_proximity_query(text)


def is_ambiguous_local_places_query(text: str) -> bool:
    """Nearby intent but missing sale/rent/address/etc. — ask before web search."""
    cleaned = text.strip()
    if not is_proximity_query(cleaned):
        return False
    if _QUALIFIED_NEARBY.search(cleaned):
        return False
    subject = _subject_without_proximity(cleaned)
    if not subject:
        return False
    return _AMBIGUOUS_NEARBY_SUBJECT.search(subject) is not None


_LETTER_ANSWER = re.compile(
    r"^(?:is\s+it\s+|option\s+|answer\s*(?:is\s+)?|i\s+(?:think|say|choose|pick)\s+)?"
    r"([A-D])\.?[?!.]*$",
    re.IGNORECASE,
)
_MAX_LETTER_ANSWER_LEN = 24


def is_short_letter_answer(text: str) -> bool:
    """Letter-only A–D replies should not trigger web search."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > _MAX_LETTER_ANSWER_LEN:
        return False
    return _LETTER_ANSWER.fullmatch(cleaned) is not None


def format_location_not_set_answer() -> str:
    """No user location for a geo query: ask where they are instead of guessing.

    Naming a place next answers the question there (``place_answer``).
    """
    return (
        f"{LOCATION_ASK_OPENING}, so I can't answer that for where you are.\n\n"
        "Tell me the city, or turn on **Location** in **Settings** (or allow location "
        "when prompted)."
    )
