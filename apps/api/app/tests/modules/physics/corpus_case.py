"""One corpus row: a question and its hand-worked answer, or None to decline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Case:
    question: str
    # (value, unit) per answered quantity, in the solver's order; None = must decline.
    expected: tuple[tuple[float, str], ...] | None
    rel: float = 0.01


def q(question: str, *expected: tuple[float, str], rel: float = 0.01) -> Case:
    return Case(question, expected, rel)


def decline(question: str) -> Case:
    return Case(question, None)
