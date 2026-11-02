"""Closed operations on a student's explicitly stated symbolic physics model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SymbolicOperation = Literal[
    "solve",
    "simplify",
    "differentiate",
    "integrate",
    "ode",
    "gradient",
    "divergence",
    "curl",
    "laplacian",
    "dot",
    "cross",
    "eigenvalues",
    "eigenvectors",
]


class SymbolicPhysicsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: SymbolicOperation
    expressions: tuple[str, ...] = Field(min_length=1, max_length=4)
    variables: tuple[str, ...] = Field(default=(), max_length=4)
    bounds: tuple[str, str] | None = None
    dependent: str | None = None
