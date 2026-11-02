"""Materials solvers: stress, strain and the Young modulus."""

from __future__ import annotations

from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError


def solve_materials(intent: PhysicsIntent) -> PhysicsResult:
    p = params_in_si(intent)
    op = intent.physics_op or ""

    if op == "stress":
        area = p["area"]
        if area <= 0:
            raise SolveServiceError("area must be positive")
        value = p["F"] / area
        return PhysicsResult(
            answer=(
                rf"\sigma = \frac{{F}}{{A}} = \frac{{{p['F']:g}}}{{{area:g}}} "
                rf"\approx {value:.4g} \text{{ Pa}}"
            ),
            formulas=(r"\sigma = \frac{F}{A}",),
            substitutions=(rf"\sigma = \frac{{{p['F']:g}}}{{{area:g}}}",),
            quantities=(QuantityResult("", value, "Pa"),),
        )

    if op == "strain":
        original = p["L0"]
        if original <= 0:
            raise SolveServiceError("the original length must be positive")
        value = p["dL"] / original
        return PhysicsResult(
            answer=(
                rf"\varepsilon = \frac{{\Delta L}}{{L_0}} = "
                rf"\frac{{{p['dL']:g}}}{{{original:g}}} \approx {value:.4g}"
            ),
            formulas=(r"\varepsilon = \frac{\Delta L}{L_0}",),
            substitutions=(rf"\varepsilon = \frac{{{p['dL']:g}}}{{{original:g}}}",),
            quantities=(QuantityResult("", value, ""),),
        )

    if op == "youngs_modulus":
        strain = p["strain"]
        if strain == 0:
            raise SolveServiceError("strain cannot be zero")
        value = p["sigma"] / strain
        return PhysicsResult(
            answer=(
                rf"E = \frac{{\sigma}}{{\varepsilon}} = "
                rf"\frac{{{p['sigma']:g}}}{{{strain:g}}} \approx {value:.4g} \text{{ Pa}}"
            ),
            formulas=(r"E = \frac{\sigma}{\varepsilon}",),
            substitutions=(rf"E = \frac{{{p['sigma']:g}}}{{{strain:g}}}",),
            quantities=(QuantityResult("", value, "Pa"),),
        )

    raise SolveServiceError(f"unsupported materials op: {op}")
