"""Optics solvers: lens power, image distance and magnification, refraction, the critical and
Brewster angles, Malus's law, double slits and single-slit diffraction.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from app.modules.physics.constants import SPEED_OF_LIGHT
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.optics_scenes import optics_scene
from app.modules.physics.solvers.results import PhysicsResult, QuantityResult
from app.modules.physics.solvers.si import params_in_si
from app.services.solving import SolveServiceError

_REFLECTION_OPS = frozenset(
    {"reflection_angle", "reflection_surface_angle", "reflection_ray_angle"}
)


def _reflection(intent: PhysicsIntent) -> PhysicsResult:
    """The angle of reflection equals the angle of incidence, both from the normal.

    A ray given against the surface is turned to the normal first, since the
    normal is perpendicular to the mirror: 35 degrees to the surface is 55 to
    the normal. Read as 35, the reflection was answered as 35.
    """
    given = intent.physics_params or {}
    op = intent.physics_op
    steps: list[str] = []
    if "angle_surface" in given:
        surface = given["angle_surface"]
        if not 0 <= surface <= 90:
            raise SolveServiceError("an angle with the mirror lies between 0 and 90 degrees")
        incidence = 90 - surface
        steps.append(rf"\theta_i = 90^\circ - {surface:g}^\circ = {incidence:g}^\circ")
    else:
        incidence = given["angle"]
        if not 0 <= incidence <= 90:
            raise SolveServiceError("an angle of incidence lies between 0 and 90 degrees")
    steps.append(rf"\theta_r = \theta_i = {incidence:g}^\circ")
    formulas = [r"\theta_r = \theta_i"]
    value = incidence
    if op == "reflection_surface_angle":
        value = 90 - incidence
        formulas.append(r"\beta = 90^\circ - \theta_r")
        steps.append(rf"\beta = 90^\circ - {incidence:g}^\circ = {value:g}^\circ")
    elif op == "reflection_ray_angle":
        value = 2 * incidence
        formulas.append(r"\theta_i + \theta_r = 2\theta_i")
        steps.append(rf"\theta_i + \theta_r = 2 \times {incidence:g}^\circ = {value:g}^\circ")
    return PhysicsResult(
        answer=r",\; ".join(steps),
        formulas=tuple(formulas),
        substitutions=tuple(steps),
        quantities=(QuantityResult("", value, "deg"),),
    )


def solve_optics(intent: PhysicsIntent) -> PhysicsResult:
    op = intent.physics_op or ""
    p: dict[str, float] = {}
    if op in _REFLECTION_OPS:
        result = _reflection(intent)
    else:
        p = params_in_si(intent)
        solver = _OPERATIONS.get(op)
        if solver is None:
            raise SolveServiceError(f"unsupported optics op: {op}")
        result = solver(intent, p)
    if result.quantities and not result.simulation_specs:
        quantity = result.quantities[0]
        scene = optics_scene(op, p, intent.physics_params or {}, quantity.unit, quantity.value)
        if scene:
            result = replace(result, simulation_specs=scene)
    return result


def _lens_power(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["focal"] == 0:
        raise SolveServiceError("lens focal length cannot be zero")
    value = 1 / p["focal"]
    return PhysicsResult(
        answer=(
            rf"P = \frac{{1}}{{f}} = \frac{{1}}{{{p['focal']:g}}} "
            rf"\approx {value:.4g} \text{{ D}}"
        ),
        formulas=(r"P = \frac{1}{f}",),
        substitutions=(rf"P = \frac{{1}}{{{p['focal']:g}}}",),
        quantities=(QuantityResult("", value, "D"),),
    )


def _double_slit_fringe_spacing(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["wavelength"] <= 0 or p["L"] <= 0 or p["d"] <= 0:
        raise SolveServiceError("double-slit spacing needs positive wavelength and distances")
    value = p["wavelength"] * p["L"] / p["d"]
    return PhysicsResult(
        answer=(
            rf"\Delta y = \frac{{\lambda L}}{{d}} = "
            rf"\frac{{{p['wavelength']:g} \cdot {p['L']:g}}}{{{p['d']:g}}} "
            rf"\approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"\Delta y = \frac{\lambda L}{d}",),
        substitutions=(rf"\Delta y = \frac{{{p['wavelength']:g} \cdot {p['L']:g}}}{{{p['d']:g}}}",),
        quantities=(QuantityResult("", value, "m"),),
    )


def _diffraction_central_width(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["wavelength"] <= 0 or p["L"] <= 0 or p["d"] <= 0:
        raise SolveServiceError("diffraction width needs positive wavelength and distances")
    value = 2 * p["wavelength"] * p["L"] / p["d"]
    return PhysicsResult(
        answer=(
            rf"w = \frac{{2\lambda L}}{{a}} = "
            rf"\frac{{2 \cdot {p['wavelength']:g} \cdot {p['L']:g}}}{{{p['d']:g}}} "
            rf"\approx {value:.4g} \text{{ m}}"
        ),
        formulas=(r"w = \frac{2\lambda L}{a}",),
        substitutions=(
            rf"w = \frac{{2 \cdot {p['wavelength']:g} \cdot {p['L']:g}}}{{{p['d']:g}}}",
        ),
        quantities=(QuantityResult("", value, "m"),),
    )


def _malus_intensity(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    value = p["intensity0"] * math.cos(p["angle"]) ** 2
    return PhysicsResult(
        answer=(
            rf"I = I_0\cos^2\theta = {p['intensity0']:g} \cdot "
            rf"\cos^2({math.degrees(p['angle']):g}^\circ) "
            rf"\approx {value:.4g} \text{{ W/m}}^2"
        ),
        formulas=(r"I = I_0\cos^2\theta",),
        substitutions=(
            rf"I = {p['intensity0']:g} \cdot \cos^2({math.degrees(p['angle']):g}^\circ)",
        ),
        quantities=(QuantityResult("", value, "W/m^2"),),
    )


def _brewster_angle(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["n1"] <= 0 or p["n2"] <= 0:
        raise SolveServiceError("refractive indexes must be positive")
    value = math.degrees(math.atan(p["n2"] / p["n1"]))
    return PhysicsResult(
        answer=(
            rf"\tan\theta_B = \frac{{n_2}}{{n_1}} \Rightarrow "
            rf"\theta_B = \tan^{{-1}}\!\left(\frac{{{p['n2']:g}}}{{{p['n1']:g}}}\right) "
            rf"\approx {value:.4g}^\circ"
        ),
        formulas=(r"\theta_B = \tan^{-1}\!\left(\frac{n_2}{n_1}\right)",),
        substitutions=(
            rf"\theta_B = \tan^{{-1}}\!\left(\frac{{{p['n2']:g}}}{{{p['n1']:g}}}\right)",
        ),
        quantities=(QuantityResult("", value, "deg"),),
    )


def _critical_angle(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    n = p["n1"]
    if n <= 1:
        raise SolveServiceError("total internal reflection needs an index above 1")
    theta_c = math.degrees(math.asin(1 / n))
    return PhysicsResult(
        answer=(
            rf"\theta_c = \arcsin\!\left(\frac{{1}}{{n}}\right) = "
            rf"\arcsin\!\left(\frac{{1}}{{{n:g}}}\right) \approx {theta_c:.2f}^\circ"
        ),
        formulas=(r"\theta_c = \arcsin\!\left(\frac{1}{n}\right)",),
        substitutions=(rf"\theta_c = \arcsin\!\left(\frac{{1}}{{{n:g}}}\right)",),
        quantities=(QuantityResult("", theta_c, "deg"),),
    )


def _refractive_index(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if "v_wave" in p:
        if p["v_wave"] <= 0:
            raise SolveServiceError("light speed in a medium must be positive")
        n = SPEED_OF_LIGHT / p["v_wave"]
        return PhysicsResult(
            answer=(
                rf"n = \frac{{c}}{{v}} = \frac{{{SPEED_OF_LIGHT:.0f}}}"
                rf"{{{p['v_wave']:g}}} \approx {n:.3g}"
            ),
            formulas=(r"n = \frac{c}{v}",),
            substitutions=(rf"n = \frac{{{SPEED_OF_LIGHT:.0f}}}{{{p['v_wave']:g}}}",),
            quantities=(QuantityResult("", n, ""),),
        )
    t1, t2 = p["angle"], p["angle2"]
    if math.sin(t2) == 0:
        raise SolveServiceError("the refracted angle cannot be zero")
    n = math.sin(t1) / math.sin(t2)
    return PhysicsResult(
        answer=(
            rf"n = \frac{{\sin\theta_1}}{{\sin\theta_2}} = "
            rf"\frac{{\sin({math.degrees(t1):.1f}^\circ)}}"
            rf"{{\sin({math.degrees(t2):.1f}^\circ)}} \approx {n:.2f}"
        ),
        formulas=(r"n = \frac{\sin\theta_1}{\sin\theta_2}",),
        substitutions=(
            rf"n = \frac{{\sin({math.degrees(t1):.1f}^\circ)}}{{\sin({math.degrees(t2):.1f}"
            rf"^\circ)}}",
        ),
        quantities=(QuantityResult("", n, ""),),
    )


def _magnification(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    if p["h_obj"] == 0:
        raise SolveServiceError("the object height cannot be zero")
    m_val = p["h_img"] / p["h_obj"]
    return PhysicsResult(
        answer=(
            rf"m = \frac{{h_i}}{{h_o}} = \frac{{{p['h_img']:g}}}{{{p['h_obj']:g}}} "
            rf"\approx {m_val:.2f}"
        ),
        formulas=(r"m = \frac{h_i}{h_o}",),
        substitutions=(rf"m = \frac{{{p['h_img']:g}}}{{{p['h_obj']:g}}}",),
        quantities=(QuantityResult("", m_val, ""),),
    )


def _virtual_image_distance(obj: float, focal: float, shown: str, *, mirror: bool) -> PhysicsResult:
    """Inside F the image is virtual: its distance, and the side it is on, in words.

    The sign of a virtual image's distance is what the conventions disagree
    about, so the answer is its size and its side: 24 cm, virtual, on the
    object's side of the lens (or behind the mirror). No sign is certified.
    """
    img = obj * focal / (focal - obj)
    side = "virtual, behind the mirror" if mirror else "virtual, on the object's side of the lens"
    return PhysicsResult(
        answer=(
            rf"\frac{{1}}{{f}} = \frac{{1}}{{u}} + \frac{{1}}{{v}} \Rightarrow |v| = "
            rf"\frac{{uf}}{{f - u}} = \frac{{{obj:g} \cdot {focal:g}}}"
            rf"{{{focal:g} - {obj:g}}} \approx {img:.4g} \text{{ {shown}}}"
        ),
        formulas=(r"|v| = \frac{uf}{f - u}",),
        substitutions=(rf"|v| = \frac{{{obj:g} \cdot {focal:g}}}{{{focal:g} - {obj:g}}}",),
        quantities=(QuantityResult("", img, shown, detail=side),),
    )


def _image_distance(intent: PhysicsIntent, p: dict[str, float]) -> PhysicsResult:
    focal, obj = p["focal"], p["d_obj"]
    if focal <= 0 or obj <= 0:
        raise SolveServiceError("only a converging lens with a real object is solved here")
    if math.isclose(obj, focal):
        raise SolveServiceError("an object at the focal point forms no image")
    # The equation holds in any one length unit: distances given in cm
    # are answered in cm (30 cm, not 0.3 m).
    units = intent.physics_units or {}
    shown = units.get("focal", "m")
    if shown in ("cm", "mm") and units.get("d_obj") == shown:
        given = intent.physics_params or {}
        focal, obj = given["focal"], given["d_obj"]
    else:
        shown = "m"
    if obj < focal:
        return _virtual_image_distance(obj, focal, shown, mirror=bool(p.get("mirror")))
    img = 1 / (1 / focal - 1 / obj)
    return PhysicsResult(
        answer=(
            rf"\frac{{1}}{{f}} = \frac{{1}}{{u}} + \frac{{1}}{{v}} \Rightarrow v = "
            rf"\frac{{uf}}{{u - f}} = \frac{{{obj:g} \cdot {focal:g}}}"
            rf"{{{obj:g} - {focal:g}}} \approx {img:.4g} \text{{ {shown}}}"
        ),
        formulas=(r"v = \frac{uf}{u - f}",),
        substitutions=(rf"v = \frac{{{obj:g} \cdot {focal:g}}}{{{obj:g} - {focal:g}}}",),
        quantities=(QuantityResult("", img, shown),),
    )


_OPERATIONS: dict[str, Callable[[PhysicsIntent, dict[str, float]], PhysicsResult]] = {
    "lens_power": _lens_power,
    "double_slit_fringe_spacing": _double_slit_fringe_spacing,
    "diffraction_central_width": _diffraction_central_width,
    "malus_intensity": _malus_intensity,
    "brewster_angle": _brewster_angle,
    "critical_angle": _critical_angle,
    "refractive_index": _refractive_index,
    "magnification": _magnification,
    "image_distance": _image_distance,
}
