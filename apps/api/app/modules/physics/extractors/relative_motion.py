"""Two bodies or two legs whose roles the words set: a chase, and a walk at right angles.

"A car at 30 m/s is chasing a truck doing 20 m/s that is 100 m ahead": the
chaser is the one that chases, so its speed is the one written before
"chasing", and the gap closes at the difference. Read by order alone, a
slower chaser would have "caught up" too. "I walk 3 km east then 4 km north":
each leg's direction is written beside it, and two legs on the two compass
axes are a right triangle, with the displacement's direction in words.

Anything else declines: a chaser slower than the one ahead, a second speed
for one body, legs on one axis or between the axes, or a third leg.
"""

from __future__ import annotations

import re

from app.modules.physics.ask import ask_clause, asked_phrases
from app.modules.physics.givens import Given, scan_givens
from app.modules.physics.schemas import PhysicsIntent

_SPEED = "[length]^1 * [time]^-1"
_LENGTH = "[length]^1"

_CHASES_RE = re.compile(
    r"\b(?:is\s+)?(?:chasing|chases|pursuing|pursues|following|follows|catching\s+up\s+(?:with|to))\b",
    re.IGNORECASE,
)
_AHEAD_RE = re.compile(r"\b(?:ahead|in\s+front|head\s+start|lead|behind|apart)\b", re.IGNORECASE)
_CATCH_ASK_RE = re.compile(
    r"\b(?:catch(?:es)?\s+up|catch\s+(?:it|him|her|them|the)|overtake|reach(?:es)?\s+(?:it|the))\b",
    re.IGNORECASE,
)
_TIME_ASKS = {"how long", "time", "time taken"}


def _values(givens: list[Given], dimension: str) -> list[Given]:
    return [given for given in givens if given.dimension == dimension]


def extract_chase_intent(cleaned: str) -> PhysicsIntent | None:
    """The time for a faster chaser to close a stated gap: t = d/(v₁ - v₂)."""
    chase = list(_CHASES_RE.finditer(cleaned))
    clause = ask_clause(cleaned)
    if len(chase) != 1 or clause is None or not _CATCH_ASK_RE.search(clause):
        return None
    phrases = asked_phrases(cleaned)
    if len(phrases) != 1 or phrases[0] not in _TIME_ASKS:
        return None
    givens = scan_givens(cleaned)
    if any(given.dimension not in {_SPEED, _LENGTH} for given in givens):
        return None
    speeds, lengths = _values(givens, _SPEED), _values(givens, _LENGTH)
    if len(speeds) != 2 or len(lengths) != 1:
        return None
    verb = chase[0]
    chaser, target = speeds
    # The chaser's speed is written before "chasing", the target's after it.
    if not (chaser.end <= verb.start() < target.start):
        return None
    gap = lengths[0]
    if not _AHEAD_RE.search(cleaned, gap.end, min(len(cleaned), gap.end + 40)):
        return None
    if chaser.si is None or target.si is None or chaser.si <= target.si:
        return None
    return PhysicsIntent(
        kind="kinematics",
        physics_op="catch_up_time",
        physics_params={"d": gap.value, "v_chaser": chaser.value, "v_target": target.value},
        physics_units={"d": gap.unit, "v_chaser": chaser.unit, "v_target": target.unit},
        operation="solve",
    )


_COMPASS = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}
_LEG_RE = re.compile(
    r"(?<![\d.])(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>km|m|miles?|mi)\s+"
    r"(?:due\s+|to\s+the\s+)?(?P<direction>north|south|east|west)(?:wards?)?\b",
    re.IGNORECASE,
)
_BETWEEN_AXES_RE = re.compile(r"\b(?:north|south)[\s-]*(?:east|west)\b", re.IGNORECASE)
_DISPLACEMENT_ASKS = {"displacement", "how far", "distance"}
# "How far is she from her starting point": the straight line, not the path.
_FROM_START_RE = re.compile(
    r"\bdisplacement\b|\bfrom\s+(?:the\s+|her\s+|his\s+|my\s+|their\s+|its\s+)?"
    r"(?:start(?:ing\s+point)?|origin|home|where\s+\w+\s+start\w*)\b|\bstraight[- ]line\b",
    re.IGNORECASE,
)


def extract_legs_intent(cleaned: str) -> PhysicsIntent | None:
    """Two legs on the two compass axes: the displacement's size and direction."""
    if _BETWEEN_AXES_RE.search(cleaned):
        return None
    clause = ask_clause(cleaned)
    phrases = asked_phrases(cleaned)
    if clause is None or len(phrases) != 1 or phrases[0] not in _DISPLACEMENT_ASKS:
        return None
    if not _FROM_START_RE.search(clause):
        return None
    legs = list(_LEG_RE.finditer(cleaned))
    givens = [given for given in scan_givens(cleaned) if given.dimension is not None]
    if len(legs) != 2 or len(givens) != 2:
        return None
    first, second = (_COMPASS[leg["direction"].lower()] for leg in legs)
    # One leg on each axis: a right angle.
    if first[0] * second[0] + first[1] * second[1] != 0:
        return None
    if legs[0]["unit"].lower() != legs[1]["unit"].lower():
        return None
    unit = legs[0]["unit"]
    return PhysicsIntent(
        kind="kinematics",
        physics_op="displacement_two_legs",
        physics_params={
            "d1": float(legs[0]["number"]),
            "d2": float(legs[1]["number"]),
            "heading1": float(list(_COMPASS).index(legs[0]["direction"].lower())),
            "heading2": float(list(_COMPASS).index(legs[1]["direction"].lower())),
        },
        physics_units={"d1": unit, "d2": unit, "heading1": "", "heading2": ""},
        operation="solve",
    )


COMPASS_NAMES = tuple(_COMPASS)
