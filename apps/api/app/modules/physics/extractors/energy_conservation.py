"""Closed work-energy and mechanical-energy requests.

A sentence that names conservation, net work, or the work-energy theorem is
either one of these templates or not verified. It must not fall through to
kinetic energy just because a mass and a speed are present.
"""

from __future__ import annotations

import re

from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    labeled_value,
)
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent

_ENERGY_UNIT = r"kilojoules?|joules?|kJ|J"
_MASS_UNIT = r"kg|g|mg|lb|lbs|oz"
_NONCONSERVATIVE_RE = re.compile(
    r"\b(?:friction|frictional|drag|air resistance|rough|roughness)\b",
    re.IGNORECASE,
)
_CLOSED_ENERGY_RE = re.compile(
    r"\bconservation of energy\b|\bmechanical energy\b|\benergy is conserved\b"
    r"|\bnet work\b|\bwork-energy\b|\bwork energy theorem\b",
    re.IGNORECASE,
)
_SPRING_RE = re.compile(r"\bspring\b|\bN/m\b", re.IGNORECASE)
_FROM_REST_RE = re.compile(
    r"\b(?:from rest|starts at rest|released from rest|initially at rest)\b",
    re.IGNORECASE,
)
_ASK = r"\b(?:find|what is|calculate)\b"
_WORK_ENERGY_RE = re.compile(r"\bnet work\b|\bwork-energy\b|\bwork energy theorem\b", re.IGNORECASE)
_CONSERVATION_RE = re.compile(
    r"\bconservation of energy\b|\bmechanical energy\b|\benergy is conserved\b",
    re.IGNORECASE,
)


def is_closed_energy_request(lower: str) -> bool:
    return _CLOSED_ENERGY_RE.search(lower) is not None


def extract_closed_energy(cleaned: str) -> PhysicsIntent | None:
    if _NONCONSERVATIVE_RE.search(cleaned):
        return None
    if _WORK_ENERGY_RE.search(cleaned):
        return _work_energy(cleaned)
    if _CONSERVATION_RE.search(cleaned) is None:
        return None
    if _SPRING_RE.search(cleaned):
        return _spring(cleaned)
    if re.search(r"\b(?:height|high)\b", cleaned, re.IGNORECASE):
        return _gravity(cleaned)
    return None


def _asked(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def _nearest_ask(text: str, asks: tuple[tuple[str, str], ...]) -> str | None:
    """The quantity named closest to the question verb.

    "Find its speed at a final height of 5 m" names the speed. A window that
    only checks whether "final height" appears after "find" would drop the
    height that was given.
    """
    best: tuple[int, str] | None = None
    for key, pattern in asks:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        if best is None or match.end() < best[0]:
            best = (match.end(), key)
    return None if best is None else best[1]


def _intent(operation: str, params: dict[str, float], units: dict[str, str]) -> PhysicsIntent:
    return PhysicsIntent(
        kind="energy",
        physics_op=operation,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _work_energy(cleaned: str) -> PhysicsIntent | None:
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    from_to = re.search(
        rf"\bfrom\s+({NUMBER})\s*({VELOCITY_UNIT_PATTERN})\s+to\s+"
        rf"({NUMBER})\s*({VELOCITY_UNIT_PATTERN})\b",
        cleaned,
        re.IGNORECASE,
    )
    if from_to is not None:
        params["v1"] = float(from_to.group(1))
        units["v1"] = from_to.group(2)
        params["v2"] = float(from_to.group(3))
        units["v2"] = from_to.group(4)
    if _FROM_REST_RE.search(cleaned):
        params["v1"] = 0.0
        units["v1"] = "m/s"
    initial = labeled_value(cleaned, r"initial (?:speed|velocity)", VELOCITY_UNIT_PATTERN)
    final = labeled_value(cleaned, r"final (?:speed|velocity)", VELOCITY_UNIT_PATTERN)
    if initial is not None:
        params["v1"], units["v1"] = initial
    if final is not None:
        params["v2"], units["v2"] = final
    mass = find_value_with_specific_unit(
        cleaned, _MASS_UNIT, ("mass", "block", "object", "cart", "box")
    )
    if mass is not None:
        params["m"], units["m"] = mass
    work = re.search(
        rf"\bnet work(?:\s+done)?(?:\s+\w+){{0,6}}?\s+(?:is\s+)?({NUMBER})\s*({_ENERGY_UNIT})\b",
        cleaned,
        re.IGNORECASE,
    )
    if work is None:
        work = re.search(
            rf"({NUMBER})\s*({_ENERGY_UNIT})\s+(?:of\s+)?net work\b",
            cleaned,
            re.IGNORECASE,
        )
    asks_work = _asked(
        cleaned, r"\b(?:find|what is|what's|how much|calculate)\b.{0,40}?\bnet work\b"
    )
    asks_final = _asked(
        cleaned, r"\b(?:find|what is|calculate)\b.{0,40}?\bfinal (?:speed|velocity)\b"
    )
    asks_initial = _asked(
        cleaned, r"\b(?:find|what is|calculate)\b.{0,40}?\binitial (?:speed|velocity)\b"
    )
    asks_mass = _asked(cleaned, r"\b(?:find|what is|calculate)\b.{0,30}?\bmass\b")
    if work is not None and not asks_work:
        params["W"] = float(work.group(1))
        units["W"] = work.group(2)
    if asks_final:
        params.pop("v2", None)
        units.pop("v2", None)
    if asks_initial:
        params.pop("v1", None)
        units.pop("v1", None)
    if asks_mass:
        params.pop("m", None)
        units.pop("m", None)
    if not any((asks_work, asks_final, asks_initial, asks_mass)):
        return None
    if len({"W", "m", "v1", "v2"} - params.keys()) != 1:
        return None
    return _intent("work_energy", params, units)


def _gravity(cleaned: str) -> PhysicsIntent | None:
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if _FROM_REST_RE.search(cleaned):
        params["v1"] = 0.0
        units["v1"] = "m/s"
    for key, label, unit in (
        ("v1", r"initial (?:speed|velocity)", VELOCITY_UNIT_PATTERN),
        ("v2", r"final (?:speed|velocity)", VELOCITY_UNIT_PATTERN),
        ("h1", r"initial height", LENGTH_UNIT_PATTERN),
        ("h2", r"final height", LENGTH_UNIT_PATTERN),
    ):
        found = labeled_value(cleaned, label, unit)
        if found is not None:
            params[key], units[key] = found
    asks = (
        ("v1", rf"{_ASK}.{{0,40}}?\binitial (?:speed|velocity)\b"),
        ("h1", rf"{_ASK}.{{0,40}}?\binitial height\b"),
        ("h2", rf"{_ASK}.{{0,40}}?\b(?:final height|the height)\b"),
        ("v2", rf"{_ASK}.{{0,50}}?\b(?:final speed|final velocity|its speed|the speed)\b"),
    )
    unknown = _nearest_ask(cleaned, asks)
    if unknown is None:
        return None
    params.pop(unknown, None)
    units.pop(unknown, None)
    lower = cleaned.lower()
    if unknown != "h2" and re.search(r"\bat (?:the )?(?:ground|ground level|bottom)\b", lower):
        params.setdefault("h2", 0.0)
        units.setdefault("h2", "m")
    if len({"v1", "h1", "v2", "h2"} - params.keys()) != 1:
        return None
    params["g"] = detect_gravity(cleaned)
    units["g"] = "m/s^2"
    return _intent("mechanical_energy_gravity", params, units)


def _spring(cleaned: str) -> PhysicsIntent | None:
    stiffness = re.search(rf"({NUMBER})\s*N/m\b", cleaned, re.IGNORECASE)
    mass = find_value_with_specific_unit(cleaned, _MASS_UNIT, ("mass", "object", "block"))
    if stiffness is None or mass is None:
        return None
    params: dict[str, float] = {"k": float(stiffness.group(1)), "m": mass[0]}
    units: dict[str, str] = {"k": "N/m", "m": mass[1] or "kg"}
    if _FROM_REST_RE.search(cleaned):
        params["v1"] = 0.0
        units["v1"] = "m/s"
    for key, label in (
        ("v1", r"initial (?:speed|velocity)"),
        ("v2", r"final (?:speed|velocity)"),
        ("x1", r"initial (?:compression|extension|displacement)"),
        ("x2", r"final (?:compression|extension|displacement)"),
    ):
        unit = VELOCITY_UNIT_PATTERN if key.startswith("v") else LENGTH_UNIT_PATTERN
        found = labeled_value(cleaned, label, unit)
        if found is not None:
            params[key], units[key] = found
    if re.search(r"\bat equilibrium\b|\bequilibrium position\b", cleaned, re.IGNORECASE):
        params.setdefault("x2", 0.0)
        units.setdefault("x2", "m")
    motion = r"(?:compression|extension|displacement)"
    asks = (
        ("v1", rf"{_ASK}.{{0,40}}?\binitial (?:speed|velocity)\b"),
        ("x1", rf"{_ASK}.{{0,40}}?\binitial {motion}\b"),
        ("x2", rf"{_ASK}.{{0,40}}?\bfinal {motion}\b"),
        ("v2", rf"{_ASK}.{{0,40}}?\b(?:final speed|final velocity|its speed|the speed)\b"),
    )
    unknown = _nearest_ask(cleaned, asks)
    if unknown is None:
        return None
    params.pop(unknown, None)
    units.pop(unknown, None)
    if len({"v1", "x1", "v2", "x2"} - params.keys()) != 1:
        return None
    return _intent("mechanical_energy_spring", params, units)
