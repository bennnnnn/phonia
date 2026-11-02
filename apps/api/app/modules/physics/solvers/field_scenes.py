"""Scenes for electric charges: two point charges and the force between them."""

from __future__ import annotations

from app.modules.physics.display import GIVEN_FIGURES, plain_number
from app.modules.physics.schemas import SimulationBlockSpec, SimulationBody, SimulationVector


def _charge_label(value: float, unit: str) -> str:
    sign = "+" if value > 0 else "\u2212" if value < 0 else ""
    unit = {"uC": "µC", "μC": "µC"}.get(unit, unit)
    return f"{sign}{plain_number(abs(value), GIVEN_FIGURES)} {unit}".strip()


def charges_scene(
    q1: tuple[float, str], q2: tuple[float, str], separation: tuple[float, str], force: float
) -> SimulationBlockSpec:
    """Two charges a stated distance apart, each pushed or pulled by the other.

    Like charges repel and unlike attract, so each arrow points away from the
    other charge or toward it; the two are equal and opposite. The charges sit
    at a display distance with the stated one written on a measure line.
    """
    like = q1[0] * q2[0] > 0
    size = 0.18
    shown = f"F = {plain_number(force)} N"
    outward = 1.0 if like else -1.0
    vectors = [
        SimulationVector(
            anchor=[-size * outward, 0.0], dx=-outward, dy=0.0, label=shown, role="result", body=0
        ),
        SimulationVector(anchor=[size * outward, 0.0], dx=outward, dy=0.0, role="result", body=1),
        SimulationVector(
            anchor=[-1.0, -0.45],
            dx=2.0,
            dy=0.0,
            label=f"r = {plain_number(separation[0], GIVEN_FIGURES)} {separation[1]}",
            role="measure",
        ),
    ]
    first, second = _charge_label(*q1), _charge_label(*q2)
    return SimulationBlockSpec(
        type="free_body",
        title="Electric Force",
        title_key="charges",
        bodies=[
            SimulationBody(path=[[-1.0, 0.0], [-1.0, 0.0]], radius=size, label=first),
            SimulationBody(
                path=[[1.0, 0.0], [1.0, 0.0]], radius=size, label=second, role="secondary"
            ),
        ],
        vectors=vectors,
        x_min=-2.2,
        x_max=2.2,
        y_min=-0.9,
        y_max=0.9,
        alt=(
            f"Charges of {first} and {second} "
            f"{plain_number(separation[0], GIVEN_FIGURES)} {separation[1]} apart "
            f"{'repel' if like else 'attract'} each other with {plain_number(force)} N."
        ),
    )
