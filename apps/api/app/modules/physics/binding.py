"""Read a question straight into a physics catalog operation, from its givens and its ask.

The extractors are written for the phrasings they know. Many questions just
state a law's inputs and ask for its result in words the catalog can list:
"accelerates from 10 m/s to 30 m/s in 5 s. Find its acceleration." The binder
reads the asked clause (``ask``), finds every operation whose ``Binding`` names
that ask, and fills each from the stated values with the shared engine
(``services.law_binding.fit``), with physics' settings for an unstated input
(g, the named planet's mass).

Anything short of one operation with one way to fill it declines: two
operations fit, a value has no input, an input could take either of two
values, or the ask names nothing the catalog lists. It runs after the
extractors, so it only answers questions they declined.
"""

from __future__ import annotations

import re
from functools import lru_cache

from app.modules.physics.ask import ask_clause, asked_dimensions, asked_unit
from app.modules.physics.binding_values import fallback_value, si_unit
from app.modules.physics.bodies import names_only_water
from app.modules.physics.catalog import CATALOG, WATER_ONLY
from app.modules.physics.givens import FRACTION_OF_C, PHYSICS_UNITS, unit_expression
from app.modules.physics.optic_elements import diverging_element, signed_distances
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.fit import (
    Subject,
    named_strength,
    only_strongest_fit,
    read_question,
)
from app.services.law_binding.model_read import excluded
from app.services.law_binding.spec import FormulaSpec
from app.services.law_binding.units import dimension_of

# Reading a paste full of numbers would cost every chat turn.
_MAX_GIVENS = 16
# A second request in the same message ("... and tell me a joke") is not a
# question the verified answer finishes.
_SECOND_REQUEST = re.compile(
    r"\b(?:and|also|then)\s+(?:also\s+)?"
    r"(?:tell|explain|show|write|give|convert|calculate|compute|solve|draw|plot|describe)\b",
    re.IGNORECASE,
)
# "Calculate his average speed and write the correct unit of speed" (a Class 8 book,
# 2026-10-30): the unit is part of the answer the card gives, not a second request.
_UNIT_REQUEST = re.compile(
    r",?\s+(?:and|also|then)\s+(?:also\s+)?(?:write|give|state|mention|name)\s+(?:down\s+)?"
    r"(?:(?:the|its|his|her|their)\s+)?(?:(?:correct|proper|right|appropriate|SI|S\.I\.)\s+)?"
    r"units?(?:\s+of\s+(?:the\s+)?[a-z]+(?:\s+[a-z]+)?)?(?=\s*[.?!]|\s*$)",
    re.IGNORECASE,
)
_PHYSICS = Subject(units=PHYSICS_UNITS, fallback=fallback_value, unit_of=si_unit)
_NORTH_SOUTH = re.compile(r"\b(?:north|south)(?:wards?|bound|erly)?\b")
_EAST_WEST = re.compile(r"\b(?:east|west)(?:wards?|bound|erly)?\b")
# A direction between the axes, a bearing or a stated angle is not a right angle.
_NOT_ALONG_AN_AXIS = re.compile(
    r"\b(?:north|south)[\s-]*(?:east|west)|\bbearing\b|\d\s*(?:°|degrees?\b|deg\b)"
)


def crosswise(lower: str) -> bool:
    """One direction on each compass axis and nothing between them: north and east."""
    return (
        _NORTH_SOUTH.search(lower) is not None
        and _EAST_WEST.search(lower) is not None
        and _NOT_ALONG_AN_AXIS.search(lower) is None
    )


def bind_physics_intent(text: str) -> PhysicsIntent | None:
    """The one catalog operation this question states and asks for, or None.

    The word checks run first, so text that names no operation's ask costs a
    few regex searches and never reads units. Detection calls this on every
    chat turn.
    """
    text = _UNIT_REQUEST.sub("", text)
    clause = ask_clause(text)
    if clause is None or _SECOND_REQUEST.search(text):
        return None
    lower = text.lower()
    # "0.8c" is a speed of light: the phrase relativity's cues are written as.
    cue_text = f"{lower} speed of light" if FRACTION_OF_C.search(lower) else lower
    # "flies due north … a wind blows from west to east": one direction on each
    # compass axis is a right angle, the cue the perpendicular laws are written with.
    if crosswise(lower):
        cue_text = f"{cue_text} crosswise"
    only_water = names_only_water(lower)
    # "The mirror is convex": a law that excludes a diverging element excludes it, however
    # the question words it.
    excluded = _with_markers(lower)
    named = [
        (spec, spec, strength)
        for spec in _bindable()
        if spec.binding is not None
        and (only_water or spec.id not in WATER_ONLY)
        and (
            strength := named_strength(
                spec.binding, clause, excluded, PHYSICS_UNITS, cue_text=cue_text
            )
        )
    ]
    if not named:
        return None
    unit = asked_unit(text)
    question = read_question(
        text,
        clause,
        PHYSICS_UNITS,
        max_givens=_MAX_GIVENS,
        asked=frozenset(asked_dimensions(text)),
        asked_in=dimension_of(unit_expression(unit) or "") if unit else None,
    )
    if question is None:
        return None
    strongest = only_strongest_fit(named, question, _PHYSICS)
    if strongest is None:
        return None
    _, chosen = strongest
    try:
        return PhysicsIntent(
            # The catalog's kind is a str; the model validates it against its Literal.
            kind=chosen.spec.kind,  # type: ignore[arg-type]
            physics_op=chosen.spec.id,
            physics_params=chosen.params,
            physics_units=chosen.units,
        )
    except ValueError:
        return None


def _with_markers(lower: str) -> str:
    """The question as the excludes read it: a convex mirror or a concave lens, however it
    is worded, is marked "diverging", and a distance given its sign is marked "signed"."""
    if signed_distances(lower):
        lower = f"{lower} signed"
    return f"{lower} diverging" if diverging_element(lower) else lower


def ruled_out(spec: FormulaSpec, text: str) -> bool:
    """The question's own words rule this law out, as the binder reads them: more than
    water named for a law about water alone, or a word its binding excludes."""
    lower = text.lower()
    if spec.id in WATER_ONLY and not names_only_water(lower):
        return True
    return excluded(spec.binding, _with_markers(lower))


@lru_cache(maxsize=1)
def _bindable() -> tuple[FormulaSpec, ...]:
    return tuple(spec for spec in CATALOG.values() if spec.binding is not None)
