"""What a model's read of a question looks like, and what the reader makes of it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

# The registry's subjects (``SubjectName``) and none, in the order the reader's schema states
# them to the model: the order is part of the measured prompt (docs/MODEL_READER.md), so it is
# written here, and ``tests/services/test_subject_registry.py`` holds the set to the registry's.
Subject = Literal["physics", "chemistry", "math", "none"]


# The maths tasks the typed read (``math.tools.llm_extract``) can express, and ``other``
# for every task it cannot: checking someone's work, a value at a point, a word problem.
MATH_TASKS: dict[str, tuple[str, str | None]] = {
    "solve_equation": ("equation", None),
    "solve_system": ("system", None),
    "solve_inequality": ("inequality", None),
    "simplify": ("calculus", "simplify"),
    "factor": ("calculus", "factor"),
    "expand": ("calculus", "expand"),
    "differentiate": ("calculus", "differentiate"),
    "integrate": ("calculus", "integrate"),
    "limit": ("limit", None),
    "graph": ("graph", None),
}


class RouteRead(BaseModel):
    """The first call: which subject the question is in, and which kind of law (for maths,
    which task, or ``other``)."""

    subject: Subject = "none"
    kind: str | None = Field(default=None, max_length=40)


class GivenRead(BaseModel):
    """One value the question states, as the model read it."""

    name: str = Field(max_length=40)
    value: float
    unit: str = Field(default="", max_length=24)
    # The question's own characters that state it, in the question's language.
    quote: str = Field(max_length=160)


class LawRead(BaseModel):
    """The second call: one law from the kind's list and the values it is given."""

    op: str = Field(default="none", max_length=64)
    givens: list[GivenRead] = Field(default_factory=list, max_length=12)
    # Quotes of numbers the question states that are no input of the law.
    unused: list[str] = Field(default_factory=list, max_length=20)
    formula: str | None = Field(default=None, max_length=40)


# Why a read gave no intent: an identifier the turn's trace line may carry.
Reason = Literal[
    "ok",
    "no_read",
    "not_subject",
    "unknown_kind",
    "unknown_op",
    "quote_missing",
    "number_unaccounted",
    "value_not_in_quote",
    "quote_not_one_value",
    "quotes_overlap",
    "binder_disagrees",
    "other_task",
    "kind_mismatch",
    "pool_busy",
    "failed",
]


@dataclass(frozen=True, slots=True)
class ModelRead:
    """What the model reader made of one message."""

    subject: str | None
    op: str | None
    intent: object | None
    reason: Reason
    ms: float
    input_tokens: int = 0
    output_tokens: int = 0


def verdict(regex_subject: str | None, regex_op: str | None, read: ModelRead | None) -> str:
    """How the model's read compares with the patterns': ``agree`` (same law),
    ``other_op`` (same subject, another operation id: a hand-written extractor's id and a
    catalog law's may name one law twice, so only answers can tell), ``disagree`` (another
    subject), ``regex_only``, ``model_only`` or ``neither``. Maths compares the subject
    only: its pattern operation names are not the model's kinds."""
    model_subject = read.subject if read is not None and read.reason == "ok" else None
    model_op = read.op if model_subject is not None and read is not None else None
    if regex_subject and model_subject:
        if regex_subject != model_subject:
            return "disagree"
        if regex_subject == "math" or regex_op == model_op:
            return "agree"
        return "other_op"
    if regex_subject:
        return "regex_only"
    return "model_only" if model_subject else "neither"
