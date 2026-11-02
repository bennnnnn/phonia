"""A weather question: the forecast or the conditions somewhere, always live.

"Under the weather", a poem about it, the weather on Mars and a temperature science asks
about ("the lowest temperature at which a substance catches fire") are no forecast.
"""

from __future__ import annotations

import re

from app.modules.turn_reading.turn import is_homework

# Weather is always live; "under the weather" or a poem about it is no forecast.
_WEATHER = re.compile(
    r"\b(?:(?:what(?:['\u2019]s|\s+is|\s+will\s+be)|how(?:['\u2019]s|\s+is))\s+the\s+"
    r"(?:weather|forecast|temperature)"
    r"|weather\s+(?:in|for|at|near|around|like|today|tomorrow|tonight|now|this\s+(?:week|weekend)"
    r"|forecast|report|update)"
    r"|(?:today|tomorrow|tonight)(?:['\u2019]s)?\s+(?:weather|forecast)"
    r"|(?:weather\s+)?forecast\s+(?:for|in|today|tomorrow|tonight|this)"
    # "The lowest temperature at which a substance catches fire", "temperature in kelvin":
    # a science question, not the temperature at a place (a Class 8 book, 2026-10-30).
    r"|temperature\s+(?:outside|today|tomorrow|tonight|right\s+now|(?:in|at)\s+(?!(?:which|whom"
    r"|room|kelvin|celsius|fahrenheit|degrees?|the\s+same|absolute|this|that|a\s+(?:substance"
    r"|body|metal|liquid|gas))\b))"
    r"|(?:(?:will|is)\s+it|^(?:i\s+(?:want|need)\s+to\s+know|(?:can|could)\s+you\s+(?:tell\s+me|check)"
    r"|do\s+you\s+know|i\s+wonder|tell\s+me|check|find\s+out)\s+(?:if|whether)\s+it(?:\s+will"
    r"|['\u2019]ll|\s+is|['\u2019]s))\s+(?:going\s+to\s+|gonna\s+)?(?:rain|snow|storm)(?:ing)?"
    r"|(?:how|is\s+it)\s+(?:hot|cold|warm|humid)\s+(?:is\s+it\s+)?(?:outside|today|out|here))\b",
    re.IGNORECASE,
)
WEATHER_NOT_A_FORECAST = re.compile(
    r"\b(?:under\s+the\s+weather|weather\s+(?:the|this|that|a)\s+\w+"
    r"|fair[- ]weather|weather(?:ing)?\s+(?:out|through)"
    r"|(?:poem|story|song|essay|haiku|joke|sentence|paragraph)s?\s+(?:about|on)\s+(?:the\s+)?weather"
    r"|(?:mean(?:s|ing)?|definition|synonyms?|spell|spelling)\b.*\bweather"
    r"|weather\b.*\b(?:mean(?:s|ing)?|definition|synonyms?)"
    r"|weather\s+vs\.?\s+whether|whether\s+(?:or|vs)"
    # A temperature science asks about: a scale, or a thing's own ("of boiling water").
    r"|temperature(?![^.?!]*\b(?:today|tonight|tomorrow|now|this\s+(?:week|weekend))\b)"
    r"\s+(?:in\s+(?:kelvin|celsius|fahrenheit|centigrade)|at\s+which"
    r"|of\s+(?:a\s+|an\s+|the\s+)?(?:boiling|melting|freezing|ice|water|steam|sun|human\s+body"
    r"|body|object|substance|liquid|gas|flame|metal|core|surface\s+of))"
    # Weather on/in/of a planet is science ("in mars" found Marseille); "Mars, PA" searches.
    r"|(?:weather|forecast|temperature|climate)(?:\s+[\w'\u2019]+){0,3}?\s+(?:(?:on|in|of|at)"
    r"\s+(?:the\s+)?(?:planet\s+)?(?:mercury|venus|mars|jupiter|saturn|uranus|neptune|pluto"
    r"|moon|titan|europa|io|other\s+planets?|another\s+planet|exoplanets?)\b(?!\s*,)"
    r"|on\s+(?:the\s+)?sun\b))",
    re.IGNORECASE,
)


def is_weather_request(text: str) -> bool:
    """A real forecast or conditions question, not a figure of speech or a writing task.

    "It's forecast to be 24°C. What is that in Fahrenheit?" converts a stated
    temperature; it asks for no forecast.
    """
    if _WEATHER.search(text) is None or WEATHER_NOT_A_FORECAST.search(text) is not None:
        return False
    if is_worked_problem(text) and not around_the_user(text):
        return False
    return not (_STATED_TEMPERATURE.search(text) and _TEMPERATURE_UNIT.search(text))


_STATED_TEMPERATURE = re.compile(r"\d\s*(?:°|degrees?\b)", re.IGNORECASE)
_TEMPERATURE_UNIT = re.compile(r"\b(?:fahrenheit|celsius|kelvin)\b", re.IGNORECASE)
# A quantity the question states: "2.50 L", "175 g", "10.0 atm", "18 meters". Two of them, a
# coordinate pair or a function make a worked problem, never a question about where the user
# is: "a 2.50 L container of 175 g of argon at 10.0 atm: what is the temperature?", "How far
# from the foot of the 18 meters tree…" and "the points closest to (0, 2)" each asked for the
# user's city (2026-10-30, Ethiopian chemistry and maths books).
# Measurements, never time: "the next 24 hours", "walk 2 km in 30 minutes" ask a forecast or a
# place.
_MEASURED = re.compile(
    r"\d(?:\.\d+)?\s*(?:mL|L|g|kg|mg|mol|atm|kPa|Pa|mmHg|torr|K|J|kJ|N|W|V|A|m|cm|km|m/s|Hz"
    r"|°\s*[CF]|(?:kilo|centi|milli)?met(?:er|re)s?|grams?|liters?|litres?|miles?|feet|foot)"
    r"(?![A-Za-z])"
)
# Coordinates of a maths object: "the point (0, 2)", not "weather near (40.7, -74.0)".
_COORDINATES = re.compile(
    r"\b(?:points?|curve|graph|line|vertex|centre|center)\b[^.?!]{0,30}"
    r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)",
    re.IGNORECASE,
)
_FUNCTION = re.compile(r"\b[a-zA-Z]\s*\(\s*[a-z]\s*\)\s*=")


# A search around the user, which no exercise asks for: "near me", "close to me", "around me",
# "near here", "in my area", "within 5 km of me", "within walking distance", "from my
# location". Not "nearby", "the nearest wall to me", "from me", "from here", "where I am" or
# a bare "here": exercises say those ("a lamp 2 m from me", "I walk 5 km from here, then 3 km
# north", "Here, a ball is dropped…", "a block at rest here."). "How hot is it here" needs no
# cue: no subject claims it.
_AROUND_THE_USER = re.compile(
    r"\b(?:(?:near|close\s+to|around)\s+(?:me|here|my\s+(?:house|home|place|hotel|office|location))"
    r"|in\s+my\s+(?:area|neighbou?rhood|city|town)"
    r"|(?:from|at|for|to)\s+my\s+(?:current\s+)?location"
    r"|within\s+(?:walking\s+distance|\d+(?:\.\d+)?\s*[a-z]+\s+of\s+(?:me|here|my\s+\w+)))\b",
    re.IGNORECASE,
)


def around_the_user(text: str) -> bool:
    """The message asks about what is around the user."""
    return _AROUND_THE_USER.search(text) is not None


def is_worked_problem(text: str) -> bool:
    """A problem that states its own measurements, coordinates or function, or homework by the
    turn's reading (``turn_reading.turn.is_homework``).

    Every reader of the user's place defers to it (places, distances and travel times, local
    weather) unless the line searches around the user (``around_the_user``): homework never
    asks where the user is. "A ball is dropped from a height of 20 m. How long does it take
    to reach the ground?" states one measurement, and was asked for the user's city
    (2026-11-01).
    """
    return (
        len(_MEASURED.findall(text)) >= 2
        or _COORDINATES.search(text) is not None
        or _FUNCTION.search(text) is not None
        or is_homework(text)
    )
