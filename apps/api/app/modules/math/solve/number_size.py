"""Refuse an expression whose exact value no student means before SymPy builds it.

``parse_expr`` evaluates while it parses, and the readers parse on the event loop: ``9^9^8``
asked SymPy for a 41-million-digit integer, which held every socket on the machine for a minute,
then raised from ``str()``. The size of each power and factorial is estimated from the unevaluated
tree in logarithms, so the check itself never builds a large number.
"""

from __future__ import annotations

import math
import re
from typing import Any

from sympy import Add, Basic, Mul, Pow, factorial, parse_expr

from app.services.solving import SolveServiceError

# More digits than any exact answer a student asks for (1000! has 2,568).
MAX_EXACT_DIGITS = 10_000

# Only a power or a factorial grows a number past what was written.
_MAY_GROW = re.compile(r"\*\*|!")


def reject_huge_numbers(normalized: str, local_dict: dict[str, Any], transformations: Any) -> None:
    """Raise when evaluating ``normalized`` would build a number past ``MAX_EXACT_DIGITS``."""
    if not _MAY_GROW.search(normalized):
        return
    try:
        tree = parse_expr(
            normalized,
            local_dict=dict(local_dict),
            transformations=transformations,
            evaluate=False,
        )
    except Exception:
        return  # the evaluating parse reports the bad syntax
    if isinstance(tree, Basic):
        _digits(tree)
    elif isinstance(tree, tuple):
        for item in tree:
            if isinstance(item, Basic):
                _digits(item)


def _digits(node: Basic) -> float | None:
    """log10 of ``node``'s magnitude when it is a number, None when it holds a symbol.

    Raises once a power or factorial inside it would run past ``MAX_EXACT_DIGITS``.
    """
    sizes = [_digits(arg) for arg in node.args]
    if node.is_Integer or node.is_Rational:
        top, bottom = abs(int(node.p)), int(node.q)
        return (math.log10(top) if top else 0.0) - math.log10(bottom)
    if node.is_Number:
        value = abs(float(node))
        return math.log10(value) if value else 0.0
    numbers = [size for size in sizes if size is not None]
    if len(numbers) < len(sizes):
        return None
    if isinstance(node, Pow):
        base, exponent = numbers
        return _checked(abs(base) * _value(node.exp, exponent))
    if isinstance(node, factorial):
        n = _value(node.args[0], numbers[0])
        return _checked(n * math.log10(n) if n > 1 else 0.0)
    if isinstance(node, Mul):
        return sum(numbers)
    if isinstance(node, Add):
        return max(numbers, default=0.0) + 1
    return None


def _value(node: Basic, size: float) -> float:
    """``node``'s magnitude as a float, infinite past a float's range."""
    if size > 300:
        return math.inf
    try:
        return abs(float(node))
    except (TypeError, ValueError, OverflowError):
        return 10.0**size


def _checked(digits: float) -> float:
    if digits > MAX_EXACT_DIGITS:
        raise SolveServiceError("Number out of range")
    return digits
