"""Angular impulse and momentum, rolling without slipping, and the parallel-axis theorem."""

from __future__ import annotations

import re

from app.modules.physics.extractors.rotational_readings import (
    _INERTIA_PATTERN,
    _OMEGA_UNIT,
    _alpha,
    _angular_values,
    _inertia_value,
    _intent,
    _mass_not_inertia,
    _time,
    _torque_value,
)
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    labeled_value,
)
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.schemas import PhysicsIntent


def _angular_impulse(cleaned: str) -> PhysicsIntent | None:
    values = _angular_values(cleaned)
    pair = re.search(
        rf"\bfrom\s+({NUMBER})\s+to\s+({NUMBER})\s*(?:kg\s*m\^?2\s*/\s*s|kg\*m\^?2/s)",
        cleaned,
        re.IGNORECASE,
    )
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if pair is not None:
        params["L_i"] = float(pair.group(1))
        params["L_f"] = float(pair.group(2))
        units["L_i"] = "kg*m^2/s"
        units["L_f"] = "kg*m^2/s"
    elif len(values) >= 2:
        params["L_i"], params["L_f"] = values[0], values[1]
        units["L_i"] = units["L_f"] = "kg*m^2/s"
    elapsed = _time(cleaned)
    if elapsed is not None:
        params["t"], units["t"] = elapsed
    torque = _torque_value(cleaned)
    if torque is not None and not re.search(r"\bfind\b.{0,30}?\btorque\b", cleaned, re.I):
        params["tau"] = torque
        units["tau"] = "N*m"
    if re.search(r"\bfind\b.{0,30}?\btorque\b", cleaned, re.I):
        params.pop("tau", None)
    elif re.search(r"\bfind\b.{0,40}?\btime\b", cleaned, re.I):
        params.pop("t", None)
    else:
        return None
    if len({"tau", "L_i", "L_f", "t"} - params.keys()) != 1:
        return None
    return _intent("torque_angular_impulse", params, units)


def _angular_momentum(cleaned: str) -> PhysicsIntent | None:
    inertias = [
        float(match.group(1))
        for match in re.finditer(rf"({NUMBER})\s*(?:{_INERTIA_PATTERN})", cleaned, re.IGNORECASE)
    ]
    omegas = [
        float(match.group(1))
        for match in re.finditer(rf"({NUMBER})\s*(?:{_OMEGA_UNIT})\b", cleaned, re.IGNORECASE)
    ]
    if len(inertias) < 1 or len(omegas) < 1:
        return None
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if len(inertias) >= 2:
        params["inertia_i"], params["inertia_f"] = inertias[0], inertias[1]
    else:
        params["inertia_i"] = inertias[0]
    units["inertia_i"] = "kg*m^2"
    if "inertia_f" in params:
        units["inertia_f"] = "kg*m^2"
    if len(omegas) >= 2:
        params["omega_i"], params["omega_f"] = omegas[0], omegas[1]
        units["omega_i"] = units["omega_f"] = "rad/s"
    else:
        params["omega_i"] = omegas[0]
        units["omega_i"] = "rad/s"
    lower = cleaned.lower()
    if re.search(r"\bfind\b.{0,40}?\b(?:final )?angular (?:velocity|speed)\b", lower):
        params.pop("omega_f", None)
        units.pop("omega_f", None)
    elif re.search(r"\bfind\b.{0,40}?\bfinal moment of inertia\b", lower):
        params.pop("inertia_f", None)
    else:
        # The usual skater question names the new inertia and asks for the new spin.
        params.pop("omega_f", None)
        units.pop("omega_f", None)
    if len({"inertia_i", "omega_i", "inertia_f", "omega_f"} - params.keys()) != 1:
        return None
    return _intent("angular_momentum_conservation", params, units)


def _rolling(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("radius", "radii"), require_keyword=True
    )
    speed = find_value_with_specific_unit(cleaned, VELOCITY_UNIT_PATTERN)
    omega = labeled_value(cleaned, r"angular (?:velocity|speed)", _OMEGA_UNIT)
    if omega is None:
        match = re.search(rf"({NUMBER})\s*({_OMEGA_UNIT})\b", cleaned, re.IGNORECASE)
        if match is not None and not re.search(
            r"\bfind\b.{0,40}?\bangular (?:velocity|speed)\b", lower
        ):
            omega = (float(match.group(1)), "rad/s")
    alpha = _alpha(cleaned)
    linear_a = find_value_with_specific_unit(cleaned, r"m/s\^?2|m/s2")
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if radius is not None:
        params["r"], units["r"] = radius
    if "kinetic energy" in lower or "total kinetic" in lower:
        mass = _mass_not_inertia(cleaned)
        inertia = _inertia_value(cleaned)
        if mass is None or inertia is None:
            return None
        params["m"], units["m"] = mass
        params["inertia"] = inertia
        units["inertia"] = "kg*m^2"
        if speed is not None and not re.search(r"\bfind\b.{0,20}?\bspeed\b", lower):
            params["v"], units["v"] = speed
        if omega is not None:
            params["omega"], units["omega"] = omega[0], "rad/s"
        if "v" not in params and "omega" not in params:
            return None
        if ("v" not in params or "omega" not in params) and "r" not in params:
            return None
        return _intent("rolling_kinetic_energy", params, units)
    if re.search(r"\bfind\b.{0,40}?\bangular acceleration\b", lower) or (
        alpha is None and linear_a is not None and "acceleration" in lower
    ):
        if linear_a is not None:
            params["a"], units["a"] = linear_a
        if radius is None:
            return None
        return _intent("rolling_acceleration", params, units)
    if alpha is not None and re.search(r"\bfind\b.{0,30}?\bacceleration\b", lower):
        params["ang_alpha"] = alpha[0]
        units["ang_alpha"] = "rad/s^2"
        if radius is None:
            return None
        return _intent("rolling_acceleration", params, units)
    if re.search(r"\bfind\b.{0,40}?\bangular (?:velocity|speed)\b", lower):
        if speed is not None:
            params["v"], units["v"] = speed
        if "r" not in params or "v" not in params:
            return None
        return _intent("rolling_speed", params, units)
    if re.search(r"\bfind\b.{0,30}?\b(?:speed|velocity)\b", lower):
        if omega is not None:
            params["omega"], units["omega"] = omega[0], "rad/s"
        if "r" not in params or "omega" not in params:
            return None
        return _intent("rolling_speed", params, units)
    return None


def _parallel_axis(cleaned: str) -> PhysicsIntent | None:
    mass = _mass_not_inertia(cleaned)
    center = find_value_with_specific_unit(
        cleaned,
        _INERTIA_PATTERN,
        ("center of mass", "centre of mass", "cm"),
        require_keyword=True,
    )
    distance = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("away", "distance", "axis"),
        require_keyword=True,
    )
    if center is None or mass is None or distance is None:
        return None
    if not re.search(r"\bfind\b.{0,40}?\bmoment of inertia\b", cleaned, re.IGNORECASE):
        return None
    return _intent(
        "parallel_axis",
        {"inertia_cm": center[0], "m": mass[0], "d": distance[0]},
        {"inertia_cm": "kg*m^2", "m": mass[1] or "kg", "d": distance[1] or "m"},
    )
