"""One resistor in series with a parallel group: R = R₁ + (R₂ ∥ R₃ ∥ …).

"A 4 Ω resistor is in series with a parallel pair of 6 Ω and 12 Ω" is 8 Ω, and
the all-series reading said 22 Ω, so a network naming both words used to be
declined. This reads the one shape a sentence states without ambiguity: exactly
one "in series with", one side holding a single resistor, the other a parallel
group ("a parallel pair of 6 Ω and 12 Ω", "6 Ω and 3 Ω are in parallel", "two
4 Ω resistors in parallel"). "In parallel with both", a second "series" or a
second "parallel" describe another network, and decline.
"""

from __future__ import annotations

import re

from app.modules.physics.extractors.circuit_patterns import network_asks, resistor_values
from app.modules.physics.schemas import PhysicsIntent

_IN_SERIES_WITH = re.compile(r"\bin\s+series\s+with\b", re.IGNORECASE)
# A group the sentence closes on itself: "a parallel pair of", "are in parallel".
# "In parallel with" or "to" joins it to something else, a network this does not read.
_PARALLEL_GROUP = re.compile(
    r"\bparallel\s+(?:pair|combination|group|bank|arrangement|network|set)\s+of\b"
    r"|\bin\s+parallel\b(?!\s+(?:with|to|across)\b)",
    re.IGNORECASE,
)
_MAX_GROUP = 4


def series_parallel_intent(
    cleaned: str,
    volts: list[tuple[float, str]],
    amps: list[tuple[float, str]],
) -> PhysicsIntent | None:
    """R₁ in series with a parallel group: its total, or the current a supply drives."""
    lower = cleaned.lower()
    joins = list(_IN_SERIES_WITH.finditer(cleaned))
    if len(joins) != 1 or lower.count("series") != 1 or lower.count("parallel") != 1:
        return None
    before, after = cleaned[: joins[0].start()], cleaned[joins[0].end() :]
    group_side, single_side = (before, after) if "parallel" in before.lower() else (after, before)
    if _PARALLEL_GROUP.search(group_side) is None:
        return None
    single, group = resistor_values(single_side), resistor_values(group_side)
    if len(single) != 1 or not 2 <= len(group) <= _MAX_GROUP:
        return None
    if any(value <= 0 for value in (*single, *group)):
        return None
    resistances = [*single, *group]
    params = {f"R{n}": value for n, value in enumerate(resistances, start=1)}
    units = {f"R{n}": "ohm" for n in range(1, len(resistances) + 1)}
    asks_current, asks_resistance = network_asks(lower)
    if asks_current and not asks_resistance:
        if len(volts) != 1 or amps:
            return None
        return PhysicsIntent(
            kind="circuit",
            physics_op="series_parallel_current",
            physics_params={**params, "V": volts[0][0]},
            physics_units={**units, "V": "volt"},
            operation="solve",
        )
    return PhysicsIntent(
        kind="circuit",
        physics_op="series_parallel_resistance",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )
