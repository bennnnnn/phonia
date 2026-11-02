# ruff: noqa: RUF002, RUF003 -- the point of this module is × and the dots it replaces.
"""Multiplication is written × in every reply: ``\\times``, never ``\\cdot`` or a middle dot.

A student read ``KE = 0.5 · 2 · 100`` and asked for the multiplication sign: a raised dot
between numbers reads as a decimal point. Every printer of a product goes through here:
``TIMES`` or ``times`` where it writes one, and ``with_times`` at the one exit of rows
written before this rule (a subject's stored working). Symbols written side by side
(``\\tfrac{1}{2}mv^2``, ``at``, ``mgh``) stay side by side; × appears only where a dot was.

Left as written: ``\\cdots``; a dot inside a unit (``\\mathrm{N·m}``,
``\\text{ N}\\cdot\\text{s}``); a dot product of vectors (``\\vec{a} \\cdot \\vec{b}``).
A 10 raised to a power after a × is bracketed, ``2 \\times (10)^{2}``:
``2 \\times 10^{2}`` is scientific notation for 200.
"""

from __future__ import annotations

import re

TIMES = r"\times"

# A dot of multiplication: \cdot (not \cdots or \cdotp), the dot operator, the middle dot.
_DOT = re.compile(r"\s*(?:\\cdot(?![A-Za-z])|\u22c5|\u00b7)\s*")
# Groups whose letters are words or units, copied as they are.
_WORDS = re.compile(r"\\(?:text|mathrm|textrm|operatorname|mbox)\s*\{")
_VECTOR = re.compile(r"\\(?:vec|mathbf|hat|boldsymbol|overrightarrow)(?![A-Za-z])")
_VECTOR_BEFORE = re.compile(
    r"\\(?:vec|mathbf|hat|boldsymbol|overrightarrow)\s*(?:\{[^{}]*\}|[A-Za-z])\s*$"
)
_UNIT_AFTER = re.compile(r"\s*\\(?:text|mathrm)\s*\{[^{}\d]*\}")
_TEN_RAISED = re.compile(r"10(?=\s*\^)")
_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|.", re.DOTALL)


def times(*factors: str) -> str:
    """``a \\times b \\times c``; a raised 10 after a × in brackets."""
    return " \\times ".join(
        _bracketed_ten(factor) if at else factor for at, factor in enumerate(factors)
    )


def _bracketed_ten(factor: str) -> str:
    """``10^{2}`` → ``(10)^{2}``: after a ×, a bare raised 10 reads as scientific notation."""
    match = _TEN_RAISED.match(factor)
    return f"(10){factor[match.end() :]}" if match else factor


def with_times(latex: str) -> str:
    """``latex`` with every dot of multiplication written ``\\times``."""
    if not latex or _DOT.search(latex) is None:
        return latex
    out: list[str] = []
    at = 0
    while at < len(latex):
        words = _WORDS.match(latex, at)
        if words is not None:
            end = _group_end(latex, words.end() - 1)
            out.append(latex[at:end])
            at = end
            continue
        dot = _DOT.match(latex, at)
        if dot is None:
            # A command is copied whole, so \\cdots and \\cdotp never read as a dot.
            token = _TOKEN.match(latex, at)
            end = token.end() if token is not None else at + 1
            out.append(latex[at:end])
            at = end
            continue
        at = dot.end()
        if _keeps_dot("".join(out), latex[at:]):
            out.append(dot.group(0))
            continue
        out.append(f" {TIMES} ")
        ten = _TEN_RAISED.match(latex, at)
        if ten is not None:
            out.append("(10)")
            at = ten.end()
    return "".join(out)


def _keeps_dot(before: str, after: str) -> bool:
    """A dot product of vectors, or a dot that joins a unit to a quantity's unit
    (``3\\,\\text{N}\\cdot\\text{s}``), is not a multiplication sign. A dot before a
    number is one, whatever unit came before it:
    ``25\\,\\mathrm{m/s} \\times 200\\,\\mathrm{s}``."""
    if _VECTOR_BEFORE.search(before) or _VECTOR.match(after.lstrip()):
        return True
    return _UNIT_AFTER.match(after) is not None


def _group_end(latex: str, brace: int) -> int:
    """Past the ``{…}`` group that opens at ``brace``."""
    depth = 0
    for index in range(brace, len(latex)):
        if latex[index] == "{":
            depth += 1
        elif latex[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(latex)
