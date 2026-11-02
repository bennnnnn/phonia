"""Rotational kinematics and torque with a moment of inertia.

The patterns are explicit on purpose. A nearby sentence that only shares a
word such as "angular" must keep the older θ/t and L = Iω operations.
"""

from __future__ import annotations

import re

from app.modules.physics.extractors.rotational_laws import (
    _angular_impulse,
    _angular_momentum,
    _parallel_axis,
    _rolling,
)
from app.modules.physics.extractors.rotational_readings import (
    _ALPHA_UNIT,
    _INERTIA_PATTERN,
    _OMEGA_UNIT,
    _alpha,
    _from_rest,
    _inertia_value,
    _intent,
    _omega_pair,
    _time,
    _torque_value,
)
from app.modules.physics.extractors.stated_values import labeled_value
from app.modules.physics.schemas import PhysicsIntent

_CLAIM_RE = re.compile(
    r"parallel[- ]axis|without slipping|angular momentum is conserved|"
    r"\bisolated\b.*\bangular momentum\b|\bangular momentum\b.*\bisolated\b|"
    r"rad(?:ians?)?\s*/\s*s(?:ec(?:ond)?s?)?\s*(?:\^?\s*2|squared)",
    re.IGNORECASE,
)


def claims_rotational_dynamics(text: str) -> bool:
    lower = text.lower()
    if _CLAIM_RE.search(text) is not None:
        return True
    if "torque" in lower and "angular momentum" in lower and re.search(r"\bfind\b", lower):
        return True
    if re.search(r"\b(?:conserved|isolated)\b", lower) and lower.count("inertia") >= 2:
        return True
    return "torque" in lower and "moment of inertia" in lower and "angular acceleration" in lower


def extract_rotational_dynamics(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if "parallel-axis" in lower or "parallel axis" in lower:
        return _parallel_axis(cleaned)
    if "without slipping" in lower or "rolls without" in lower:
        return _rolling(cleaned)
    if re.search(r"\b(?:conserved|isolated)\b", lower) and (
        "angular momentum" in lower or lower.count("inertia") >= 2
    ):
        return _angular_momentum(cleaned)
    if "angular momentum" in lower and "torque" in lower:
        return _angular_impulse(cleaned)
    if "torque" in lower and (
        "moment of inertia" in lower or re.search(_INERTIA_PATTERN, cleaned, re.I)
    ):
        if "angular acceleration" in lower or re.search(_ALPHA_UNIT, cleaned, re.I):
            return _torque_inertia(cleaned)
    if re.search(_ALPHA_UNIT, cleaned, re.I) or "angular acceleration" in lower:
        return _kinematics(cleaned)
    labeled_endpoints = (
        labeled_value(cleaned, r"initial angular (?:velocity|speed)", _OMEGA_UNIT) is not None
        and labeled_value(cleaned, r"final angular (?:velocity|speed)", _OMEGA_UNIT) is not None
    )
    if (
        "angular displacement" in lower
        and _time(cleaned) is not None
        and (_omega_pair(cleaned) is not None or labeled_endpoints)
    ):
        return _kinematics(cleaned)
    return None


def _kinematics(cleaned: str) -> PhysicsIntent | None:
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    if _from_rest(cleaned):
        params["omega0"] = 0.0
        units["omega0"] = "rad/s"
    pair = _omega_pair(cleaned)
    if pair is not None:
        params["omega0"], units["omega0"] = pair[0]
        params["omega"], units["omega"] = pair[1]
    initial = labeled_value(cleaned, r"initial angular (?:velocity|speed)", _OMEGA_UNIT)
    final = labeled_value(cleaned, r"final angular (?:velocity|speed)", _OMEGA_UNIT)
    lone = labeled_value(cleaned, r"(?:final )?angular (?:velocity|speed)", _OMEGA_UNIT)
    if initial is not None:
        params["omega0"], units["omega0"] = initial
    if initial is not None and final is not None:
        params["omega"], units["omega"] = final
    elif (
        initial is None
        and lone is not None
        and "omega" not in params
        and not re.search(r"\bfind\b.{0,40}?\bangular (?:velocity|speed)\b", cleaned, re.IGNORECASE)
    ):
        params["omega0"], units["omega0"] = lone
    alpha = _alpha(cleaned)
    if alpha is not None:
        params["ang_alpha"] = alpha[0]
        units["ang_alpha"] = "rad/s^2"
    elapsed = _time(cleaned)
    if elapsed is not None:
        params["t"], units["t"] = elapsed
    angle = labeled_value(cleaned, r"angular displacement|angle", r"radians?|rad")
    if angle is not None:
        params["theta"], units["theta"] = angle[0], "rad"
    lower = cleaned.lower()
    asks_omega = (
        re.search(r"\b(?:find|what is)\b.{0,40}?\bangular (?:velocity|speed)\b", lower)
        and "initial" not in lower.split("find", 1)[-1][:40]
    )
    asks_theta = (
        re.search(r"\b(?:find|what is)\b.{0,40}?\bangular displacement\b", lower) is not None
    )
    asks_alpha = (
        re.search(r"\b(?:find|what is)\b.{0,40}?\bangular acceleration\b", lower) is not None
    )
    if asks_alpha:
        params.pop("ang_alpha", None)
        if {"omega", "omega0", "t"} <= params.keys() or {
            "omega",
            "omega0",
            "theta",
        } <= params.keys():
            return _intent("rotational_alpha", params, units)
        return None
    if asks_theta:
        params.pop("theta", None)
        if (
            {"omega0", "ang_alpha", "t"} <= params.keys()
            or {"omega", "omega0", "ang_alpha"} <= params.keys()
            or {"omega", "omega0", "t"} <= params.keys()
        ):
            return _intent("rotational_theta", params, units)
        return None
    if asks_omega or (
        "ang_alpha" in params and "omega0" in params and ("t" in params or "theta" in params)
    ):
        params.pop("omega", None)
        if {"omega0", "ang_alpha"} <= params.keys() and ("t" in params or "theta" in params):
            return _intent("rotational_omega", params, units)
    return None


def _torque_inertia(cleaned: str) -> PhysicsIntent | None:
    params: dict[str, float] = {}
    units: dict[str, str] = {}
    torque = _torque_value(cleaned)
    inertia = _inertia_value(cleaned)
    alpha = _alpha(cleaned)
    if torque is not None:
        params["tau"] = torque
        units["tau"] = "N*m"
    if inertia is not None:
        params["inertia"] = inertia
        units["inertia"] = "kg*m^2"
    if alpha is not None:
        params["ang_alpha"] = alpha[0]
        units["ang_alpha"] = "rad/s^2"
    lower = cleaned.lower()
    if re.search(r"\bfind\b.{0,40}?\bangular acceleration\b", lower):
        params.pop("ang_alpha", None)
        units.pop("ang_alpha", None)
    elif re.search(r"\bfind\b.{0,30}?\btorque\b", lower):
        params.pop("tau", None)
        units.pop("tau", None)
    elif re.search(r"\bfind\b.{0,40}?\bmoment of inertia\b", lower):
        params.pop("inertia", None)
        units.pop("inertia", None)
    else:
        return None
    if len({"tau", "inertia", "ang_alpha"} - params.keys()) != 1:
        return None
    return _intent("torque_inertia", params, units)
