"""Closed forms for linear drag, quadratic drag, and Stokes terminal speed.

The identities are checked by differentiating the textbook formula and taking
the limits, in this process. Chat already runs physics in the SymPy worker.
"""

from __future__ import annotations

import math
from functools import lru_cache

from app.modules.physics.display import latex_number
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError

_LINEAR_V = r"v(t)=\frac{mg}{k}\left(1-e^{-(k/m)t}\right)"
_LINEAR_VT = r"v_{T}=\frac{mg}{k}"
_LINEAR_LIMIT = r"\lim_{k\to 0}v(t)=gt"
_UP_V = r"v(t)=-\frac{mg}{k}+\left(v_0+\frac{mg}{k}\right)e^{-(k/m)t}"
_UP_LIMIT = r"\lim_{k\to 0}v(t)=v_0-gt"
_QUAD_V = r"v(t)=v_{T}\tanh\left(\frac{gt}{v_{T}}\right)"
_QUAD_VT = r"v_{T}=\sqrt{\frac{mg}{b}}"
_QUAD_LIMIT = r"\lim_{b\to 0}v(t)=gt"


@lru_cache(maxsize=1)
def _drag_identities_hold() -> bool:
    """Textbook formulas satisfy the ODEs, the rest condition, and the limits."""
    import sympy as sp

    m, g, k, b, t = sp.symbols("m g k b t", positive=True)
    v0 = sp.symbols("v0", real=True)
    fall = (m * g / k) + (v0 - m * g / k) * sp.exp(-(k / m) * t)
    fall_ode = sp.diff(fall, t) - (g - (k / m) * fall)
    upward = -(m * g / k) + (v0 + m * g / k) * sp.exp(-(k / m) * t)
    upward_ode = sp.diff(upward, t) - (-g - (k / m) * upward)
    terminal = sp.sqrt(m * g / b)
    quad = terminal * sp.tanh(t * sp.sqrt(b * g / m))
    quad_ode = sp.diff(quad, t) - (g - (b / m) * quad**2)
    checks = (
        sp.simplify(fall_ode) == 0,
        sp.simplify(fall.subs(t, 0) - v0) == 0,
        sp.simplify(sp.limit(fall, t, sp.oo) - m * g / k) == 0,
        sp.simplify(sp.limit(fall, k, 0) - (v0 + g * t)) == 0,
        sp.simplify(upward_ode) == 0,
        sp.simplify(upward.subs(t, 0) - v0) == 0,
        sp.simplify(sp.limit(upward, k, 0) - (v0 - g * t)) == 0,
        sp.simplify(quad_ode) == 0,
        sp.simplify(quad.subs(t, 0)) == 0,
        sp.simplify(sp.limit(quad, t, sp.oo) - terminal) == 0,
        sp.simplify(sp.limit(quad, b, 0) - g * t) == 0,
    )
    return all(checks)


def _require_identities() -> None:
    if not _drag_identities_hold():
        raise SolveServiceError("drag closed form failed its differential-equation check")


def _positive(params: dict[str, float], *keys: str) -> None:
    for key in keys:
        if params.get(key, 0) <= 0:
            raise SolveServiceError(f"{key} must be positive")


def _n(value: float) -> str:
    return latex_number(value, 6)


def solve_linear_drag_fall(intent: PhysicsIntent) -> PhysicsResult:
    """Downward positive. From rest, v(t) = (mg/k)(1 - e^{-(k/m)t}) and lim = gt."""
    _require_identities()
    params = params_in_si(intent)
    show = params.get("show_motion", 0) >= 1 or "t" in params or "v0" in params
    if "m" not in params:
        if not show:
            return _symbolic_terminal_only()
        return _symbolic_fall()
    _positive(params, "m", "drag_k", "g")
    mass, drag_k, gravity = params["m"], params["drag_k"], params["g"]
    v0 = params.get("v0", 0.0)
    terminal = mass * gravity / drag_k
    formulas = (_LINEAR_V, _LINEAR_VT, _LINEAR_LIMIT) if show or v0 == 0 else (_LINEAR_VT,)
    rows = [rf"v_{{T}}=\frac{{{_n(mass)}\cdot {_n(gravity)}}}{{{_n(drag_k)}}}"]
    quantities = [QuantityResult("v_{T}", terminal, "m/s")]
    if "t" in params:
        if params["t"] < 0:
            raise SolveServiceError("time cannot be negative")
        decay = math.exp(-(drag_k / mass) * params["t"])
        speed = terminal + (v0 - terminal) * decay
        rows.append(
            rf"v({_n(params['t'])})={_n(terminal)}+\left({_n(v0)}-{_n(terminal)}\right)"
            rf"e^{{-({_n(drag_k)}/{_n(mass)})\cdot {_n(params['t'])}}}"
        )
        quantities.insert(0, QuantityResult("v(t)", speed, "m/s"))
    return PhysicsResult(
        answer=rf"{_LINEAR_VT} = {_n(terminal)}\ \mathrm{{m/s}}",
        formulas=formulas,
        substitutions=tuple(rows),
        quantities=tuple(quantities),
        joiner="projectile",
    )


def _symbolic_fall() -> PhysicsResult:
    card = rf"{_LINEAR_V},\quad {_LINEAR_VT},\quad {_LINEAR_LIMIT}"
    return PhysicsResult(
        answer="v(t) = (mg/k)(1 - exp(-(k/m)t)); v_T = mg/k; limit as k -> 0 is gt",
        answer_value="v(t) = (mg/k)(1 - exp(-(k/m)t)); v_T = mg/k; limit as k -> 0 is gt",
        answer_latex=card,
        formulas=(
            r"m\frac{dv}{dt}=mg-kv",
            _LINEAR_V,
            _LINEAR_VT,
            _LINEAR_LIMIT,
        ),
        substitutions=(
            r"1-e^{-(k/m)t}\to (k/m)t",
            r"\frac{mg}{k}\cdot\frac{k}{m}t=gt",
            _LINEAR_LIMIT,
        ),
    )


def _symbolic_terminal_only() -> PhysicsResult:
    return PhysicsResult(
        answer="v_T = mg/k",
        answer_value="v_T = mg/k",
        answer_latex=_LINEAR_VT,
        formulas=(_LINEAR_VT,),
        substitutions=(_LINEAR_VT,),
    )


def solve_linear_drag_upward(intent: PhysicsIntent) -> PhysicsResult:
    """Upward positive. v approaches -mg/k, and the zero-drag limit is v0 - gt."""
    _require_identities()
    params = params_in_si(intent)
    if "m" not in params:
        card = rf"{_UP_V},\quad {_LINEAR_VT},\quad {_UP_LIMIT}"
        return PhysicsResult(
            answer="v(t) = -mg/k + (v0 + mg/k) exp(-(k/m)t); limit as k -> 0 is v0 - gt",
            answer_value=("v(t) = -mg/k + (v0 + mg/k) exp(-(k/m)t); limit as k -> 0 is v0 - gt"),
            answer_latex=card,
            formulas=(_UP_V, _LINEAR_VT, _UP_LIMIT),
            substitutions=(_UP_LIMIT,),
        )
    _positive(params, "m", "drag_k", "g", "v0")
    mass, drag_k, gravity, v0 = params["m"], params["drag_k"], params["g"], params["v0"]
    terminal = mass * gravity / drag_k
    quantities: list[QuantityResult] = [QuantityResult("v_{T}", terminal, "m/s")]
    rows = [rf"v_{{T}}=\frac{{{_n(mass)}\cdot {_n(gravity)}}}{{{_n(drag_k)}}}"]
    if "t" in params:
        if params["t"] < 0:
            raise SolveServiceError("time cannot be negative")
        decay = math.exp(-(drag_k / mass) * params["t"])
        speed = -terminal + (v0 + terminal) * decay
        quantities.insert(0, QuantityResult("v(t)", speed, "m/s"))
        rows.append(rf"v({_n(params['t'])})={_n(speed)}")
    return PhysicsResult(
        answer=_UP_V,
        formulas=(_UP_V, _LINEAR_VT, _UP_LIMIT),
        substitutions=tuple(rows),
        quantities=tuple(quantities),
        joiner="projectile",
    )


def solve_quadratic_drag_fall(intent: PhysicsIntent) -> PhysicsResult:
    """Downward positive, from rest: v = v_T tanh(gt/v_T), v_T = sqrt(mg/b)."""
    _require_identities()
    params = params_in_si(intent)
    show = params.get("show_motion", 0) >= 1 or "t" in params
    if "m" not in params:
        if not show:
            return PhysicsResult(
                answer="v_T = sqrt(mg/b)",
                answer_value="v_T = sqrt(mg/b)",
                answer_latex=_QUAD_VT,
                formulas=(_QUAD_VT,),
                substitutions=(_QUAD_VT,),
            )
        card = rf"{_QUAD_V},\quad {_QUAD_VT},\quad {_QUAD_LIMIT}"
        return PhysicsResult(
            answer="v(t) = v_T tanh(gt/v_T); v_T = sqrt(mg/b); limit as b -> 0 is gt",
            answer_value="v(t) = v_T tanh(gt/v_T); v_T = sqrt(mg/b); limit as b -> 0 is gt",
            answer_latex=card,
            formulas=(_QUAD_V, _QUAD_VT, _QUAD_LIMIT),
            substitutions=(_QUAD_LIMIT,),
        )
    _positive(params, "m", "drag_b", "g")
    mass, drag_b, gravity = params["m"], params["drag_b"], params["g"]
    terminal = math.sqrt(mass * gravity / drag_b)
    formulas = (_QUAD_V, _QUAD_VT, _QUAD_LIMIT) if show else (_QUAD_VT,)
    rows = [rf"v_{{T}}=\sqrt{{\frac{{{_n(mass)}\cdot {_n(gravity)}}}{{{_n(drag_b)}}}}}"]
    quantities = [QuantityResult("v_{T}", terminal, "m/s")]
    if "t" in params:
        if params["t"] < 0:
            raise SolveServiceError("time cannot be negative")
        speed = terminal * math.tanh(gravity * params["t"] / terminal)
        quantities.insert(0, QuantityResult("v(t)", speed, "m/s"))
        rows.append(
            rf"v({_n(params['t'])})={_n(terminal)}\tanh"
            rf"\left(\frac{{{_n(gravity)}\cdot {_n(params['t'])}}}{{{_n(terminal)}}}\right)"
        )
    return PhysicsResult(
        answer=_QUAD_VT,
        formulas=formulas,
        substitutions=tuple(rows),
        quantities=tuple(quantities),
        joiner="projectile",
    )


def solve_stokes_terminal(intent: PhysicsIntent) -> PhysicsResult:
    """Terminal speed of a sphere. Buoyancy uses the fluid density."""
    params = params_in_si(intent)
    _positive(params, "r", "viscosity", "g", "rho_body")
    if params["rho"] < 0:
        raise SolveServiceError("fluid density cannot be negative")
    gap = params["rho_body"] - params["rho"]
    if gap <= 0:
        raise SolveServiceError("the sphere must be denser than the fluid")
    speed = 2 * params["r"] ** 2 * gap * params["g"] / (9 * params["viscosity"])
    formula = r"v_{T}=\frac{2r^{2}(\rho_{s}-\rho_{f})g}{9\eta}"
    plugged = (
        rf"v_{{T}}=\frac{{2\cdot {_n(params['r'])}^{{2}}\cdot {_n(gap)}\cdot {_n(params['g'])}}}"
        rf"{{9\cdot {_n(params['viscosity'])}}}"
    )
    return PhysicsResult(
        answer=formula,
        formulas=(formula,),
        substitutions=(plugged,),
        quantities=(QuantityResult("v_{T}", speed, "m/s"),),
        joiner="projectile",
    )


DRAG_SOLVERS = {
    "linear_drag_fall": solve_linear_drag_fall,
    "linear_drag_upward": solve_linear_drag_upward,
    "quadratic_drag_fall": solve_quadratic_drag_fall,
    "stokes_terminal_velocity": solve_stokes_terminal,
}
