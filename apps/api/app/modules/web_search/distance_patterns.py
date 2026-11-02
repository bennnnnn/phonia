"""Distance and trip intent: is this a trip from the user, needing their location?

Split from ``patterns.py``. "How far is the airport" is a trip from the user;
"how far did it go in that time", a walk across a named bridge, a trip between
two stated times, and a converted amount are not.
Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts (shared cases:
docs/fixtures/geo_intent_cases.json).
"""

from __future__ import annotations

import re

from app.modules.web_search.patterns import _GEO_PHRASE_GAP, _find_word

# Distance / travel from the user's location — venue-agnostic.
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts DISTANCE_INTENT.
# ``does it take`` must require a commute verb (get/drive/walk/reach/arrive).
# Bare ``how long does it take the car to travel`` is kinematics, not maps.
# A walk or drive across, around or along something ("walk across the Brooklyn
# Bridge") takes that thing's length, wherever the user is. "Walk over to
# Sara's" is still a trip from the user.
_ALONG_A_PLACE = r"(?!\s+(?:(?:across|around|over|through|along)\b(?!\s+to\b)|the\s+length\s+of\b))"
# "How far did it go in that time?" asks how far something moved: the car of
# the problem before it, a ball, a friend. A trip from the user is "how far is".
_HOW_FAR_IT_MOVED = (
    r"(?!\s+(?:does|did|do|will|would|can|could|has|had|have)\s+"
    r"(?:it|she|he|they|we|you|(?:the|this|that)\s+[a-z]+)\s+"
    r"(?:go|goes|gone|went|get|got|travel\w*|fall\w*|fell|move\w*|fly|flies|flew|flown"
    r"|roll\w*|slide|slid|drift\w*|run|ran|swim|swam|jump\w*|cover\w*)\b)"
)
_DISTANCE_INTENT = re.compile(
    r"\b("
    rf"how\s+far{_HOW_FAR_IT_MOVED}"
    r"|(?:walking|driving|drive|travel|commute)\s+(?:distance|time)"
    r"|distance\s+(?:to|from)"
    r"|how\s+long\s+(?:to\s+get"
    rf"|does\s+it\s+take\s+to\s+(?:get|reach|arrive|(?:drive|walk){_ALONG_A_PLACE})"
    rf"|is\s+the\s+(?:trip|(?:drive|walk){_ALONG_A_PLACE}))"
    r"|(?:miles|km|kilometers?|kilometres?|minutes?)\s+(?:away|from\s+(?:me|here))"
    r"|directions?\s+to"
    r")\b",
    re.IGNORECASE,
)

# "A bus leaves at 7:15am and arrives at 9:40am. How long is the trip?" is a sum
# over the two times it states. "I leave at 5pm and need to arrive by 7pm" sets
# a deadline, not an arrival time, and stays a trip from the user.
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts TIMETABLE.
_CLOCK_TIME = r"(?:\d{1,2}(?::[0-5]\d)?\s*[ap]\.?m\b\.?|\d{1,2}:[0-5]\d\b|noon\b|midnight\b)"
_TIMETABLE = re.compile(
    r"\b(?:leaves?|left|leaving|departs?|departed|departing|sets?\s+off)\b"
    rf"(?:\s+\S+){{0,3}}?\s+{_CLOCK_TIME}"
    r".{0,80}?"
    r"\b(?:arrives?|arrived|arriving|reaches|reached|lands?|landed|gets\s+in|got\s+in)\b"
    rf"(?:\s+(?!by\b)\S+){{0,3}}?\s+{_CLOCK_TIME}",
    re.IGNORECASE,
)

# "How many miles is a 5k?" and "how many minutes in an hour?" convert a stated
# amount. "How many miles is it to Hawassa?" is still a trip from the user.
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts UNIT_CONVERSION.
_UNIT_CONVERSION = re.compile(
    r"\bhow\s+many\s+(?:miles|kilometers|kilometres|km|minutes|mins)\s+"
    r"(?:(?:is|are)(?:\s+there)?(?:\s+in)?|in|makes?|equals?)\s+"
    r"(?:(?:a|an|one)\s+)?"
    r"(?:\d[\d,.]*\s*(?:k|km|kilomet(?:er|re)s?|mi|miles?|m|meters?|metres?|ft|feet|yards?"
    r"|h|hrs?|hours?|days?|weeks?|laps?|steps?)"
    r"|(?:half[\s-]?)?marathons?|kilomet(?:er|re)s?|miles?|hours?|days?|weeks?|months?"
    r"|years?|laps?)\b",
    re.IGNORECASE,
)

# Homework motion — not maps, even if the prompt also says "how far" / "how long".
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts MOTION_HOMEWORK.
_MOTION_HOMEWORK = re.compile(
    r"\b(?:"
    r"accelerat(?:e|es|ed|ing|ion)"
    r"|decelerat(?:e|es|ed|ing|ion)"
    r"|from\s+rest"
    r"|kinematics"
    r"|projectile"
    r"|free\s*falls?"
    r"|pivot"
    r"|fulcrum"
    r"|lever"
    r"|torque"
    r"|constant\s+(?:rate|acceleration|speed|velocity)"
    r"|metres?\s+per\s+second"
    r"|meters?\s+per\s+second"
    # "A train leaves at 9am and travels at 60 km/h. How far has it gone?"
    r"|km\s+(?:per|an)\s+hour|miles\s+(?:per|an)\s+hour"
    r"|travel(?:s|ed|led)?\s+at|average\s+speed"
    # "A ball is kicked at 40° ... how far does it go?" is a launch, not a trip.
    r"|thrown|kicked(?!\s+off)|(?:above|below)\s+the\s+(?:horizontal|ground)"
    # "How far is the image from the lens?" is optics, not the user's location.
    r"|lens(?:es)?|mirror|focal|echo(?:es)?|pendulum|wavelength|refract\w*"
    r")\b"
    # A speed unit may sit right on its number: "90km/h", "5m/s". The boundary
    # before it is the digit's, so these read without a leading \b.
    r"|(?<![A-Za-z])(?:m\s*/\s*s|km\s*/\s*h|kph|mph)\b"
    r"|\d\s*(?:cm|mm)\b|\d\s*°",
    re.IGNORECASE,
)

_FROM_USER = re.compile(
    r"\b(?:from\s+(?:me|here|my\s+(?:location|place))|to\s+me|where\s+i\s+am)\b",
    re.IGNORECASE,
)

# A fixed A-to-B distance names its own origin: "distance from the sun to Mars",
# "how far is the moon from the earth". From "me", "here" or "my house" it is a trip.
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts FIXED_DISTANCE_FROM.
_FIXED_DISTANCE_FROM = re.compile(
    r"\bdistance\s+from\b"
    r"|\bhow\s+far\s+(?:away\s+)?is\s+[\w' -]{1,40}?\s+from\s+(?!(?:me|here|my|our)\b)",
    re.IGNORECASE,
)

# "How many minutes to the airport?" asks about a trip; "how many minutes in a
# good nap", "how many minutes to boil an egg" or "how many miles is a 5k run?"
# asks about a duration or a length. Minutes, miles and km are a trip only
# beside where it goes or starts ("to the airport", "from here", "to Bole") or
# "away".
# Keep in sync with apps/mobile/lib/places/localPlacesQuery.ts HOW_MANY_ASKED / TRIP_PLACE.
_HOW_MANY_ASKED = re.compile(
    r"\bhow\s+many\s+(?:minutes|mins|miles|kilometers|kilometres|km)\b", re.IGNORECASE
)
_TRIP_PLACE = re.compile(
    r"\b(?:away"
    r"|get(?:ting)?\s+(?:there|here|home)"
    r"|(?:to|from)\s+(?:here|there|home|work|school|campus|town|downtown)"
    # "to the station", "from my house"; not "to the end" or "to my next class".
    r"|(?:to|from)\s+(?:the|my|our|your)\s+"
    r"(?!(?:end|start|beginning|hour|time|next|last|first)\b)[a-z]+)\b",
    re.IGNORECASE,
)
_TRIP_NAMED_PLACE = re.compile(r"\b(?i:to|from)\s+[A-Z](?![\s'\u2019])")


def trip_how_many_phrase(text: str) -> bool:
    """True for "how many minutes / miles / km" about a trip: to or from a place, or away."""
    if _HOW_MANY_ASKED.search(text) is None:
        return False
    return bool(_TRIP_PLACE.search(text) or _TRIP_NAMED_PLACE.search(text))


def distance_between_phrase(text: str) -> bool:
    """True for 'distance … between …' (city A–B), not distance-from-me."""
    low = text.lower()
    i = _find_word(low, "distance")
    if i == -1:
        return False
    rest = low[i + 8 : i + 8 + _GEO_PHRASE_GAP]
    return _find_word(rest, "between") != -1
