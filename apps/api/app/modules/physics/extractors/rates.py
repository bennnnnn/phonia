"""Whole-request extraction for the distance-speed-time law."""

from __future__ import annotations

import re

from app.modules.physics.catalog.kinematics import CLOSED_PATH, ONE_TURN
from app.modules.physics.catalog.suvat import TWO_BODIES
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.words import word_pattern
from app.services.unit_text import LENGTH_UNITS, QUANTITY_NUMBER, TIME_UNITS, unit_after_quantity

_VELOCITY_ASK_RE = re.compile(r"\bvelocit(?:y|ies)\b")

_RATE_CUES = (
    "average speed",
    "what is its speed",
    "what is the speed",
    "what distance",
    "how far",
    "how long does it take",
)

# A stop is not constant speed. "15 m/s ... to a stop in 3 s, how far" is
# braking distance, and d = vt would answer 45 m instead of 22.5 m.
_STOP_OR_BRAKE_RE = re.compile(
    r"\b(?:to\s+(?:a\s+)?(?:stop|rest|halt)|brak(?:e|es|ing))\b",
    re.IGNORECASE,
)


def extract_rate_intent(cleaned: str) -> PhysicsIntent | None:
    """Extract exactly two compatible givens and one requested rate quantity."""
    if _STOP_OR_BRAKE_RE.search(cleaned):
        return None
    lower = cleaned.lower()
    # A length covered once a turn is a radius, not the distance (2πr), and two
    # bodies' speeds are not one speed. Neither is d = vt.
    if any(word_pattern(phrase).search(lower) for phrase in (*ONE_TURN, *TWO_BODIES)):
        return None
    # A lap ends where it began: its average velocity is zero, not d/t.
    if _VELOCITY_ASK_RE.search(lower) and any(
        word_pattern(phrase).search(lower) for phrase in CLOSED_PATH
    ):
        return None
    if not any(word in lower for word in ("speed", "velocity", "distance", "how far", "how long")):
        return None

    def speed_unit_after(number_end: int) -> tuple[str, str, int] | None:
        match = re.match(
            r"\s*([A-Za-z]+)\s*(?:/|\bper\b)\s*([A-Za-z]+)\b",
            cleaned[number_end:],
            re.IGNORECASE,
        )
        if match is None:
            return None
        length_name, time_name = (group.lower() for group in match.groups())
        if length_name not in LENGTH_UNITS or time_name not in TIME_UNITS:
            return None
        return LENGTH_UNITS[length_name], TIME_UNITS[time_name], number_end + match.end()

    numbers = list(QUANTITY_NUMBER.finditer(cleaned))
    if len(numbers) != 2:
        return None
    measures: list[tuple[str, float, str, str | None, int]] = []
    for number in numbers:
        speed_unit = speed_unit_after(number.end())
        if speed_unit is not None:
            length_unit, time_unit, end = speed_unit
            measures.append(("speed", float(number.group(0)), length_unit, time_unit, end))
            continue
        unit_hit = unit_after_quantity(cleaned, number.end())
        if unit_hit is None:
            return None
        unit = unit_hit[0].lower()
        if unit in LENGTH_UNITS:
            measures.append(
                ("distance", float(number.group(0)), LENGTH_UNITS[unit], None, unit_hit[1])
            )
        elif unit in TIME_UNITS:
            measures.append(("time", float(number.group(0)), TIME_UNITS[unit], None, unit_hit[1]))
        else:
            return None

    tail = cleaned[measures[-1][4] :].strip()
    plain_tail = tail.strip(" .?!").lower()
    speed_question = re.fullmatch(
        r"[.?!]*\s*(?:what\s+is|what's|find|calculate|compute|determine)\s+"
        r"(?:the|its|his|her|their)\s+(?:average\s+)?(?:speed|velocity)(?:\s+please)?[.?!]*",
        tail,
        re.IGNORECASE,
    )
    distance_question = re.fullmatch(
        r"[.?!]*\s*(?:(?:what\s+(?:is\s+)?(?:the|its|his|her|their)?\s*distance)|"
        r"(?:how\s+far(?:\s+does\s+it\s+travel)?)|"
        r"(?:(?:find|calculate|compute|determine)\s+(?:the|its|his|her|their)?\s*distance))"
        r"(?:\s+(?:does\s+it\s+travel|travelled|traveled))?(?:\s+please)?[.?!]*",
        tail,
        re.IGNORECASE,
    )
    time_question = re.fullmatch(
        r"[.?!]*\s*(?:(?:how\s+long(?:\s+does\s+it\s+take)?)|"
        r"(?:(?:what\s+is|find|calculate|compute|determine)\s+(?:the|its|his|her|their)?\s*time))"
        r"(?:\s+does\s+it\s+take)?(?:\s+please)?[.?!]*",
        tail,
        re.IGNORECASE,
    )
    prefix = cleaned[: numbers[0].start()].strip(" .?!").lower()
    requested: str | None = None
    if speed_question is not None or (
        plain_tail in {"", "please"}
        and re.search(r"(?:average\s+)?(?:speed|velocity)\s*(?:for|of)?\s*$", prefix)
    ):
        requested = "speed"
    elif distance_question is not None or (
        plain_tail in {"", "please"}
        and re.search(r"(?:find|calculate|compute|determine)\s+(?:the\s+)?distance\b", prefix)
    ):
        requested = "distance"
    elif time_question is not None or (
        plain_tail in {"", "please"}
        and re.search(r"(?:find|calculate|compute|determine)\s+(?:the\s+)?time\b", prefix)
    ):
        requested = "time"
    if requested is None:
        return None

    distance = next((measure for measure in measures if measure[0] == "distance"), None)
    duration = next((measure for measure in measures if measure[0] == "time"), None)
    speed = next((measure for measure in measures if measure[0] == "speed"), None)
    if requested == "speed":
        if distance is None or duration is None or speed is not None:
            return None
        if distance[1] < 0 or duration[1] <= 0:
            return None
        return PhysicsIntent(
            kind="kinematics",
            physics_op="average_speed" if "average" in lower else "rate_speed",
            physics_params={"d": distance[1], "t": duration[1]},
            physics_units={"d": distance[2], "t": duration[2]},
        )
    if speed is None or speed[1] < 0:
        return None
    if requested == "distance":
        if duration is None or distance is not None or duration[1] < 0 or speed[3] != duration[2]:
            return None
        return PhysicsIntent(
            kind="kinematics",
            physics_op="rate_distance",
            physics_params={"v": speed[1], "t": duration[1]},
            physics_units={"v": f"{speed[2]}/{speed[3]}", "t": duration[2]},
        )
    if distance is None or duration is not None or speed[1] == 0 or speed[2] != distance[2]:
        return None
    return PhysicsIntent(
        kind="kinematics",
        physics_op="rate_time",
        physics_params={"d": distance[1], "v": speed[1]},
        physics_units={"d": distance[2], "v": f"{speed[2]}/{speed[3]}"},
    )
