"""Structured chemistry I/O validated before a deterministic solve.

Extractors do not calculate, and solvers do not guess what the user asked for.
"""

from __future__ import annotations

import math
import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

ChemistryKind = Literal[
    "equations",
    "amounts",
    "stoichiometry",
    "solutions",
    "acid_base",
    "gases",
    "thermochemistry",
    "equilibrium",
    "kinetics",
    "electrochemistry",
    "nuclear",
    "spectroscopy",
    "structure",
    "organic",
    "inorganic",
    "analytical",
    "biochemistry",
]

CrystalGeometry = Literal["octahedral", "tetrahedral", "square_planar"]

# No supported calculation needs more. RDKit and SymPy never see a longer string.
MAX_TEXT_FIELD = 500
MAX_SPECIES = 20
MAX_SAMPLES = 50
MAX_STEPS = 6
MAX_PARAMS = 40
# A typed number is short; anything longer was not read from a question.
MAX_WRITTEN = 32
MAX_DECIMALS = 6
# ``written`` only ever holds a number as typed ("1.10", "-0.76", "1.8e-5"), never other text.
_NUMBER_LITERAL = re.compile(r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")

__all__ = ["ChemistryIntent", "ChemistryKind"]


class ChemistryIntent(BaseModel):
    """One unambiguous chemistry calculation.

    ``params`` contains canonical numeric variables and ``units`` records how
    they were supplied for user-visible Given lines. Textual chemistry data
    (formula, equation, target species) is explicit rather than hidden inside
    a generic params dictionary.
    """

    kind: ChemistryKind
    # A catalog id. The catalog is the one list of operations: the validator refuses an id
    # it does not declare, or one it files under another kind.
    chemistry_op: str = Field(max_length=64)
    params: dict[str, float] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    formula: str | None = Field(default=None, max_length=MAX_TEXT_FIELD)
    equation: str | None = Field(default=None, max_length=MAX_TEXT_FIELD)
    target: str | None = Field(default=None, max_length=MAX_TEXT_FIELD)
    geometry: CrystalGeometry | None = None
    species: dict[str, float] = Field(default_factory=dict)
    samples: list[float] = Field(default_factory=list)
    # Step equations a Hess's-law question combines into ``equation`` (each with its ΔH in
    # ``params``, dh1, dh2, ...).
    steps: list[Annotated[str, Field(max_length=MAX_TEXT_FIELD)]] = Field(
        default_factory=list, max_length=MAX_STEPS
    )
    # How the question wrote its numbers (chemistry.sig_figs): the answer's significant
    # figures, the decimal places of a logarithm or of a sum of the givens, and each given's
    # text as typed, keyed by repr.
    figures: int | None = Field(default=None, ge=1, le=6)
    decimals: int | None = Field(default=None, ge=0, le=MAX_DECIMALS)
    written: dict[str, str] = Field(default_factory=dict)
    # A given an extractor converted (500 mL stored as 0.5 L), keyed by the stored value's repr:
    # the literal as typed, so the answer can echo it and keep its figures.
    converted: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def finite_values(self) -> ChemistryIntent:
        # The catalog does not import this module, so asking it here cannot loop.
        from app.modules.chemistry.catalog import check_operation

        check_operation(self.kind, self.chemistry_op)
        if (
            len(self.species) > MAX_SPECIES
            or len(self.samples) > MAX_SAMPLES
            or len(self.params) > MAX_PARAMS
            or len(self.written) > MAX_PARAMS + MAX_SPECIES + MAX_SAMPLES
            or len(self.converted) > MAX_PARAMS + MAX_SPECIES + MAX_SAMPLES
            or any(
                len(text) > MAX_WRITTEN
                for text in (*self.written.values(), *self.converted.values())
            )
        ):
            raise ValueError("chemistry intent is larger than any supported calculation")
        typed = (*self.written.values(), *self.converted.values())
        if not all(_NUMBER_LITERAL.fullmatch(text) for text in typed):
            raise ValueError("a written chemistry value must be a number as typed")
        values = (*self.params.values(), *self.species.values(), *self.samples)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("chemistry values must be finite")
        return self
