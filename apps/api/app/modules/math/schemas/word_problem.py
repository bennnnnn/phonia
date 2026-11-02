"""A word problem translated into unknowns and equations (LLM-extracted).

The translation is never trusted: every number must appear in the problem,
and SymPy must find exactly one solution that fits the stated domain before
anything reaches the user. Text fields are shown in the reply, so they are
short and later stripped of markup.

SymPy checks the arithmetic of the equations, not that they say what the problem says. A
setup the server's own templates read from the words (``tools/word_templates.py``) may be
certified; a model's translation is shown to the model as an unchecked reading, never as a
verified card. "divided by x + 1 … the remainder is 3" became f(1) = 3, and a checked card
said A = -61/3, B = 1/3 for A = 1, B = -1 (2026-11-01).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr


class WordUnknown(BaseModel):
    symbol: str = Field(pattern=r"^[a-z]$")
    meaning: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=24)


class WordEquation(BaseModel):
    # Plain ASCII math with one "=": "m = 3*s".
    equation: str = Field(min_length=3, max_length=160)
    # The words of the problem this equation says, shown beside it.
    source: str | None = Field(default=None, max_length=160)


class WordTarget(BaseModel):
    # What the question asks for: an unknown ("s") or an expression in them.
    expr: str = Field(min_length=1, max_length=64)
    meaning: str = Field(min_length=1, max_length=80)
    unit: str | None = Field(default=None, max_length=24)


class WordProblemSetup(BaseModel):
    found: bool = False
    unknowns: list[WordUnknown] = Field(default_factory=list, max_length=3)
    equations: list[WordEquation] = Field(default_factory=list, max_length=4)
    targets: list[WordTarget] = Field(default_factory=list, max_length=3)
    # Counts of people or things: a fractional solution is a misreading.
    whole_numbers: bool = False
    # Ages, lengths, prices: a negative solution is a misreading.
    positive: bool = False
    # Set only by the server's templates, never from a model's JSON: the setup was read
    # from the problem's words, so its solve may be certified.
    _read_from_text: bool = PrivateAttr(default=False)

    @property
    def read_from_text(self) -> bool:
        return self._read_from_text

    def as_read_from_text(self) -> WordProblemSetup:
        """This setup, marked as one the server read from the problem's words."""
        setup = self.model_copy()
        setup._read_from_text = True
        return setup
