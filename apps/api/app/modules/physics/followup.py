"""Replay the previous physics problem when this line only continues it.

Each shape declines instead of guessing: explain the result, ask for another
quantity of the same setup ("how far does it go?"), give the result in another
unit, or replace or scale one given ("and after 10 s?", "what if the mass
doubles?"). A rewrite counts only when it verifies. A new question that brings
its own data is not a follow-up.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.physics.ask_words import _DIMENSIONLESS, _MONEY, _QUANTITIES
from app.modules.physics.extract import extract_physics_intent, needs_physics
from app.modules.physics.givens import ANGLE, PHYSICS_UNITS
from app.services.law_binding.units import unit_dimension
from app.services.problem_followup import (
    EXPLAIN_RE,
    GivenRewriter,
    adjacent_problem,
    ask_replaced,
    asked_unit,
    followup_line,
    in_unit,
    new_value,
    scaled_given,
)

PHYSICS_FOLLOWUP_HINT = (
    "This short request continues the immediately preceding physics problem. "
    "When the request changes one given or asks for a different quantity, the "
    "verified block is that new result: present it in the usual layout with the "
    "changed given under Given, and never compare it with or comment on the earlier "
    "answer. When it asks why or how, explain the verified result: why the formula "
    "applies and how the numbers produce it. Do not start a new problem. Copy the "
    "verified numbers; do not recompute them."
)

_ABOUT = re.compile(r"^(?:and )?what about (?:the |its )?(?P<ask>[a-z][a-z ]{0,40}?)\??$")
_CHANGED = re.compile(
    r"^(?:but )?(?:what )?if "
    r"(?:it (?:was|were|is) |"
    r"(?:the )?(?P<name>[a-z][a-z ]{0,30}?) (?:was|were|is) )"
    r"(?P<value>[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?) ?"
    r"(?P<unit>[a-zμµ°/^0-9][a-zμµ°/^0-9. ]{0,16})?\??$"
)
# "how far does it go?" asks another quantity of the same setup.
_HOW = re.compile(
    r"^(?:(?:and|so|ok(?:ay)?|now|then)[ ,]+)?how (?P<word>far|long|high|fast) "
    r"(?:does|did|will|would|is|was|can) (?:it|she|he|they|the [a-z]+) "
    r"(?:go|travel|get|take|fall|rise|climb|move|moving|going|travelling|traveling"
    r"|stay in the air|be in the air)"
    r"(?: (?:for|in total|altogether|(?:in|during|over) (?:that|this|the same) time"
    r"|before (?:it )?(?:stops|lands|hits the ground)))?$"
)
_HOW_QUANTITY = {"far": "distance", "long": "time", "high": "maximum height", "fast": "speed"}


def physics_followup_problem(query: str | None, recent: Sequence[Any]) -> str | None:
    """The problem to verify again, or None when this line is not that follow-up."""
    written = followup_line(query)
    prior = adjacent_problem(recent, needs_physics)
    if written is None or prior is None:
        return None
    line = written.lower()
    if extract_physics_intent(line) is not None:
        return None
    if EXPLAIN_RE.fullmatch(line):
        return prior
    about = _ABOUT.fullmatch(line)
    if about is not None:
        return _another_quantity(prior, about.group("ask"))
    changed = _CHANGED.fullmatch(line)
    if changed is not None:
        return _GIVENS.changed(
            prior, changed.group("name"), changed.group("value"), changed.group("unit")
        )
    how = _HOW.fullmatch(line)
    if how is not None:
        return _another_quantity(prior, _HOW_QUANTITY[how.group("word")])
    unit = asked_unit(written)
    if unit is not None:
        return _in_unit(prior, unit)
    scaled = scaled_given(line)
    if scaled is not None:
        return _GIVENS.scaled(prior, *scaled)
    value = new_value(written)
    if value is not None:
        return _GIVENS.changed(prior, None, *value)
    return None


def _in_unit(prior: str, unit: str) -> str | None:
    """The prior result in the asked unit, when the verified card writes that unit."""
    if _dimension_of_unit(unit) is None:
        return None
    rewritten = in_unit(prior, unit)
    display = _verified_display(rewritten)
    if display is None or unit.replace(" ", "") not in display.replace(" ", ""):
        return None
    return rewritten


def _another_quantity(prior: str, ask: str) -> str | None:
    phrase = " ".join(ask.split())
    if phrase not in _QUANTITIES and phrase not in {
        "range",
        "time of flight",
        "maximum height",
        "max height",
        "impact speed",
    }:
        return None
    rewritten = ask_replaced(prior, phrase)
    return rewritten if _verifies(rewritten) else None


def _verifies(text: str) -> bool:
    """True when one operation answers this wording, including the ask guard."""
    return _verified_display(text) is not None


def _verified_display(text: str) -> str | None:
    """The verified card's answer for this wording, or None when nothing verifies it."""
    intent = extract_physics_intent(text)
    if intent is None:
        return None
    from app.core.config import get_settings
    from app.modules.physics.block import build_verified_physics_block

    block = build_verified_physics_block(intent, get_settings())
    if block is None:
        return None
    return block.display_answer or block.canonical_answer or ""


def _dimension_of_unit(unit: str) -> str | None:
    reading = unit_dimension(PHYSICS_UNITS.expression(unit) or "")
    return None if reading is None else reading[0]


def _dimension_of_phrase(phrase: str) -> str | None:
    expression = _QUANTITIES.get(phrase)
    if expression is None:
        return None
    if expression in {ANGLE, _DIMENSIONLESS, _MONEY}:
        return expression
    reading = unit_dimension(expression)
    return None if reading is None else reading[0]


_GIVENS = GivenRewriter(PHYSICS_UNITS, _dimension_of_unit, _dimension_of_phrase, _verifies)
