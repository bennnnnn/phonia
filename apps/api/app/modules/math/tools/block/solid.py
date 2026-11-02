"""The verified block for a solid's volume or surface area."""

from __future__ import annotations

from dataclasses import replace

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent, SolidGeometryInput
from app.modules.math.solve.geometry import answer_is_rounded
from app.modules.math.tools.block.answer_text import format_quantity
from app.modules.math.tools.block.canonical import finish_with_answer
from app.services.solving import VerifiedMathBlock


def _verified_block_solid(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if intent.solid_shape is None:
        return None
    geo = math_solve.solid_geometry(
        SolidGeometryInput(
            shape=intent.solid_shape,
            width=intent.width,
            height=intent.height,
            depth=intent.depth,
            side=intent.side,
            radius=intent.radius,
            unit=intent.unit,
        )
    )
    lines.append(
        f"Solid ({geo.shape}): volume={geo.labels['volume']} "
        f"surface_area={geo.labels['surface_area']}"
    )
    for key, value in geo.labels.items():
        if key in {"volume", "surface_area"}:
            continue
        lines.append(f"{key}={value}")
    if not (intent.wants_volume or intent.wants_surface_area):
        return VerifiedMathBlock(text="\n".join(lines))
    if intent.wants_surface_area and not intent.wants_volume:
        answer, unit = geo.labels["surface_area"].rsplit(" ", 1)
    else:
        answer, unit = geo.labels["volume"].rsplit(" ", 1)
    quantity = format_quantity(answer, unit)
    block = finish_with_answer(lines, quantity)
    if not answer_is_rounded(answer, geo):
        return block
    # π or a third shown to a few places is that rounding, not the measure: the card says so.
    return replace(block, display_answer=rf"\approx {quantity}")
