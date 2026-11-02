"""Chemistry as a model reads it: the laws it chooses from, and the intent its read binds to.

A read is a law's id, the values the question states and, for a law about one substance,
its formula. It becomes an intent only through the chemistry binder
(``binding.bind_chemistry_intent``), which must read the read's own English back to the
same law and values; anything else is no read.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.modules.chemistry.binding import bind_chemistry_intent, prepare
from app.modules.chemistry.given_units import CHEMISTRY_UNITS
from app.modules.chemistry.law_record import ChemistryLaw
from app.modules.chemistry.laws import LAWS
from app.modules.chemistry.request import EQUATION_RE
from app.modules.chemistry.schemas import ChemistryIntent
from app.services.law_binding.model_read import (
    OpCard,
    Stated,
    excluded,
    op_card,
    renderings,
    same_values,
    written,
)

# A formula a reader may name: element symbols, digits, brackets and charges only.
_FORMULA_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()[]+-·."
)


@lru_cache(maxsize=1)
def _laws() -> dict[str, ChemistryLaw]:
    """Each bound law by its own id: one operation may have several (by molality, by mass)."""
    return {law.spec.id: law for law in LAWS if law.spec.binding is not None}


@lru_cache(maxsize=1)
def chemistry_menu() -> dict[str, tuple[OpCard, ...]]:
    """Every law a question can bind to, by its kind ("acid_base", "solutions")."""
    menu: dict[str, list[OpCard]] = {}
    for law in _laws().values():
        card = op_card(law.spec)
        if card is not None:
            menu.setdefault(law.kind, []).append(card)
    return {kind: tuple(cards) for kind, cards in menu.items()}


def chemistry_needs_formula(op: str) -> bool:
    """The law is about one substance the question names."""
    law = _laws().get(op)
    return law is not None and law.species is not None


def _ruled_out(law: ChemistryLaw, message: str) -> bool:
    """The message's own words rule the law out, as they would for the binder: a word its
    binding excludes, or an equation for a law that reads none."""
    if law.no_equation and EQUATION_RE.search(message):
        return True
    return excluded(law.spec.binding, prepare(message).text.lower())


def chemistry_read_intent(
    op: str, stated: Sequence[Stated], formula: str | None = None, message: str = ""
) -> ChemistryIntent | None:
    """The intent a model's read of the law ``op`` (its menu id) binds to, or None when
    the binder reads it differently (another law, value or substance, or nothing) or the
    ``message`` itself rules the law out."""
    law = _laws().get(op)
    if law is None or (message and _ruled_out(law, message)):
        return None
    about = ""
    if law.species is not None:
        if not formula or not set(formula) <= _FORMULA_CHARACTERS or len(formula) > 40:
            return None
        # The substance must be the message's own: its formula or its name, as the chemistry
        # reader finds them (water is H2O), never one the model brought.
        if message and formula not in prepare(message).species:
            return None
        about = f" of {formula}"
    variables = {variable.name: variable for variable in law.spec.variables if variable.visible}
    values: dict[str, tuple[float, str]] = {}
    for item in stated:
        variable = variables.get(item.name)
        found = None if variable is None else written(item, variable, CHEMISTRY_UNITS, message)
        if found is None or item.name in values:
            return None
        values[item.name] = found
    for text in renderings(law.spec, values, about=about):
        intent = bind_chemistry_intent(text)
        if (
            intent is not None
            and intent.chemistry_op == law.op
            and (law.species is None or intent.formula == formula)
            and same_values(intent.params, values, CHEMISTRY_UNITS, law.spec)
        ):
            return intent
    return None
