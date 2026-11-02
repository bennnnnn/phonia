"""A request that asks about a place or the weather on its own words.

A line the turn's reading gives physics, maths or chemistry is its subject's homework, solved
or not, and no reader of the user's place claims it (``turn_reading.turn.is_homework``). A
request beside the homework that finds places or asks the weather is not the homework's:
"What's the weather like today? Also solve 2x + 3 = 7" still asks the forecast. The turn's
reading asks this of each request (``chat.turn_prep.reading``).
"""

from __future__ import annotations

from app.modules.web_search.geo_intent import is_proximity_query
from app.modules.web_search.weather import is_weather_request


def asks_about_a_place(request: str) -> bool:
    """A request that, on its own words, finds places or asks the weather."""
    return is_proximity_query(request) or is_weather_request(request)
