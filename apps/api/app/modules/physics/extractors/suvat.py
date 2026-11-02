"""Constant acceleration in a straight line (SUVAT) for any one unknown."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.modules.physics.ask import ask_clause, asked_phrases
from app.modules.physics.catalog.suvat import TWO_BODIES
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.words import word_pattern
from app.services.text_match import has_equation

_SUVAT_CUES: tuple[str, ...] = ()

_SUVAT_CUE_RES: tuple[re.Pattern[str], ...] = (
    # "accelerates ... at 3 m/s^2", and the same reading written backwards.
    re.compile(r"\b(?:ac|de)celerat\w*\b.{0,60}?\d\s*m/s\^?2", re.IGNORECASE),
    re.compile(r"\d\s*m/s\^?2.{0,60}?\b(?:ac|de)celerat\w*\b", re.IGNORECASE),
    # A rest state at one end and a speed at the other: "from rest ... 20 m/s",
    # "12 m/s to rest". This is the shape that carries no acceleration at all
    # (s = ½(u+v)t), so it cannot be found by looking for m/s².
    re.compile(r"\b(?:from|at)\s+rest\b.{0,80}?\d\s*(?:m/s|km/h|mph)\b", re.IGNORECASE),
    re.compile(
        r"\d\s*(?:m/s|km/h|mph)\b.{0,80}?\bto\s+(?:rest|a\s+(?:stop|halt))\b", re.IGNORECASE
    ),
    re.compile(r"\b(?:constant|uniform)\s+(?:ac|de)celeration\b", re.IGNORECASE),
    re.compile(r"\bslows?\b.{0,80}?\d\s*m/s\^?2", re.IGNORECASE),
    re.compile(
        r"\d\s*(?:m/s|km/h|mph)\b.{0,80}?\d\s*(?:m/s|km/h|mph)\b"
        r".{0,80}?\d\s*(?:seconds?|secs?|sec|s)\b.{0,80}?\bacceleration\b",
        re.IGNORECASE,
    ),
)

_AT_REST_START_RE = re.compile(
    r"\b(?:from|at|starts?\s+(?:from|at)|starting\s+(?:from|at)|initially\s+at)\s+rest\b",
    re.IGNORECASE,
)

# A lone speed the question says it ends at: "accelerates ... and reaches 18 m/s".
# That is v, and a question for v that states it has nothing left to solve.
_FINAL_SPEED_RE = re.compile(
    r"\b(?:reach(?:es|ed|ing)?|final\s+(?:speed|velocity)(?:\s+(?:of|is))?|up\s+to|until\s+it\s+reaches)"
    rf"\s+(?:a\s+(?:speed|velocity)\s+of\s+)?{NUMBER}\s*(?:{VELOCITY_UNIT_PATTERN})",
    re.IGNORECASE,
)

_AT_REST_END_RE = re.compile(
    r"\bto\s+(?:rest|a\s+(?:stop|halt))\b|\b(?:stops?|stopping|halts?)\b"
    r"|\bcomes?\s+to\s+(?:rest|a\s+(?:stop|halt))\b",
    re.IGNORECASE,
)

_DECELERATION_RE = re.compile(r"\bdecelerat\w*\b|\bslow(?:s|ing|ed)?\s+down\b", re.IGNORECASE)

_SUVAT_TIME_UNITS = r"seconds?|secs?|sec|s|minutes?|mins?|min|hours?|hrs?|hr|h"

_PHRASE_OP = {
    "distance": "suvat_distance",
    "displacement": "suvat_distance",
    "how far": "suvat_distance",
    "length": "suvat_distance",
    "velocity": "suvat_velocity",
    "speed": "suvat_velocity",
    "how fast": "suvat_velocity",
    "acceleration": "suvat_acceleration",
    "deceleration": "suvat_acceleration",
    "time": "suvat_time",
    "how long": "suvat_time",
    "how much time": "suvat_time",
    "time taken": "suvat_time",
    "stopping time": "suvat_time",
}
_WANTED = {
    "suvat_velocity": "v",
    "suvat_distance": "d",
    "suvat_time": "t",
    "suvat_acceleration": "a",
}
# The input sets each operation can solve. A multipart question is verified only
# when every asked unknown is one of these and the remaining givens cover it.
_DETERMINED: dict[str, tuple[frozenset[str], ...]] = {
    "suvat_velocity": (frozenset("uat"), frozenset("uad"), frozenset("udt")),
    "suvat_distance": (
        frozenset("uat"),
        frozenset("uva"),
        frozenset("uvt"),
        frozenset("vat"),
    ),
    "suvat_time": (frozenset("uva"), frozenset("uad"), frozenset("uvd")),
    "suvat_acceleration": (frozenset("uvt"), frozenset("uvd"), frozenset("udt")),
}


def _listed_unknowns(phrases: Sequence[str]) -> list[str] | None:
    """The SUVAT unknowns named together.

    None means another topic is in the list, so the whole question stays
    unverified. An empty list means the phrases are not SUVAT nouns and the
    older wording patterns still apply.
    """
    ops: list[str] = []
    foreign = False
    for phrase in phrases:
        op = _PHRASE_OP.get(phrase)
        if op is None:
            foreign = True
            continue
        if op not in ops:
            ops.append(op)
    if foreign:
        return None if ops else []
    return ops


def _determined(op: str, params: dict[str, float]) -> bool:
    known = set(params)
    return any(need <= known for need in _DETERMINED[op])


_SUVAT_UNKNOWN_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "suvat_distance",
        re.compile(
            r"\bdisplacement\b|\bhow far\b|\bwhat distance\b"
            r"|\bdistance (?:does|do|is|will|travel|cover)"
            r"|\bdistance travell?ed\b|\bhow much (?:distance|ground)\b|\bfind the distance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "suvat_velocity",
        re.compile(
            r"\bfinal (?:velocity|speed)\b|\bhow fast\b|\bwhat (?:is its |is the )?"
            r"(?:velocity|speed)\b|\bfind the (?:velocity|speed)\b|\bspeed (?:does|will|is)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "suvat_acceleration",
        re.compile(
            r"\bwhat (?:is the |was the )?(?:ac|de)celeration\b|\bfind the (?:ac|de)celeration\b"
            r"|\bhow (?:quickly|rapidly) (?:does|did) it (?:ac|de)celerate\b",
            re.IGNORECASE,
        ),
    ),
    (
        "suvat_time",
        re.compile(
            r"\bhow long\b|\bhow much time\b|\bwhat time\b|\bfind the time\b"
            r"|\btime (?:does|will|is) it take\b|\bstopping time\b|\btime to stop\b",
            re.IGNORECASE,
        ),
    ),
)


def _extract_suvat_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _SUVAT_CUES, _SUVAT_CUE_RES):
        return None
    # Two moving bodies' speeds are not one body's u and v.
    if any(word_pattern(phrase).search(lower) for phrase in TWO_BODIES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    clause = ask_clause(cleaned)
    if clause is None:
        return None
    # A stated displacement/final speed is a given, not an unknown. Read the
    # first requested noun before the fallback phrasings ("how far/long/fast").
    phrases = asked_phrases(cleaned)
    listed = _listed_unknowns(phrases) if phrases else []
    if listed is None:
        return None
    unknown = listed[0] if listed else None
    if unknown is None:
        matches = [
            (match.start(), op)
            for op, rx in _SUVAT_UNKNOWN_RES
            if (match := rx.search("find " + clause)) is not None
        ]
        unknown = min(matches)[1] if matches else None
    if unknown is None:
        return None

    params: dict[str, float] = {}
    units: dict[str, str] = {}

    # --- the two velocities, bound by written order -------------------------
    # "from 10 m/s to 30 m/s" reads left to right; a stated rest state at
    # either end fills the slot that has no number of its own.
    velocities = ordered_values(cleaned, VELOCITY_UNIT_PATTERN)
    if (
        len(velocities) > 1
        and re.search(r"\b(?:from|initial(?:ly)?)\b", cleaned, re.IGNORECASE) is None
    ):
        # Written order alone cannot identify which of two unlabeled speeds
        # came first ("has speeds 10 m/s and 30 m/s").
        return None
    starts_at_rest = _AT_REST_START_RE.search(cleaned) is not None
    ends_at_rest = _AT_REST_END_RE.search(cleaned) is not None

    if starts_at_rest:
        params["u"], units["u"] = 0.0, "m/s"
        if velocities:
            params["v"], units["v"] = velocities[0]
    elif ends_at_rest:
        params["v"], units["v"] = 0.0, "m/s"
        if velocities:
            params["u"], units["u"] = velocities[0]
    elif len(velocities) == 1 and _FINAL_SPEED_RE.search(cleaned):
        params["v"], units["v"] = velocities[0]
    elif velocities:
        params["u"], units["u"] = velocities[0]
        if len(velocities) > 1:
            params["v"], units["v"] = velocities[1]

    # --- acceleration -------------------------------------------------------
    # "decelerates at 4 m/s^2" states a magnitude and a direction separately;
    # the sign lives in the word, not the number.
    accel = find_value_with_specific_unit(
        cleaned,
        r"m/s\^?2|m/s2",
        ("acceleration", "accelerates", "accelerating", "deceleration", "decelerates", "rate"),
    )
    if accel is not None:
        value, unit = accel
        if _DECELERATION_RE.search(cleaned) and value > 0:
            value = -value
        params["a"], units["a"] = value, unit or "m/s^2"

    # --- time and distance --------------------------------------------------
    times = ordered_values(cleaned, _SUVAT_TIME_UNITS)
    if times:
        params["t"], units["t"] = times[0]
    distances = ordered_values(cleaned, LENGTH_UNIT_PATTERN)
    if distances:
        params["d"], units["d"] = distances[0]

    # The unknown must not also be a given, and three of the other four are
    # needed to reach it — every SUVAT equation relates exactly four variables.
    if listed and len(listed) > 1:
        for op in listed:
            params.pop(_WANTED[op], None)
            units.pop(_WANTED[op], None)
        if len(listed) > 4 or any(not _determined(op, params) for op in listed):
            return None
        return PhysicsIntent(
            kind="suvat",
            physics_op=listed[0],
            physics_params=params,
            physics_units=units,
            operation="solve",
            # The ids are catalog strings; the model validates each one.
            requested_ops=listed,  # type: ignore[arg-type]
        )

    wanted = _WANTED[unknown]
    params.pop(wanted, None)
    units.pop(wanted, None)
    if len(params) < 3:
        return None

    return PhysicsIntent(
        kind="suvat",
        physics_op=unknown,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
