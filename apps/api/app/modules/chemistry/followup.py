"""Replay the previous chemistry problem when this line only continues it.

Each shape declines instead of guessing: explain the result, ask for another
quantity of the same setup ("and the pOH?"), or replace or scale one given
("and 0.001 M?", "what if the concentration doubles?"). A reaction problem also
takes an amount or an ask of one of its substances ("what if i only had 16g of
o2", "and how much o2 do i need": ``reaction_followup.py``), and a line that
only asks to see the molecules of a shape answer draws them again
(``shape_followup.py``: "can u show me both"). A new
question that brings its own data is not a follow-up. Exact phrases such as
``why`` and ``explain`` stay on the shared continuation list; this resolver
is the line that is not one of those phrases.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.given_units import CHEMISTRY_UNITS
from app.modules.chemistry.reaction_followup import reaction_followup_problem, substance_amount
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.shape_followup import shape_followup_problem
from app.modules.chemistry.species_words import substance_mentions, with_formulas
from app.services.law_binding.units import dimension_of
from app.services.problem_followup import (
    EXPLAIN_RE,
    GivenRewriter,
    adjacent_problem,
    ask_replaced,
    followup_line,
    new_value,
    scaled_given,
)

CHEMISTRY_FOLLOWUP_HINT = (
    "This short request continues the immediately preceding chemistry problem. "
    "Explain that verified result: why the formula applies and how the numbers "
    "produce it. Do not start a new problem. Copy the verified numbers; do not "
    "recompute them. When the request changes one given or asks for a different "
    "quantity, the verified block is that new result."
)

# The asked word as the catalog writes it. A rewrite is accepted only when the
# verified find or answer names this word, so an extractor that ignores the ask
# cannot verify the previous law.
_ASKS = {
    "ph": "pH",
    "poh": "pOH",
    "pka": "pKa",
    "pkb": "pKb",
    "ka": "Ka",
    "kb": "Kb",
    "molar mass": "molar mass",
    "density": "density",
    "molality": "molality",
    "percent ionization": "percent ionization",
    "equilibrium constant": "equilibrium constant",
    "enthalpy": "enthalpy",
    "absorbance": "absorbance",
    "ionic strength": "ionic strength",
    "optical purity": "optical purity",
    "partition coefficient": "partition coefficient",
    "heat": "heat",
}
_NAMED_DIMENSIONS = {
    "concentration": "mole / liter",
    "molarity": "mole / liter",
    "mass": "gram",
    "volume": "liter",
    "temperature": "kelvin",
    "pressure": "atmosphere",
    "molality": "mole / kilogram",
}
_ABOUT = re.compile(
    r"^(?:(?:and )?(?:what|how) about |and |now )(?:the |its )?(?P<ask>[a-z][a-z' ]{0,40}?)\??$"
)
_CHANGED = re.compile(
    r"^(?:but )?(?:what )?if "
    r"(?:it (?:was|were|is) |"
    r"(?:the )?(?P<name>[A-Za-z][A-Za-z ]{0,30}?) (?:was|were|is) )"
    r"(?P<value>[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:e[-+]?\d+)?) ?"
    r"(?P<unit>[A-Za-zμµ°/^0-9][A-Za-zμµ°/^0-9. ]{0,16})?\??$",
    re.IGNORECASE,
)


def chemistry_followup_problem(query: str | None, recent: Sequence[Any]) -> str | None:
    """The problem to verify again, or None when this line is not that follow-up."""
    text = followup_line(query)
    if text is None or extract_chemistry_intent(text) is not None:
        return None
    # "can u show me both" after a shape answer: its molecules are drawn again.
    shown = shape_followup_problem(text, recent)
    if shown is not None and _verifies(shown):
        return shown
    prior = adjacent_problem(recent, is_chemistry_question)
    adjacent = None if prior is None else _adjacent_problem(prior, text)
    if adjacent is not None:
        return adjacent
    # "what if i only had 16g of o2" changes the reaction it names, past lines with no amount.
    reaction = reaction_followup_problem(text, recent)
    return reaction if reaction is not None and _verifies(reaction) else None


def _adjacent_problem(prior: str, text: str) -> str | None:
    """The last exchange's problem, explained again or with one thing changed."""
    folded = text.lower()
    if EXPLAIN_RE.fullmatch(folded):
        return prior
    about = _ABOUT.fullmatch(folded)
    if about is not None:
        return _another_quantity(prior, about.group("ask"))
    changed = _CHANGED.fullmatch(text)
    if changed is not None:
        rewritten = _GIVENS.changed(
            prior, changed.group("name"), changed.group("value"), changed.group("unit")
        )
        if rewritten is not None:
            return rewritten
    scaled = scaled_given(text)
    if scaled is not None:
        return _GIVENS.scaled(prior, *scaled)
    value = new_value(text)
    if value is not None:
        return _GIVENS.changed(prior, None, *value)
    return _amount_of_its_substance(prior, text)


def _amount_of_its_substance(prior: str, text: str) -> str | None:
    """ "what about 20 g of H2" after "How many moles are in 10 g of H2?": the one given of
    that kind, when the problem states it of the same substance."""
    amount = substance_amount(text)
    if amount is None:
        return None
    value, unit, formula = amount
    stated = substance_mentions(prior)
    written = with_formulas(prior, stated) if stated else prior
    of_it = rf"\d\s*(?:g|grams?|mol|moles?)\s+(?:of\s+)?(?-i:{re.escape(formula)})(?![A-Za-z0-9])"
    if re.search(of_it, written, re.IGNORECASE) is None:
        return None
    return _GIVENS.changed(prior, None, value, unit)


def _another_quantity(prior: str, ask: str) -> str | None:
    phrase = " ".join(ask.split())
    written = _ASKS.get(phrase)
    if written is None:
        return None
    rewritten = ask_replaced(prior, written)
    return rewritten if _verifies(rewritten, ask=written) else None


def _verifies(text: str, *, ask: str | None = None) -> bool:
    """True when one operation answers this wording, including the asked word."""
    intent = extract_chemistry_intent(text)
    if intent is None:
        return False
    from app.modules.chemistry.block import build_verified_chemistry

    verified = build_verified_chemistry(intent)
    if verified is None:
        return False
    if ask is None:
        return True
    haystack = f"{verified.result.find} {verified.result.answer}".lower()
    return re.search(rf"(?<![a-z0-9]){re.escape(ask.lower())}(?![a-z0-9])", haystack) is not None


def _dimension_of_unit(unit: str) -> str | None:
    return dimension_of(CHEMISTRY_UNITS.expression(unit) or "")


def _dimension_of_phrase(phrase: str) -> str | None:
    """A quantity named in any case ("the Concentration") by its dimension."""
    expression = _NAMED_DIMENSIONS.get(phrase.lower())
    return None if expression is None else dimension_of(expression)


_GIVENS = GivenRewriter(CHEMISTRY_UNITS, _dimension_of_unit, _dimension_of_phrase, _verifies)
