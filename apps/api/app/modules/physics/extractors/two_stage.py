"""Two stages of straight-line motion: speed up from rest, then hold the speed or brake.

"accelerates from rest at 0.8 m/s² for 25 s, then travels at constant speed for
1 min"; "reaches her top speed of 11 m/s in 2.2 s starting from rest and holds it
to the finish"; "accelerates from rest at 2 m/s² for 10 s, then brakes at 4 m/s²
to a stop". One constant-acceleration interval cannot read these, and d = vt
would read one speed for both stages. The stages are roles, so this is a reader:
the clause before "then" speeds up from rest, the clause after holds the speed or
brakes to a stop, and each stated value belongs to the clause it is written in.

Only the whole trip is answered: its total distance, or its total time. A
question about one stage ("how far does it go while braking?"), a value in the
wrong stage, a stage this does not read, or a stated start speed declines.
"""

from __future__ import annotations

import re

from app.modules.physics.ask import ask_clause, asked_phrases
from app.modules.physics.givens import Given, scan_givens
from app.modules.physics.schemas import PhysicsIntent

_ACCELERATION = "[length]^1 * [time]^-2"
_SPEED = "[length]^1 * [time]^-1"
_TIME = "[time]^1"
_LENGTH = "[length]^1"

# Where the second stage starts: "…, then", "and then", "and holds it", "after which".
_SECOND_STAGE_RE = re.compile(
    r",?\s*\b(?:and\s+)?then\b"
    r"|\s+and\s+(?=(?:holds?|maintains?|keeps?|continues?|cruises?|travels?|moves?|runs?"
    r"|drives?|brakes?|decelerates?|slows?)\b)"
    r"|,?\s*\bafter\s+which\b",
    re.IGNORECASE,
)
_FROM_REST_RE = re.compile(
    r"\bfrom\s+(?:rest|a\s+standstill|standstill|a\s+standing\s+start|a\s+stop)\b"
    r"|\bstarts?\s+at\s+rest\b",
    re.IGNORECASE,
)
_SPEEDS_UP_RE = re.compile(
    r"\baccelerat\w*|\bspeeds?\s+up\b|\breach(?:es|ed)?\b|\bpicks?\s+up\b|\bgets?\s+up\s+to\b",
    re.IGNORECASE,
)
_SLOWS_RE = re.compile(r"\bbrak\w*|\bdecelerat\w*|\bslows?\b|\bretard\w*", re.IGNORECASE)
_STOPS_RE = re.compile(
    r"\bto\s+(?:a\s+)?(?:stop|rest|halt|standstill)\b|\bstops\b|\buntil\s+it\s+(?:stops|halts)\b",
    re.IGNORECASE,
)
_HOLDS_RE = re.compile(
    r"\b(?:constant|steady|uniform|same|that|this|top)\s+(?:speed|velocity|rate)\b"
    r"|\b(?:holds?|maintains?|keeps?|cruises?)\b",
    re.IGNORECASE,
)
# A question about one stage, or about a speed, is not the whole trip's.
_ONE_STAGE_RE = re.compile(
    r"\b(?:while|during|first|second|last|before|after|when|until|braking|accelerat\w*"
    r"|speeding|cruising|stage|part|phase|leg|top\s+speed|maximum|max|average)\b",
    re.IGNORECASE,
)
_DISTANCE_ASKS = {"distance", "how far", "how much distance"}
_TIME_ASKS = {"how long", "time", "time taken"}


def whole_trip_of_two_stages(cleaned: str) -> bool:
    """A trip in two stages, asked about as a whole: no one-interval law answers it.

    "Accelerates from rest at 1 m/s² for 20 s, then travels at constant speed.
    Total distance?" read as one interval was 200 m, the first stage alone. A
    question about one stage ("while braking", "in the first 10 s") is that
    stage's, and stays with the laws that read one interval.
    """
    stages = list(_SECOND_STAGE_RE.finditer(cleaned))
    if len(stages) != 1:
        return False
    clause = ask_clause(cleaned)
    if clause is None or _ONE_STAGE_RE.search(clause):
        return False
    ask_start = cleaned.rfind(clause)
    split = stages[0]
    if ask_start < split.end():
        return False
    first, second = cleaned[: split.start()], cleaned[split.end() : ask_start]
    return bool(
        _SPEEDS_UP_RE.search(first) and (_SLOWS_RE.search(second) or _HOLDS_RE.search(second))
    )


def _values(givens: list[Given], start: int, end: int) -> dict[str, list[Given]]:
    found: dict[str, list[Given]] = {}
    for given in givens:
        if start <= given.start < end and given.dimension is not None:
            found.setdefault(given.dimension, []).append(given)
    return found


def _one(values: dict[str, list[Given]], dimension: str) -> Given | None:
    found = values.get(dimension, [])
    return found[0] if len(found) == 1 else None


def extract_two_stage_intent(cleaned: str) -> PhysicsIntent | None:
    """The total distance or time of a trip that speeds up from rest, then holds or brakes."""
    stages = list(_SECOND_STAGE_RE.finditer(cleaned))
    if len(stages) != 1:
        return None
    clause = ask_clause(cleaned)
    phrases = asked_phrases(cleaned)
    if clause is None or len(phrases) != 1 or _ONE_STAGE_RE.search(clause):
        return None
    if phrases[0] in _DISTANCE_ASKS:
        asks_time = False
    elif phrases[0] in _TIME_ASKS:
        asks_time = True
    else:
        return None
    ask_start = cleaned.rfind(clause)
    split = stages[0]
    if ask_start < split.end():
        return None
    first, second = cleaned[: split.start()], cleaned[split.end() : ask_start]
    if not _FROM_REST_RE.search(first) or not _SPEEDS_UP_RE.search(first):
        return None
    if _SLOWS_RE.search(first):
        return None
    givens = scan_givens(cleaned)
    # Every number is a measure of its stage: a bare count or a stray value
    # is one this reading would leave out.
    if any(given.dimension is None for given in givens):
        return None
    motion = {_ACCELERATION, _SPEED, _TIME, _LENGTH}
    stage_one = _values(givens, 0, split.start())
    stage_two = _values(givens, split.end(), ask_start)
    asked = _values(givens, ask_start, len(cleaned))
    counted = sum(
        len(found)
        for part in (stage_one, stage_two, asked)
        for dimension, found in part.items()
        if dimension in motion
    )
    if counted != sum(1 for given in givens if given.dimension in motion):
        return None

    params: dict[str, float] = {}
    units: dict[str, str] = {}

    def take(name: str, given: Given | None) -> None:
        if given is not None:
            params[name] = given.value
            units[name] = given.unit

    # Stage one: two of the acceleration, its time and the speed it reaches.
    if any(len(found) > 1 for found in stage_one.values()) or _LENGTH in stage_one:
        return None
    take("a1", _one(stage_one, _ACCELERATION))
    take("t1", _one(stage_one, _TIME))
    take("v_top", _one(stage_one, _SPEED))
    if len(params) != 2:
        return None

    # Stage two: brake to a stop, or hold the speed.
    if _SPEED in stage_two or _LENGTH in stage_two:
        return None
    if any(len(found) > 1 for found in stage_two.values()):
        return None
    if _SLOWS_RE.search(second):
        if not _STOPS_RE.search(second) or asked:
            return None
        take("a_brake", _one(stage_two, _ACCELERATION))
        take("t_brake", _one(stage_two, _TIME))
        if ("a_brake" in params) == ("t_brake" in params):
            return None
    elif _HOLDS_RE.search(second):
        if _ACCELERATION in stage_two:
            return None
        take("t_cruise", _one(stage_two, _TIME))
        if "t_cruise" not in params:
            # Held to the end of a stated distance: only the time to cover it is asked.
            distance = _one(asked, _LENGTH)
            if not asks_time or distance is None or len(asked) != 1:
                return None
            take("d_total", distance)
        elif asked:
            return None
    else:
        return None
    if any(value <= 0 for value in params.values()):
        return None
    return PhysicsIntent(
        kind="kinematics",
        physics_op="two_stage_time" if asks_time else "two_stage_distance",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
