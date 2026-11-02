"""Shared result formatting for the closed school-physics solvers."""

from __future__ import annotations

from app.modules.physics.solvers.results import PhysicsResult, QuantityResult, solved
from app.services.solving import SolveServiceError


def positive(params: dict[str, float], *keys: str) -> None:
    for key in keys:
        if params[key] <= 0:
            raise SolveServiceError(f"{key} must be positive")


def result(symbol: str, formula: str, numeric: str, value: float, unit: str) -> PhysicsResult:
    shown = f"{value:.4g}"
    unit_text = rf" \text{{ {unit}}}" if unit else ""
    return solved(
        QuantityResult(symbol, value, unit),
        formula=f"{symbol} = {formula}",
        substitution=f"{symbol} = {numeric}",
        answer=rf"{symbol} = {formula} = {numeric} \approx {shown}{unit_text}",
    )
