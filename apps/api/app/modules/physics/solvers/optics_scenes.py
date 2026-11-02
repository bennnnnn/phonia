"""Ray diagrams for the optics questions that have a geometry.

Every ray is traced here, in the question's own length unit, and handed to
the phone as a polyline; the phone draws, it never traces.
"""

from __future__ import annotations

import math

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import (
    OpticsArrow,
    OpticsRay,
    OpticsSpec,
    SimulationAngle,
    SimulationBlockSpec,
)


def lens_scene(u: float, f: float, v: float, unit: str) -> list[SimulationBlockSpec]:
    """A converging lens with a real object outside F: the three principal rays.

    The object's height is a display choice (the question gives none); every
    ray, and the image they meet at, follows from it and from u and f.
    """
    if not (u > f > 0 and v > 0):
        return []
    h = 0.35 * min(f, u)
    hi = -h * v / u
    rays = [
        # Parallel to the axis, then through the far focal point.
        OpticsRay(points=[[-u, h], [0.0, h], [v, hi]]),
        # Straight through the centre.
        OpticsRay(points=[[-u, h], [0.0, 0.0], [v, hi]]),
        # Through the near focal point, then parallel to the axis.
        OpticsRay(points=[[-u, h], [0.0, hi], [v, hi]]),
    ]
    reach = max(abs(h), abs(hi)) * 1.6
    shown_u = f"{plain_number(u, GIVEN_FIGURES)} {unit}"
    shown_v = f"{plain_number(v)} {unit}"
    return [
        SimulationBlockSpec(
            type="rays",
            title="Ray Diagram",
            title_key="lens",
            optics=OpticsSpec(
                element="converging_lens",
                focal=f,
                object=OpticsArrow(x=-u, height=h, label=f"u = {shown_u}"),
                image=OpticsArrow(x=v, height=hi, label=f"v = {shown_v}"),
                rays=rays,
            ),
            x_min=-u * 1.15,
            x_max=max(v, f) * 1.15,
            y_min=-reach,
            y_max=reach,
            alt=(
                f"An object {shown_u} from a lens of focal length "
                f"{plain_number(f, GIVEN_FIGURES)} {unit} makes a real, inverted image "
                f"{shown_v} behind it."
            ),
        )
    ]


def mirror_image_scene(u: float, f: float, v: float, unit: str) -> list[SimulationBlockSpec]:
    """A concave mirror with a real object outside F: three rays back to the image.

    The mirror faces left, so the object and its real image are both in front
    of it (negative x). The object's height is a display choice, as for a lens.
    """
    if not (u > f > 0 and v > 0):
        return []
    h = 0.35 * min(f, u)
    hi = -h * v / u
    rays = [
        # Parallel to the axis, back through F.
        OpticsRay(points=[[-u, h], [0.0, h], [-v, hi]]),
        # Through F, back parallel to the axis.
        OpticsRay(points=[[-u, h], [0.0, hi], [-v, hi]]),
        # At the vertex, back at the mirrored angle.
        OpticsRay(points=[[-u, h], [0.0, 0.0], [-v, hi]]),
    ]
    reach = max(abs(h), abs(hi)) * 1.6
    shown_u = f"{plain_number(u, GIVEN_FIGURES)} {unit}"
    shown_v = f"{plain_number(v)} {unit}"
    far = max(u, v, f)
    return [
        SimulationBlockSpec(
            type="rays",
            title="Ray Diagram",
            title_key="mirror",
            optics=OpticsSpec(
                element="concave_mirror",
                focal=f,
                object=OpticsArrow(x=-u, height=h, label=f"u = {shown_u}"),
                image=OpticsArrow(x=-v, height=hi, label=f"v = {shown_v}"),
                rays=rays,
            ),
            x_min=-far * 1.15,
            x_max=far * 0.15,
            y_min=-reach,
            y_max=reach,
            alt=(
                f"An object {shown_u} in front of a concave mirror of focal length "
                f"{plain_number(f, GIVEN_FIGURES)} {unit} makes a real, inverted image "
                f"{shown_v} in front of it."
            ),
        )
    ]


def interface_scene(
    incident_deg: float,
    refracted_deg: float,
    media: tuple[str, str],
    *,
    asked: str,
    alt: str,
) -> list[SimulationBlockSpec]:
    """A ray meeting a boundary and bending, with its angles from the normal.

    The boundary is y = 0 and the normal x = 0; light comes from the upper left.
    ``asked`` is "incident" or "refracted", the angle the question asked for.
    """
    i, r = math.radians(incident_deg), math.radians(refracted_deg)
    length = 2.0
    start = [-length * math.sin(i), length * math.cos(i)]
    end = [length * math.sin(r), -length * math.cos(r)]
    if refracted_deg >= 89.9:
        # Grazing: the ray runs along the boundary, drawn just below it.
        end = [length, -0.02]
    return [
        SimulationBlockSpec(
            type="rays",
            title="Refraction",
            title_key="refraction",
            optics=OpticsSpec(
                element="interface",
                media=list(media),
                rays=[OpticsRay(points=[start, [0.0, 0.0], end])],
            ),
            angles=[
                SimulationAngle(
                    vertex=[0.0, 0.0],
                    start_deg=90.0,
                    end_deg=90.0 + incident_deg,
                    label=f"{plain_number(incident_deg)}°",
                    role="result" if asked == "incident" else "given",
                ),
                SimulationAngle(
                    vertex=[0.0, 0.0],
                    start_deg=-90.0,
                    end_deg=-90.0 + refracted_deg,
                    label=f"{plain_number(refracted_deg)}°",
                    role="result" if asked == "refracted" else "given",
                ),
            ],
            x_min=-2.3,
            x_max=2.3,
            y_min=-2.3,
            y_max=2.3,
            alt=alt,
        )
    ]


def mirror_scene(incidence: float, *, asked: bool, alt: str) -> list[SimulationBlockSpec]:
    """A ray off a plane mirror, its two equal angles measured from the normal.

    The mirror stands at x = 0 facing left, so the axis y = 0 is its normal.
    """
    i = math.radians(incidence)
    length = 2.0
    start = [-length * math.cos(i), length * math.sin(i)]
    end = [-length * math.cos(i), -length * math.sin(i)]
    shown = f"{plain_number(incidence)}°"
    angles = (
        [
            SimulationAngle(
                vertex=[0.0, 0.0], start_deg=180.0 - incidence, end_deg=180.0, label=shown
            ),
            SimulationAngle(
                vertex=[0.0, 0.0],
                start_deg=180.0,
                end_deg=180.0 + incidence,
                label=shown,
                role="result" if asked else "given",
            ),
        ]
        if incidence >= 1.0
        else []
    )
    return [
        SimulationBlockSpec(
            type="rays",
            title="Reflection",
            title_key="mirror",
            optics=OpticsSpec(
                element="plane_mirror", rays=[OpticsRay(points=[start, [0.0, 0.0], end])]
            ),
            angles=angles,
            x_min=-2.4,
            x_max=0.6,
            y_min=-2.3,
            y_max=2.3,
            alt=alt,
        )
    ]


def optics_scene(
    op: str, p: dict[str, float], given: dict[str, float], unit: str, value: float
) -> list[SimulationBlockSpec]:
    """The picture for one optics answer, or nothing for one with no geometry."""
    if op == "image_distance":
        shown = unit if unit in ("cm", "mm") else "m"
        u, f = (given["d_obj"], given["focal"]) if shown != "m" else (p["d_obj"], p["focal"])
        if given.get("mirror"):
            return mirror_image_scene(u, f, value, shown)
        return lens_scene(u, f, value, shown)
    if op == "critical_angle":
        n = p["n1"]
        return interface_scene(
            value,
            90.0,
            (f"n = {plain_number(n, GIVEN_FIGURES)}", "air"),
            asked="incident",
            alt=(
                f"Light inside a material of index {plain_number(n, GIVEN_FIGURES)} meets "
                f"the surface at {plain_number(value)}° and skims along it."
            ),
        )
    if op == "refractive_index" and "angle" in p and "angle2" in p:
        incident, refracted = math.degrees(p["angle"]), math.degrees(p["angle2"])
        return interface_scene(
            incident,
            refracted,
            ("air", f"n = {plain_number(value)}"),
            asked="",
            alt=(
                f"Light enters at {plain_number(incident)}° and bends to "
                f"{plain_number(refracted)}°: the index is {plain_number(value)}."
            ),
        )
    if op in ("reflection_angle", "reflection_surface_angle", "reflection_ray_angle"):
        incidence = 90.0 - given["angle_surface"] if "angle_surface" in given else given["angle"]
        return mirror_scene(
            incidence,
            asked=op == "reflection_angle",
            alt=(
                f"A ray meets a plane mirror {plain_number(incidence)}° from the normal "
                f"and leaves {plain_number(incidence)}° from it on the other side."
            ),
        )
    return []
