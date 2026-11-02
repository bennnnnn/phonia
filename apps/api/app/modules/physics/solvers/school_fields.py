"""Closed Gauss and Faraday solvers. Magnitudes only; direction is an assumption."""

from __future__ import annotations

from app.modules.physics.constants import COULOMB_K, EPSILON_0
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.school_common import positive, result
from app.services.solving import SolveServiceError


def _gauss_outside(params: dict[str, float]) -> PhysicsResult:
    positive(params, "r")
    value = COULOMB_K * abs(params["Q"]) / params["r"] ** 2
    return result(
        "E",
        r"k\frac{|Q|}{r^2}",
        rf"{COULOMB_K:.6g}\cdot\frac{{{abs(params['Q']):g}}}{{{params['r']:g}^2}}",
        value,
        "N/C",
    )


def _gauss_shell(params: dict[str, float]) -> PhysicsResult:
    positive(params, "radius_body")
    if params["r"] < 0 or params["r"] >= params["radius_body"]:
        raise SolveServiceError("the point is not inside the shell")
    return PhysicsResult(
        answer=r"E = 0 \text{ inside a charged spherical shell}",
        quantities=(QuantityResult("E", 0.0, "N/C"),),
        formulas=(r"E = 0",),
        substitutions=(r"E = 0",),
    )


def _gauss_sphere(params: dict[str, float]) -> PhysicsResult:
    positive(params, "radius_body")
    if params["r"] < 0 or params["r"] >= params["radius_body"]:
        raise SolveServiceError("the point is not inside the sphere")
    radius = params["radius_body"]
    value = COULOMB_K * abs(params["Q"]) * params["r"] / radius**3
    return result(
        "E",
        r"k\frac{|Q|r}{R^3}",
        rf"{COULOMB_K:.6g}\cdot\frac{{{abs(params['Q']):g}\cdot {params['r']:g}}}{{{radius:g}^3}}",
        value,
        "N/C",
    )


def _gauss_line(params: dict[str, float]) -> PhysicsResult:
    positive(params, "r")
    value = 2 * COULOMB_K * abs(params["lambda_line"]) / params["r"]
    return result(
        "E",
        r"\frac{2k|\lambda|}{r}",
        rf"\frac{{2\cdot {COULOMB_K:.6g}\cdot {abs(params['lambda_line']):g}}}{{{params['r']:g}}}",
        value,
        "N/C",
    )


def _gauss_plane(params: dict[str, float]) -> PhysicsResult:
    value = abs(params["sigma_charge"]) / (2 * EPSILON_0)
    return result(
        "E",
        r"\frac{|\sigma|}{2\epsilon_0}",
        rf"\frac{{{abs(params['sigma_charge']):g}}}{{2\cdot {EPSILON_0:.6g}}}",
        value,
        "N/C",
    )


def _faraday(params: dict[str, float]) -> PhysicsResult:
    positive(params, "turns", "dt")
    if "delta_flux" in params:
        delta = abs(params["delta_flux"])
    else:
        positive(params, "area")
        delta = abs(params["area"] * (params["b2"] - params["b1"]))
    value = params["turns"] * delta / params["dt"]
    return result(
        r"|\mathcal{E}|",
        r"N\frac{|\Delta\Phi|}{\Delta t}",
        rf"{params['turns']:g}\cdot\frac{{{delta:g}}}{{{params['dt']:g}}}",
        value,
        "V",
    )


FIELD_SOLVERS = {
    "gauss_outside": _gauss_outside,
    "gauss_inside_shell": _gauss_shell,
    "gauss_inside_sphere": _gauss_sphere,
    "gauss_line": _gauss_line,
    "gauss_plane": _gauss_plane,
    "faraday_emf": _faraday,
}
