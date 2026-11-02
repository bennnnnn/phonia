"""Physics as a model reads it: the menu it chooses from, and the intent its read binds to.

A read is a catalog id and the values the question states. It becomes an intent only
through the physics binder (``binding.bind_physics_intent``), which must read the read's
own English back to the same law and values; anything else is no read.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from app.modules.physics.binding import bind_physics_intent, ruled_out
from app.modules.physics.catalog import CATALOG
from app.modules.physics.givens import PHYSICS_UNITS
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.model_read import (
    OpCard,
    Stated,
    op_card,
    renderings,
    same_values,
    written,
)


@lru_cache(maxsize=1)
def physics_menu() -> dict[str, tuple[OpCard, ...]]:
    """Every law a question can bind to, by its kind ("kinematics", "optics")."""
    menu: dict[str, list[OpCard]] = {}
    for spec in CATALOG.values():
        card = op_card(spec)
        if card is not None:
            menu.setdefault(card.kind, []).append(card)
    return {kind: tuple(cards) for kind, cards in menu.items()}


def physics_read_intent(
    op: str, stated: Sequence[Stated], message: str = ""
) -> PhysicsIntent | None:
    """The intent a model's read of ``op`` binds to, or None when the binder reads it
    differently (another law, another value, nothing) or the ``message`` itself rules
    the law out, as it would for the binder (water mixed with alcohol, a word the law
    excludes)."""
    spec = CATALOG.get(op)
    if spec is None or spec.binding is None or (message and ruled_out(spec, message)):
        return None
    variables = {variable.name: variable for variable in spec.variables if variable.visible}
    values: dict[str, tuple[float, str]] = {}
    for item in stated:
        variable = variables.get(item.name)
        found = None if variable is None else written(item, variable, PHYSICS_UNITS, message)
        if found is None or item.name in values:
            return None
        values[item.name] = found
    for text in renderings(spec, values):
        intent = bind_physics_intent(text)
        if (
            intent is not None
            and intent.physics_op == op
            and same_values(intent.physics_params or {}, values, PHYSICS_UNITS, spec)
        ):
            return intent
    return None
