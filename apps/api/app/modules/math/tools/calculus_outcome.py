"""Presentation of integral outcomes that are not ordinary finite values."""

import re

_UNDEFINED_VALUE = re.compile(r"\b(?:nan|zoo)\b|\bAccumBounds\(")


def undefined_integral_note(result: str) -> str | None:
    """Undefined markers/accumulation bounds are not defined integral values."""
    if _UNDEFINED_VALUE.search(result) is None:
        return None
    return (
        "The solver did not establish a defined value for this integral. "
        "Do not present this as a verified numeric answer or infer convergence. "
        "Check whether the ordinary integral exists. A Cauchy principal value "
        "is a separate convention and was not computed."
    )


def infinite_integral_note(result: str) -> str | None:
    """Retain the sign of a divergent integral without calling it finite."""
    if result not in {"oo", "-oo"}:
        return None
    direction = "positive" if result == "oo" else "negative"
    return (
        f"This improper integral diverges to {direction} infinity. "
        "Preserve its sign and state that it does not converge to a finite value."
    )
