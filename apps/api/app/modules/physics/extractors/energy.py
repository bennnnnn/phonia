"""Energy extractors: kinetic, potential, work, power and conservation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.modules.physics.extractors.angles import _stated_angle
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    _has_cue_either_case,
)
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import NUMBER, VELOCITY_UNIT_PATTERN
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_ENERGY_CUES = (
    "kinetic energy",
    "potential energy",
    "work done",
    "work is done",
    "how much work",
    "work of",
    "what is the power",
    "what is its power",
    "what's the power",
    "what's its power",
    "energy of",
    "what power",
    "how much power",
    "find the power",
    "find its power",
    "calculate the power",
    "power needed",
    "power required",
    "power is needed",
    "mechanical efficiency",
    "machine efficiency",
    "efficiency of a machine",
    "net work",
    "work-energy",
    "work energy",
    "conservation of energy",
    "mechanical energy",
    "energy is conserved",
)

_KE_ABBREV_RE = re.compile(r"\bk\.?\s?e\.?\s+of\b")

_PE_ABBREV_RE = re.compile(r"\bp\.?\s?e\.?\s+of\b")

# ``power`` is also ordinary exponent language. Route it to physics only when
# the request contains a complete input pair for one of the supported laws:
# P = W/t or P = Fv. This handles arbitrary subjects (motor, student, animal)
# without maintaining a noun allowlist or stealing "the third power of 5".
_SOLVABLE_POWER_DATA_RE = re.compile(
    rf"(?is)\A(?=.*\bpower\b)(?:"
    rf"(?=.*{NUMBER}\s*(?:kilojoules?|joules?|kJ|J)\b)"
    rf"(?=.*{NUMBER}\s*(?:milliseconds?|ms|seconds?|secs?|sec|s|"
    r"minutes?|mins?|min|hours?|hrs?|hr|h)\b)"
    rf"|(?=.*{NUMBER}\s*N\b)(?=.*{NUMBER}\s*(?:{VELOCITY_UNIT_PATTERN})\b))"
)

_ENERGY_CUE_RES: tuple[re.Pattern[str], ...] = (
    _KE_ABBREV_RE,
    _PE_ABBREV_RE,
    _SOLVABLE_POWER_DATA_RE,
)


_ROLLING_BODY_RE = re.compile(
    r"\bwithout\s+slipping\b"
    r"|\b(?:sphere|ball|marble|cylinder|disc|disk|hoop|ring|wheel|tyre|tire|can|pipe)s?\b"
    r"[^.?!]{0,80}?\broll(?:s|ed|ing)?\b(?!\s+off\b)",
    re.IGNORECASE,
)


def _unstated_work_angle(text: str) -> bool:
    """An angle is mentioned, but no number was given to put in cos θ."""
    has_words = re.search(r"\bat an angle\b", text, re.IGNORECASE) is not None
    return has_words and _stated_angle(text) is None


_EnergyOp = Literal["kinetic_energy", "potential_energy", "work", "power"]


@dataclass(frozen=True, slots=True)
class _EnergyGivens:
    """Each value an energy law reads, as (value, unit written), or None when not given."""

    mass: tuple[float, str] | None
    velocity: tuple[float, str] | None
    height: tuple[float, str] | None
    force: tuple[float, str] | None
    distance: tuple[float, str] | None
    work: tuple[float, str] | None
    elapsed: tuple[float, str] | None


def _extract_energy_intent(cleaned: str) -> PhysicsIntent | None:
    from app.modules.physics.extractors.energy_conservation import (
        extract_closed_energy,
        is_closed_energy_request,
    )

    lower = cleaned.lower()
    if not _has_cue_either_case(cleaned, _ENERGY_CUES, _ENERGY_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None
    if _ROLLING_BODY_RE.search(cleaned):
        # A rolling sphere, cylinder or hoop also spins: ½mv² is not its energy.
        return None
    closed = extract_closed_energy(cleaned)
    if closed is not None:
        return closed
    if is_closed_energy_request(lower):
        return None
    if "efficiency" in lower:
        return _mechanical_efficiency(cleaned, lower)

    givens = _read_energy_givens(cleaned)
    op = _choose_energy_op(cleaned, lower, givens)
    if op is None:
        return None
    params, units = _energy_params(op, givens, cleaned)
    return PhysicsIntent(
        kind="energy",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _labelled_energy(
    forward: re.Match[str] | None, reverse: re.Match[str] | None
) -> tuple[float, str] | None:
    match = forward or reverse
    return None if match is None else (float(match.group(1)), match.group(2))


def _mechanical_efficiency(cleaned: str, lower: str) -> PhysicsIntent | None:
    """A machine's useful energy output divided by its energy input.

    Thermal engines retain their own W/Q_in operation in the earlier thermal
    extractor; this branch owns explicitly mechanical/machine wording.
    """
    if not any(word in lower for word in ("machine", "mechanical", "device", "motor")):
        return None
    energies = ordered_values(cleaned, r"kilojoules?|joules?|kJ|J")
    if len(energies) != 2:
        return None
    output_match = re.search(
        rf"(?:output|outputs|useful(?:\s+energy)?)\D{{0,24}}?({NUMBER})\s*"
        r"(kilojoules?|joules?|kJ|J)",
        cleaned,
        re.IGNORECASE,
    )
    input_match = re.search(
        rf"(?:input|supplied|receives?|takes?\s+in)\D{{0,24}}?({NUMBER})\s*"
        r"(kilojoules?|joules?|kJ|J)",
        cleaned,
        re.IGNORECASE,
    )
    output_reverse = re.search(
        rf"({NUMBER})\s*(kilojoules?|joules?|kJ|J)\s*(?:output|useful)",
        cleaned,
        re.IGNORECASE,
    )
    input_reverse = re.search(
        rf"({NUMBER})\s*(kilojoules?|joules?|kJ|J)\s*(?:input|supplied)",
        cleaned,
        re.IGNORECASE,
    )
    output = _labelled_energy(output_match, output_reverse)
    supplied = _labelled_energy(input_match, input_reverse)
    if output is None or supplied is None:
        # Numeric order alone is not a safe way to infer input vs output.
        return None
    return PhysicsIntent(
        kind="energy",
        physics_op="mechanical_efficiency",
        physics_params={"E_out": output[0], "E_in": supplied[0]},
        physics_units={"E_out": output[1] or "J", "E_in": supplied[1] or "J"},
        operation="solve",
    )


def _read_energy_givens(cleaned: str) -> _EnergyGivens:
    """Each value by its own unit, nearest the words that name it."""
    return _EnergyGivens(
        # Mass (m) — use unit-specific search so force isn't picked up as mass.
        mass=find_value_with_specific_unit(
            cleaned, r"kg|g|mg|lb|lbs|oz", ("mass", "object", "body")
        ),
        # Velocity (v) — for KE = 1/2 m v^2
        velocity=find_value_with_specific_unit(
            cleaned,
            r"m/s|km/h|mph|cm/s|mm/s",
            ("velocity", "speed", "moving", "traveling", "travelling"),
        ),
        # Height (h) — for PE = m g h. Use length-specific search.
        height=find_value_with_specific_unit(
            cleaned, r"km|cm|mm|m|ft|yd|in|mi", ("height", "high", "above")
        ),
        # Force (F) — for W = F d
        force=find_value_with_specific_unit(cleaned, r"\bN\b", ("force",)),
        # Distance (d) — for W = F d. Use length-specific search.
        distance=find_value_with_specific_unit(
            cleaned, r"km|cm|mm|m|ft|yd|in|mi", ("distance", "over", "through")
        ),
        # Energy done (W, in joules) and elapsed time — for P = W / t.
        work=find_value_with_specific_unit(
            cleaned, r"kilojoules?|joules?|kJ|J", ("work", "energy")
        ),
        elapsed=find_value_with_specific_unit(
            cleaned, r"milliseconds?|ms|seconds?|secs?|sec|s|minutes?|mins?|min|hours?|hrs?|hr|h"
        ),
    )


def _choose_energy_op(cleaned: str, lower: str, givens: _EnergyGivens) -> _EnergyOp | None:
    """The law the question names, or the one its givens solve; None when they cannot.

    Power is checked before work because a question naming both ("what power does
    100 J of work in 5 s need") is asking for the power; "work done by a 10 N force"
    names only work and is unaffected.
    """
    mass, velocity, height = givens.mass, givens.velocity, givens.height
    force, distance = givens.force, givens.distance
    if "kinetic energy" in lower or _KE_ABBREV_RE.search(lower):
        return None if mass is None or velocity is None else "kinetic_energy"
    if "potential energy" in lower or _PE_ABBREV_RE.search(lower):
        return None if mass is None or height is None else "potential_energy"
    if "power" in lower:
        if _unstated_work_angle(cleaned):
            return None
        # Either school form: P = F v, or P = W / t.
        if (force is None or velocity is None) and (givens.work is None or givens.elapsed is None):
            return None
        # An angle belongs to F v cos θ, not to work divided by time.
        if _stated_angle(cleaned) is not None and (force is None or velocity is None):
            return None
        return "power"
    if "work" in lower:
        if _unstated_work_angle(cleaned):
            return None
        return None if force is None or distance is None else "work"
    # "energy of" / "conservation of energy" — pick whichever we can solve.
    if mass is not None and velocity is not None:
        return "kinetic_energy"
    if mass is not None and height is not None:
        return "potential_energy"
    if force is not None and distance is not None:
        if _unstated_work_angle(cleaned):
            return None
        return "work"
    return None


def _energy_params(
    op: _EnergyOp, givens: _EnergyGivens, cleaned: str
) -> tuple[dict[str, float], dict[str, str]]:
    """The chosen law's givens and their units, in the order the working lists them."""
    mass, velocity, height = givens.mass, givens.velocity, givens.height
    force, distance = givens.force, givens.distance
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if op in ("kinetic_energy", "potential_energy") and mass is not None:
        params["m"] = mass[0]
        units["m"] = mass[1] or "kg"
    if op in ("kinetic_energy", "power") and velocity is not None:
        params["v"] = velocity[0]
        units["v"] = velocity[1] or "m/s"
    if op == "potential_energy" and height is not None:
        params["h"] = height[0]
        units["h"] = height[1] or "m"
    if op == "power" and (force is None or velocity is None):
        # P = W / t. Drop any partial F/v so solve_energy picks this form.
        params.pop("v", None)
        units.pop("v", None)
        if givens.work is not None and givens.elapsed is not None:
            params["W"] = givens.work[0]
            units["W"] = givens.work[1] or "J"
            params["t"] = givens.elapsed[0]
            units["t"] = givens.elapsed[1] or "s"
    elif op in ("work", "power") and force is not None:
        params["F"] = force[0]
        units["F"] = force[1] or "N"
    if op == "work" and distance is not None:
        params["d"] = distance[0]
        units["d"] = distance[1] or "m"
    if op in ("work", "power"):
        angle = _stated_angle(cleaned)
        if angle is not None and "F" in params:
            params["angle"] = angle[0]
            units["angle"] = angle[1]
    if op == "potential_energy":
        params["g"] = detect_gravity(cleaned)
        units["g"] = "m/s^2"
    return params, units
