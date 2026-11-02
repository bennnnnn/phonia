"""Fluid laws a question names: Stokes, Reynolds, Laplace, Torricelli, Bernoulli."""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.physics.extractors.fluid_readings import _PRESSURE_PATTERN, FluidReading
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN
from app.modules.physics.givens import scan_givens, unit_dimension, unit_expression
from app.modules.physics.schemas import PhysicsIntent
from app.services.law_binding.ask import ask_clause


def _stokes(f: FluidReading) -> PhysicsIntent | None:
    if f.viscosity is None or f.radius is None or len(f.speed) != 1:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="stokes_drag",
        physics_params={
            "viscosity": f.viscosity[0],
            "r": f.radius[0],
            "v": f.speed[0][0],
        },
        physics_units={
            "viscosity": f.viscosity[1] or "Pa*s",
            "r": f.radius[1] or "m",
            "v": f.speed[0][1] or "m/s",
        },
        operation="solve",
    )


def _reynolds(f: FluidReading) -> PhysicsIntent | None:
    rho = f.fluid_density()
    if rho is None or f.viscosity is None or f.characteristic_length is None or len(f.speed) != 1:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="reynolds_number",
        physics_params={
            "rho": rho,
            "v": f.speed[0][0],
            "L": f.characteristic_length[0],
            "viscosity": f.viscosity[0],
        },
        physics_units={
            "rho": f.density[1] if f.density is not None else "kg/m^3",
            "v": f.speed[0][1] or "m/s",
            "L": f.characteristic_length[1] or "m",
            "viscosity": f.viscosity[1] or "Pa*s",
        },
        operation="solve",
    )


def _laplace(f: FluidReading) -> PhysicsIntent | None:
    if f.surface_tension is None or f.radius is None:
        return None
    factor = 4.0 if "soap bubble" in f.lower else 2.0
    return PhysicsIntent(
        kind="fluids",
        physics_op="laplace_pressure",
        physics_params={
            "surface_tension": f.surface_tension[0],
            "r": f.radius[0],
            "mode_factor": factor,
        },
        physics_units={
            "surface_tension": f.surface_tension[1] or "N/m",
            "r": f.radius[1] or "m",
            "mode_factor": "",
        },
        operation="solve",
    )


def _surface_tension(f: FluidReading) -> PhysicsIntent | None:
    length = find_value_with_specific_unit(
        f.cleaned, LENGTH_UNIT_PATTERN, ("length", "edge", "contact")
    )
    if f.force is None or length is None:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="surface_tension",
        physics_params={"F": f.force[0], "L": length[0]},
        physics_units={"F": f.force[1] or "N", "L": length[1] or "m"},
        operation="solve",
    )


def _torricelli(f: FluidReading) -> PhysicsIntent | None:
    if f.depth is None:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="torricelli_speed",
        physics_params={"depth": f.depth[0], "g": detect_gravity(f.cleaned)},
        physics_units={"depth": f.depth[1] or "m", "g": "m/s^2"},
        operation="solve",
    )


def _mass_flow(f: FluidReading) -> PhysicsIntent | None:
    rho = f.fluid_density()
    if rho is None or f.area is None or len(f.speed) != 1:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="mass_flow_rate",
        physics_params={"rho": rho, "area": f.area[0], "v": f.speed[0][0]},
        physics_units={
            "rho": f.density[1] if f.density is not None else "kg/m^3",
            "area": f.area[1] or "m^2",
            "v": f.speed[0][1] or "m/s",
        },
        operation="solve",
    )


_SMALL_SIDE = r"small(?:er)?|narrow(?:er)?|input|first"
_LARGE_SIDE = r"large(?:r)?|big(?:ger)?|wide(?:r)?|output|second"
_PISTON_SIDE = re.compile(
    rf"\b(?:on|to|at|of|by)\s+(?:the|a)\s+(?P<side>{_SMALL_SIDE}|{_LARGE_SIDE})\s+"
    r"(?:piston|cylinder|plunger|side)\b",
    re.IGNORECASE,
)
# The load a hydraulic press lifts stands on its large piston.
_LOAD = re.compile(r"\b(?:car|truck|load|raises?|supports?|holds?\s+up)\b", re.I)


def _known_force_on_large(f: FluidReading) -> bool | None:
    """Whether the stated force acts on the larger piston; None when unsaid.

    "What force on the small piston lifts a 10000 N car?" states the car's
    weight, which stands on the large piston, and asks for the small one's.
    """
    clause = ask_clause(f.cleaned) or ""
    asked = _PISTON_SIDE.search(clause)
    if asked is not None:
        return re.fullmatch(_SMALL_SIDE, asked.group("side"), re.IGNORECASE) is not None
    stated = _PISTON_SIDE.search(f.cleaned.replace(clause, " ") if clause else f.cleaned)
    if stated is not None:
        return re.fullmatch(_LARGE_SIDE, stated.group("side"), re.IGNORECASE) is not None
    if _LOAD.search(f.cleaned):
        return True
    return None


def two_diameters(cleaned: str) -> list[tuple[float, str]] | None:
    """The two diameters a question states: "a diameter of 2 cm and the big one 20 cm".

    Only when "diameter" is said, "radius" is not, and exactly two lengths
    are written.
    """
    lower = cleaned.lower()
    if "diameter" not in lower or "radius" in lower or "radii" in lower:
        return None
    lengths = [
        (given.value, given.unit)
        for given in scan_givens(cleaned)
        if given.dimension == "[length]^1"
    ]
    return lengths if len(lengths) == 2 else None


def _hydraulic_diameters(f: FluidReading) -> PhysicsIntent | None:
    """Pascal's principle with pistons given by diameter; the force side as for areas."""
    diameters = two_diameters(f.cleaned)
    on_large = _known_force_on_large(f)
    if f.force is None or diameters is None or on_large is None:
        return None
    small, large = sorted(diameters, key=lambda diameter: _in_metres(diameter))
    if _in_metres(small) == _in_metres(large):
        return None
    known, other = (large, small) if on_large else (small, large)
    return PhysicsIntent(
        kind="fluids",
        physics_op="hydraulic_force",
        physics_params={"F1": f.force[0], "d1": known[0], "d2": other[0]},
        physics_units={"F1": f.force[1] or "N", "d1": known[1], "d2": other[1]},
        operation="solve",
    )


def _in_metres(length: tuple[float, str]) -> float:
    reading = unit_dimension(unit_expression(length[1]) or "")
    return length[0] if reading is None else length[0] * reading[1]


def _hydraulic(f: FluidReading) -> PhysicsIntent | None:
    """Pascal's principle: F1/A1 = F2/A2, with F1 the stated force on area A1."""
    if f.force is not None and not f.areas:
        return _hydraulic_diameters(f)
    if f.force is None or len(f.areas) != 2:
        return None
    first, second = f.areas
    on_large = _known_force_on_large(f)
    if on_large is None:
        known, other = first, second
    else:
        small, large = sorted((first, second), key=lambda area: area[0])
        known, other = (large, small) if on_large else (small, large)
    return PhysicsIntent(
        kind="fluids",
        physics_op="hydraulic_force",
        physics_params={"F1": f.force[0], "A1": known[0], "A2": other[0]},
        physics_units={
            "F1": f.force[1] or "N",
            "A1": known[1] or "m^2",
            "A2": other[1] or "m^2",
        },
        operation="solve",
    )


def _bernoulli(f: FluidReading) -> PhysicsIntent | None:
    """Bernoulli. Heights only when both are stated; otherwise horizontal."""
    # Height terms are not guessed. Both heights, or the word horizontal.
    initial_height = find_value_with_specific_unit(
        f.cleaned,
        LENGTH_UNIT_PATTERN,
        ("initial height", "starting height"),
        require_keyword=True,
    )
    final_height = find_value_with_specific_unit(
        f.cleaned,
        LENGTH_UNIT_PATTERN,
        ("final height", "ending height"),
        require_keyword=True,
    )
    pressure = find_value_with_specific_unit(f.cleaned, _PRESSURE_PATTERN)
    rho = f.fluid_density()
    if (
        initial_height is not None
        and final_height is not None
        and pressure is not None
        and rho is not None
        and len(f.speed) == 2
    ):
        return PhysicsIntent(
            kind="fluids",
            physics_op="bernoulli_pressure",
            physics_params={
                "pres1": pressure[0],
                "rho": rho,
                "v1": f.speed[0][0],
                "v2": f.speed[1][0],
                "h1": initial_height[0],
                "h2": final_height[0],
                "g": detect_gravity(f.cleaned),
            },
            physics_units={
                "pres1": pressure[1] or "Pa",
                "rho": f.density[1] if f.density is not None else "kg/m^3",
                "v1": f.speed[0][1] or "m/s",
                "v2": f.speed[1][1] or "m/s",
                "h1": initial_height[1] or "m",
                "h2": final_height[1] or "m",
                "g": "m/s^2",
            },
            operation="solve",
        )
    if "horizontal" not in f.lower:
        return None
    if pressure is None or rho is None or len(f.speed) != 2:
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="bernoulli_pressure",
        physics_params={
            "pres1": pressure[0],
            "rho": rho,
            "v1": f.speed[0][0],
            "v2": f.speed[1][0],
        },
        physics_units={
            "pres1": pressure[1] or "Pa",
            "rho": f.density[1] if f.density is not None else "kg/m^3",
            "v1": f.speed[0][1] or "m/s",
            "v2": f.speed[1][1] or "m/s",
        },
        operation="solve",
    )


# A pipe that changes size: the section stated first, and the one it changes to.
_CHANGES_RE = re.compile(
    r"\b(?P<verb>narrow(?:s|ing|ed)?|widen(?:s|ing|ed)?|taper(?:s|ing|ed)?|expand(?:s|ing|ed)?)"
    r"\b(?:\s+(?:down|out))?(?:\s+from\b[^.?!;]{0,40}?)?\s+to\b",
    re.IGNORECASE,
)
_NARROW_WORDS = re.compile(
    r"\b(?:narrow(?:er)?|small(?:er)?|constriction|nozzle|throat|thin(?:ner)?)\b", re.IGNORECASE
)
_WIDE_WORDS = re.compile(r"\b(?:wide(?:r)?|large(?:r)?|big(?:ger)?|broad(?:er)?)\b", re.IGNORECASE)


def pipe_sections(f: FluidReading) -> PhysicsIntent | None:
    """Continuity through a pipe given by diameter: v₂ = v₁(d₁/d₂)².

    "Water flows at 2 m/s in a pipe of diameter 4 cm, which narrows to 2 cm":
    the size after "narrows to" is the second section, the other size the
    first, and the speed is the first section's. The ask must name the second
    section ("in the narrow part"), and a speed stated for the second section
    is not the first's: either way round, the question is not this reading.
    """
    change = _CHANGES_RE.search(f.cleaned)
    diameters = two_diameters(f.cleaned)
    clause = ask_clause(f.cleaned)
    if change is None or diameters is None or clause is None or len(f.speed) != 1:
        return None
    if len(_CHANGES_RE.findall(f.cleaned)) != 1:
        return None
    narrows = change.group("verb").lower().startswith(("narrow", "taper"))
    second_words, first_words = (
        (_NARROW_WORDS, _WIDE_WORDS) if narrows else (_WIDE_WORDS, _NARROW_WORDS)
    )
    if not second_words.search(clause) or first_words.search(clause):
        return None
    ask_start = f.cleaned.rfind(clause)
    givens = scan_givens(f.cleaned)
    lengths = [given for given in givens if given.dimension == "[length]^1"]
    speeds = [given for given in givens if given.dimension == "[length]^1 * [time]^-1"]
    second_at = [given for given in lengths if change.end() <= given.start < ask_start]
    if len(lengths) != 2 or len(second_at) != 1 or len(speeds) != 1:
        return None
    second = second_at[0]
    first = lengths[0] if lengths[1] is second else lengths[1]
    if second.si is None or first.si is None or (second.si < first.si) != narrows:
        return None
    speed = speeds[0]
    sentence_start = max(
        (found.end() for found in re.finditer(r"[.?!;](?:\s|$)", f.cleaned[: speed.start])),
        default=0,
    )
    # The speed is the first section's: never one stated for the second.
    if speed.start >= ask_start or second_words.search(f.cleaned, sentence_start, speed.start):
        return None
    return PhysicsIntent(
        kind="fluids",
        physics_op="continuity_velocity",
        physics_params={"v": speed.value, "d1": first.value, "d2": second.value},
        physics_units={"v": speed.unit, "d1": first.unit, "d2": second.unit},
        operation="solve",
    )


# Each named law and the phrases that name it, tried in this order. A question
# that names one is answered or declined by that law alone.
NAMED_FLUID_LAWS: tuple[
    tuple[tuple[str, ...], Callable[[FluidReading], PhysicsIntent | None]], ...
] = (
    (("stokes",), _stokes),
    (("reynolds",), _reynolds),
    (("laplace pressure", "soap bubble", "droplet"), _laplace),
    (("surface tension",), _surface_tension),
    (("torricelli",), _torricelli),
    (("mass flow rate",), _mass_flow),
    (("hydraulic", "pascal's principle"), _hydraulic),
    (("bernoulli",), _bernoulli),
)
