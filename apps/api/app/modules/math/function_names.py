"""The function names the maths parser reads (``solve/parse.py``).

Every gate that decides whether a letter run is a function or an English word
reads this set, so a function the parser knows is never dropped as a word. The
lists used to drift: ``sech`` and ``\\arccot`` parsed, but a gate threw the
question away first.
"""

from __future__ import annotations

import re

TRIG = ("sin", "cos", "tan", "cot", "sec", "csc")
HYPERBOLIC = ("sinh", "cosh", "tanh", "coth", "sech", "csch")
_DIRECT = TRIG + HYPERBOLIC
# SymPy's names (``acot``) and the textbook's (``arccot``).
INVERSE = tuple(f"a{name}" for name in _DIRECT) + tuple(f"arc{name}" for name in _DIRECT)

MATH_FUNCTION_NAMES = frozenset((*_DIRECT, *INVERSE, "log", "ln", "lg", "exp", "sqrt", "abs"))
# Greek letters spelled out, which the parser reads as one name each (``theta``, not t·h·e·t·a).
GREEK_NAMES = (
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota",
    "kappa", "lambda", "mu", "nu", "xi", "rho", "sigma", "tau", "upsilon", "phi",
    "chi", "psi", "omega",
)  # fmt: skip


def names_longest_first(names: frozenset[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Longest first, so a regex or prefix match reads ``sinh`` before ``sin``."""
    return tuple(sorted(names, key=lambda name: (-len(name), name)))


def function_name_alternation(names: frozenset[str] | tuple[str, ...]) -> str:
    """``sinh|cosh|…|sin`` for a regex group."""
    return "|".join(names_longest_first(names))


_NAMES_AND_CONSTANTS = re.compile(rf"(?:{function_name_alternation(MATH_FUNCTION_NAMES)}|pi|e\^)")


def variable_letters(expr: str) -> set[str]:
    """The letters left once function names and constants go: ``sec(x) + e^x`` has x."""
    return {ch for ch in _NAMES_AND_CONSTANTS.sub("", expr) if ch.isalpha()}
