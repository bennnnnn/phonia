"""Rotational mechanics: moment of inertia, rotational kinetic energy and angular momentum."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.oscillations import _ANGULAR_FREQ_RE
from app.modules.physics.extractors.rotational_dynamics import (
    claims_rotational_dynamics,
    extract_rotational_dynamics,
)
from app.modules.physics.extractors.rotational_readings import _INERTIA_PATTERN
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.unit_patterns import DECIMAL, LENGTH_UNIT_PATTERN, MASS_UNITS
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation, word_index

_ROTATION_CUES = (
    "moment of inertia",
    "rotational inertia",
    "angular momentum",
    "rotational kinetic energy",
    "angular acceleration",
    "parallel-axis",
    "parallel axis",
    "without slipping",
    "rolls without",
)

_ROTATION_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\d\s*(?:{_INERTIA_PATTERN})", re.IGNORECASE),
    re.compile(r"\bangular\s+(?:velocity|speed)\b.{0,80}?\d\s*(?:radians?|rad)\b", re.IGNORECASE),
    re.compile(r"\d\s*(?:radians?|rad)\b.{0,80}?\bangular\s+(?:velocity|speed)\b", re.IGNORECASE),
    re.compile(
        r"\brad(?:ians?)?\s*/\s*s(?:ec(?:ond)?s?)?\s*(?:\^?\s*2|squared)\b",
        re.IGNORECASE,
    ),
)

_INERTIA_SHAPES: dict[str, tuple[float, str]] = {
    "hoop": (1.0, "m r^2"),
    "ring": (1.0, "m r^2"),
    "cylindrical shell": (1.0, "m r^2"),
    "disc": (0.5, r"\tfrac{1}{2} m r^2"),
    "disk": (0.5, r"\tfrac{1}{2} m r^2"),
    "solid cylinder": (0.5, r"\tfrac{1}{2} m r^2"),
    "solid sphere": (0.4, r"\tfrac{2}{5} m r^2"),
    "hollow sphere": (2 / 3, r"\tfrac{2}{3} m r^2"),
    "spherical shell": (2 / 3, r"\tfrac{2}{3} m r^2"),
}


def _extract_rotation_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _ROTATION_CUES, _ROTATION_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None
    dynamic = extract_rotational_dynamics(cleaned)
    if dynamic is not None:
        return dynamic
    if claims_rotational_dynamics(cleaned):
        return None

    inertia = find_value_with_specific_unit(cleaned, _INERTIA_PATTERN)
    omega = _ANGULAR_FREQ_RE.search(cleaned)
    mass = find_value_with_specific_unit(cleaned, MASS_UNITS, ("mass", "of"))
    radius = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("radius", "radii"), require_keyword=True
    )

    if "moment of inertia" in lower or "rotational inertia" in lower:
        # Longest name first, and only as a whole word. ``ring`` sits inside
        # ``during`` and ``disc`` sits inside ``discuss``.
        shape_factor = next(
            (
                factor
                for name, (factor, _) in sorted(
                    _INERTIA_SHAPES.items(), key=lambda item: len(item[0]), reverse=True
                )
                if word_index(lower, name) != -1
            ),
            None,
        )
        if word_index(lower, "rod") != -1:
            length = find_value_with_specific_unit(
                cleaned, LENGTH_UNIT_PATTERN, ("length", "long"), require_keyword=True
            )
            about_end = word_index(lower, "end") != -1
            about_center = word_index(lower, "center") != -1 or word_index(lower, "centre") != -1
            # The axis is the formula. Center and end are different, and neither
            # may be guessed.
            if mass is None or length is None or about_end == about_center:
                return None
            return PhysicsIntent(
                kind="rotation",
                physics_op="rod_end_inertia" if about_end else "rod_center_inertia",
                physics_params={"m": mass[0], "rod_length": length[0]},
                physics_units={"m": mass[1] or "kg", "rod_length": length[1] or "m"},
                operation="solve",
            )
        if shape_factor is None or mass is None or radius is None:
            return None
        return PhysicsIntent(
            kind="rotation",
            physics_op="moment_of_inertia",
            physics_params={"m": mass[0], "r": radius[0], "shape_factor": shape_factor},
            physics_units={"m": mass[1] or "kg", "r": radius[1] or "m", "shape_factor": ""},
            operation="solve",
        )

    if inertia is not None and omega is not None:
        op = (
            "rotational_kinetic_energy"
            if "kinetic energy" in lower or "rotational energy" in lower
            else "angular_momentum"
        )
        return PhysicsIntent(
            kind="rotation",
            physics_op=op,
            physics_params={"inertia": inertia[0], "omega": float(omega.group(1))},
            physics_units={"inertia": "kg*m^2", "omega": "rad/s"},
            operation="solve",
        )

    # omega = theta / t
    # "rad" in "rad/s" is not an angle, and neither is "radians per second".
    turned = re.search(
        rf"({DECIMAL})\s*(?:radians?|rad)(?![A-Za-z/])(?!\s*per\s+second)",
        cleaned,
        re.IGNORECASE,
    )
    elapsed = find_value_with_specific_unit(cleaned, r"seconds?|secs?|sec|s|minutes?|mins?|min")
    if turned is not None and elapsed is not None:
        return PhysicsIntent(
            kind="rotation",
            physics_op="angular_displacement_rate",
            physics_params={"theta": float(turned.group(1)), "t": elapsed[0]},
            physics_units={"theta": "rad", "t": elapsed[1] or "s"},
            operation="solve",
        )
    return None
