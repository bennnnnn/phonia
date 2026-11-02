"""Small physics-owned helpers shared by the physics regression suites."""

import re

from app.modules.physics import (
    build_verified_physics_block,
    extract_physics_intent,
    needs_physics,
)
from app.modules.physics.direct import maybe_direct_physics_reply
from app.modules.physics.fence import validate_physics_fences
from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES


def _spec_fence_kind(spec: dict[str, object]) -> str | None:
    kind = spec.get("type")
    if kind in SIMULATION_SPEC_TYPES:
        return "simulation"
    if kind in {"trajectory", "function", "vertical", "number_line", "inequality"}:
        return "graph"
    if kind == "answer":
        return "answer"
    return None


_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def answer_number(answer: str) -> float:
    """The leading value of a plain answer, scientific form included (``1.67 × 10⁵ J``)."""  # noqa: RUF002
    match = re.match(r"(-?\d+(?:\.\d+)?)(?: × 10([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+))?", answer)
    assert match is not None, answer
    exponent = int(match.group(2).translate(_SUPERSCRIPTS)) if match.group(2) else 0
    return float(match.group(1)) * 10.0**exponent


__all__ = [
    "_spec_fence_kind",
    "answer_number",
    "build_verified_physics_block",
    "extract_physics_intent",
    "maybe_direct_physics_reply",
    "needs_physics",
    "validate_physics_fences",
]
