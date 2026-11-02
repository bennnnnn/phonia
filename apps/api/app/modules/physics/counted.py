"""A solve reads a counted item's value once per item, or not at all.

Two 5 kg blocks weigh 98.1 N; a solve that bound one 5 kg mass answered 49.1 N, and two
heaters rated 2 kW each answered one heater's energy (2026-10-31). A value stated once for
several items (``counted_items``) is accounted for when the solve binds it as many times
as there are items (a network's R1 … Rn, Coulomb's q1 and q2) or never. A count of parts
whose values the question gives fewer than ("two resistors ... one is 10 Ω") is refused
too, unless each value given belongs to one item ("a 12 V battery has two cells").
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

from app.modules.physics.accounting import param_readings
from app.modules.physics.extractors.counted_parts import counted_items, one_item_value
from app.modules.physics.givens import Given, scan_givens
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.units import dimension_of

# The parts and the kinds their values are, so values of those kinds are theirs to count:
# "two lamps of 6 Ω" and "two heaters of 2 kW" were read as one lamp and one heater
# (2026-11-01). A lamp's value may be its resistance or its power.
_LOADS = ("ohm", "watt")
_PART_KINDS: dict[str, tuple[str, ...]] = {
    **dict.fromkeys(("resistors", "resistances", "coils", "wires"), ("ohm",)),
    **dict.fromkeys(("cells", "batteries"), ("volt",)),
    "capacitors": ("farad",),
    **dict.fromkeys(
        ("lamps", "bulbs", "heaters", "fans", "irons", "kettles", "lights", "tubes"), _LOADS
    ),
    **dict.fromkeys(("appliances", "motors", "toasters", "elements"), _LOADS),
}
# Between two numbers of one list: "2, 3 and 6 ohms".
_LIST_JOIN = re.compile(r"\s*(?:,\s*(?:and|or)?|and|or)\s*")
# "A 10 Ω resistor and two others": items whose values the question never gives.
_UNVALUED = frozenset({"others"})


def accounts_for_counted_items(intent: PhysicsIntent, text: str) -> bool:
    """Whether the solve reads every counted item's value once per item."""
    params = param_readings(intent)
    givens = scan_givens(text)
    for item in counted_items(text):
        if item.noun.lower() in _UNVALUED:
            return False
        for given in item.each:
            bound = sum(
                1
                for dimension, si in params
                if dimension == given.dimension
                and si is not None
                and given.si is not None
                and math.isclose(si, given.si, rel_tol=1e-6, abs_tol=1e-12)
            )
            if bound and (item.count is None or bound < item.count):
                return False
        kinds = _PART_KINDS.get(item.noun.lower(), ())
        if item.each or item.count is None:
            continue
        for dimension in map(dimension_of, kinds):
            stated = [
                given
                for given in _with_listed_units(text, givens)
                if given.dimension == dimension and not one_item_value(text, given)
            ]
            if 0 < len(stated) < item.count:
                return False
    return True


def _with_listed_units(text: str, givens: list[Given]) -> list[Given]:
    """The givens, a list's numbers taking the unit written after its last ("2, 3 and 6
    ohms" is three resistances)."""
    read = list(givens)
    for index in range(len(read) - 1, 0, -1):
        after, before = read[index], read[index - 1]
        joined = _LIST_JOIN.fullmatch(text, before.end, after.start)
        if before.dimension is None and after.dimension is not None and joined:
            read[index - 1] = replace(before, unit=after.unit, dimension=after.dimension)
    return read
