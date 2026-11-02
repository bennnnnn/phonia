"""Linear drag, quadratic drag, and Stokes terminal speed.

Free fall does not own a drop once a velocity-dependent drag law is stated.
``k`` on a spring is newtons per meter, so the drag coefficient is ``drag_k``.
"""

from __future__ import annotations

import re

from app.modules.physics.bodies import WATER_DENSITY
from app.modules.physics.extractors.stated_values import find_value_with_specific_unit
from app.modules.physics.extractors.surface_gravity import detect_gravity
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, MASS_UNITS, NUMBER
from app.modules.physics.schemas import PhysicsIntent

_KV_FORCE = re.compile(
    r"F_drag\s*=\s*-\s*k\s*v\b"
    r"|F_\{drag\}\s*=\s*-\s*k\s*v\b"
    r"|F_d\s*=\s*-\s*k\s*v\b"
    r"|F\s*=\s*-\s*k\s*v\b"
    r"|drag\s*=\s*-\s*k\s*v\b",
    re.IGNORECASE,
)
_LINEAR_WORDS = re.compile(
    r"\blinear drag\b"
    r"|drag(?:\s+force)?\s+proportional to (?:the |its )?(?:velocity|speed)\b"
    r"|resistance proportional to (?:the |its )?(?:velocity|speed)\b",
    re.IGNORECASE,
)
_QUADRATIC_WORDS = re.compile(
    r"\bquadratic drag\b|square of (?:the )?(?:velocity|speed)\b",
    re.IGNORECASE,
)
_V_SQUARED = re.compile(r"v\s*(?:\^|\*\*)\s*2\b|v²", re.IGNORECASE)
_DRAG_WORD = re.compile(r"\b(?:drag|resistance)\b", re.IGNORECASE)
_VELOCITY_DEPENDENT = re.compile(r"\bvelocity-dependent drag\b", re.IGNORECASE)
_NEGLECT_DRAG = re.compile(
    r"\b(?:neglect(?:ing)?|ignore|ignor(?:e|ing)|no|without)\s+(?:the\s+)?"
    r"(?:air resistance|drag)\b",
    re.IGNORECASE,
)
_UPWARD = re.compile(
    r"\b(?:thrown|projected|launched|fired)\s+up(?:ward)?\b|\bvertically\s+up(?:ward)?\b",
    re.IGNORECASE,
)
_FROM_REST = re.compile(r"\bfrom rest\b|\bdropped\b", re.IGNORECASE)
_ASKS_VT = re.compile(r"\bterminal (?:velocity|speed)\b", re.IGNORECASE)
_ASKS_V = re.compile(
    r"v\s*\(\s*t\s*\)|solve for v\b|velocity after|speed after|\bv\(t\)",
    re.IGNORECASE,
)
_ASKS_LIMIT = re.compile(
    r"\blimit\b|k\s*(?:→|->|to)\s*0|no fluid resistance|as k (?:goes|approaches|tends)",
    re.IGNORECASE,
)
_ASKS_TIME = re.compile(
    r"\bhow long\b|\btime (?:until|to|before|does)\b",
    re.IGNORECASE,
)
_K_VALUE = re.compile(
    rf"\bk\s*=\s*({NUMBER})(?:\s*(kg/s|N\s*[·*]\s*s\s*/\s*m|Ns/m))?",
    re.IGNORECASE,
)
_B_VALUE = re.compile(
    rf"\bb\s*=\s*({NUMBER})(?:\s*(kg/m))?",
    re.IGNORECASE,
)
_TIME = re.compile(
    rf"\b(?:after|at)\s+({NUMBER})\s*(?:s|sec|secs|seconds)\b"
    rf"|\bt\s*=\s*({NUMBER})\s*(?:s|sec|secs|seconds)?\b",
    re.IGNORECASE,
)
_SPEED = re.compile(
    rf"({NUMBER})\s*(m/s|km/h|mph)(?![A-Za-z0-9/^])",
    re.IGNORECASE,
)
_DENSITY_UNIT = r"kg/m\^?3|g/cm\^?3"
_BODY_DENSITY = re.compile(
    rf"\b(?:sphere|particle|ball|bead|drop|object)\b.{{0,48}}?"
    rf"({NUMBER})\s*({_DENSITY_UNIT})",
    re.IGNORECASE,
)
_FLUID_DENSITY = re.compile(
    rf"\b(?:fluid|liquid|oil|water|air)\b.{{0,40}}?({NUMBER})\s*({_DENSITY_UNIT})",
    re.IGNORECASE,
)

_DRAG_CUES = (
    "linear drag",
    "quadratic drag",
    "terminal velocity",
    "terminal speed",
    "velocity-dependent drag",
)

_MASS_WORDS = (
    "mass",
    "particle",
    "object",
    "ball",
    "body",
    "raindrop",
    "skydiver",
    "sphere",
    "bead",
)


def _is_quadratic_drag(text: str) -> bool:
    if _KV_FORCE.search(text):
        return False
    if _QUADRATIC_WORDS.search(text):
        return True
    return _V_SQUARED.search(text) is not None and _DRAG_WORD.search(text) is not None


def _is_linear_drag(text: str) -> bool:
    if _is_quadratic_drag(text):
        return False
    return _KV_FORCE.search(text) is not None or _LINEAR_WORDS.search(text) is not None


def closed_drag_request(text: str) -> bool:
    """A drag law this module can solve, even when the question has no digit."""
    return _is_linear_drag(text) or _is_quadratic_drag(text)


def states_velocity_drag(text: str) -> bool:
    """True when constant-acceleration free fall would answer a different problem.

    ``Neglect air resistance`` stays free fall. A stated ``F = -kv`` does not,
    including the limit question that also says the fluid resistance vanishes.
    """
    if _NEGLECT_DRAG.search(text) and not closed_drag_request(text):
        return False
    return bool(
        closed_drag_request(text)
        or _VELOCITY_DEPENDENT.search(text)
        or (_ASKS_VT.search(text) and _DRAG_WORD.search(text))
    )


def _mass(text: str) -> tuple[float, str] | None:
    return find_value_with_specific_unit(text, MASS_UNITS, _MASS_WORDS)


def _time(text: str) -> float | None:
    match = _TIME.search(text)
    if match is None:
        return None
    raw = match.group(1) or match.group(2)
    return float(raw)


def _launch_speed(text: str) -> tuple[float, str] | None:
    match = _SPEED.search(text)
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def _gravity_params(text: str) -> tuple[dict[str, float], dict[str, str]]:
    return {"g": detect_gravity(text)}, {"g": "m/s^2"}


def _asks_only_for_time(text: str) -> bool:
    """A flight time under drag is not the from-rest v(t) formula."""
    return (
        _ASKS_TIME.search(text) is not None
        and _ASKS_V.search(text) is None
        and _ASKS_VT.search(text) is None
        and _ASKS_LIMIT.search(text) is None
    )


def _linear_intent(text: str) -> PhysicsIntent | None:
    if _asks_only_for_time(text):
        return None
    upward = _UPWARD.search(text) is not None
    from_rest = _FROM_REST.search(text) is not None and not upward
    asks_v = _ASKS_V.search(text) is not None or from_rest
    asks_limit = _ASKS_LIMIT.search(text) is not None
    asks_vt = _ASKS_VT.search(text) is not None
    if not (asks_v or asks_limit or asks_vt or upward):
        return None
    mass = _mass(text)
    k_match = _K_VALUE.search(text)
    if (mass is None) != (k_match is None):
        return None
    if upward and from_rest:
        return None
    speed = _launch_speed(text)
    if upward and mass is not None and speed is None:
        return None
    show_motion = from_rest or asks_v or asks_limit or upward
    if mass is None:
        if upward:
            return PhysicsIntent(kind="fluids", physics_op="linear_drag_upward", operation="solve")
        return PhysicsIntent(
            kind="fluids",
            physics_op="linear_drag_fall",
            physics_params={"show_motion": 1.0 if show_motion else 0.0},
            physics_units={"show_motion": ""},
            operation="solve",
        )
    if k_match is None:
        return None
    k_value = float(k_match.group(1))
    if k_value <= 0 or mass[0] <= 0:
        return None
    params, units = _gravity_params(text)
    params["m"] = mass[0]
    params["drag_k"] = k_value
    units["m"] = mass[1] or "kg"
    units["drag_k"] = k_match.group(2) or "kg/s"
    when = _time(text)
    if when is not None:
        if when < 0:
            return None
        params["t"] = when
        units["t"] = "s"
    if upward:
        if speed is None:
            return None
        params["v0"] = speed[0]
        units["v0"] = speed[1]
        op = "linear_drag_upward"
    else:
        op = "linear_drag_fall"
        params["show_motion"] = 1.0 if show_motion else 0.0
        units["show_motion"] = ""
        if speed is not None and not asks_vt:
            params["v0"] = speed[0]
            units["v0"] = speed[1]
    return PhysicsIntent(
        kind="fluids",
        physics_op=op,
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _quadratic_intent(text: str) -> PhysicsIntent | None:
    if _UPWARD.search(text) or _asks_only_for_time(text):
        return None
    from_rest = _FROM_REST.search(text) is not None
    asks_vt = _ASKS_VT.search(text) is not None
    asks_v = _ASKS_V.search(text) is not None
    # v(t) = v_T tanh(gt/v_T) is the from-rest solution. A different launch
    # speed needs another closed form, so that question is not verified.
    if asks_v and not from_rest:
        return None
    if not asks_vt and not from_rest:
        return None
    mass = _mass(text)
    b_match = _B_VALUE.search(text)
    if mass is None and b_match is None:
        return PhysicsIntent(
            kind="fluids",
            physics_op="quadratic_drag_fall",
            physics_params={"show_motion": 1.0 if from_rest or asks_v else 0.0},
            physics_units={"show_motion": ""},
            operation="solve",
        )
    if mass is None or b_match is None:
        return None
    b_value = float(b_match.group(1))
    if b_value <= 0 or mass[0] <= 0:
        return None
    params, units = _gravity_params(text)
    params["m"] = mass[0]
    params["drag_b"] = b_value
    params["show_motion"] = 1.0 if from_rest or asks_v else 0.0
    units["m"] = mass[1] or "kg"
    units["drag_b"] = b_match.group(2) or "kg/m"
    units["show_motion"] = ""
    when = _time(text)
    if when is not None and _FROM_REST.search(text):
        params["t"] = when
        units["t"] = "s"
    return PhysicsIntent(
        kind="fluids",
        physics_op="quadratic_drag_fall",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _stokes_terminal(text: str) -> PhysicsIntent | None:
    lower = text.lower()
    if "terminal" not in lower:
        return None
    if "stokes" not in lower and "sphere" not in lower:
        return None
    radius = find_value_with_specific_unit(
        text, LENGTH_UNIT_PATTERN, ("radius",), require_keyword=True
    )
    viscosity = find_value_with_specific_unit(text, r"Pa\s*[·*]\s*s|Pa\s*s|pascal\s*seconds?")
    if radius is None or viscosity is None:
        return None
    body = _BODY_DENSITY.search(text)
    fluid = _FLUID_DENSITY.search(text)
    if body is None:
        return None
    if fluid is None and "water" in lower:
        fluid_value, fluid_unit = WATER_DENSITY, "kg/m^3"
    elif fluid is None:
        return None
    else:
        fluid_value, fluid_unit = float(fluid.group(1)), fluid.group(2)
    params, units = _gravity_params(text)
    params.update(
        {
            "r": radius[0],
            "viscosity": viscosity[0],
            "rho_body": float(body.group(1)),
            "rho": fluid_value,
        }
    )
    units.update(
        {
            "r": radius[1] or "m",
            "viscosity": viscosity[1] or "Pa*s",
            "rho_body": body.group(2),
            "rho": fluid_unit,
        }
    )
    return PhysicsIntent(
        kind="fluids",
        physics_op="stokes_terminal_velocity",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def extract_drag_intent(text: str) -> PhysicsIntent | None:
    """One drag law, or nothing. Stokes force (a speed is given) stays with fluids."""
    stokes = _stokes_terminal(text)
    if stokes is not None:
        return stokes
    if _is_quadratic_drag(text):
        return _quadratic_intent(text)
    if _is_linear_drag(text):
        return _linear_intent(text)
    return None
