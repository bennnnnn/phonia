"""Typed reads of ``ChemistryIntent.params`` for solvers.

A value the extractor did not find is a refusal, never a default: ``params.get(key) or 1``
turns "the question never gave a concentration" into a verified answer about 1 M.
"""

from __future__ import annotations

from app.modules.chemistry.schemas import ChemistryIntent
from app.services.solving import SolveServiceError


def positive(value: float | None, name: str) -> float:
    """``value`` when it is a positive number, else a refusal naming ``name``."""
    if value is None or value <= 0:
        raise SolveServiceError(f"{name} must be positive")
    return float(value)


def require(
    intent: ChemistryIntent,
    key: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
    message: str | None = None,
) -> float:
    """``params[key]`` as a float; raise ``SolveServiceError`` when absent or out of range."""
    value = intent.params.get(key)
    if value is None:
        raise SolveServiceError(message or f"missing chemistry parameter: {key}")
    if positive and value <= 0:
        raise SolveServiceError(message or f"{key} must be positive")
    if non_negative and value < 0:
        raise SolveServiceError(message or f"{key} cannot be negative")
    return float(value)


def require_all(
    intent: ChemistryIntent,
    *keys: str,
    positive: bool = False,
    non_negative: bool = False,
    message: str | None = None,
) -> tuple[float, ...]:
    """Every key of ``params`` as floats, under the same range rule and message."""
    return tuple(
        require(intent, key, positive=positive, non_negative=non_negative, message=message)
        for key in keys
    )
