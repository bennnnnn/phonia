"""Math-only answer-formatting helpers (fence body text).

The verified-block primitive itself (``VerifiedMathBlock``, ``SolveServiceError``,
the ``[BEGIN/END VERIFIED MATH]`` wrapping) moved to ``app.services.solving`` —
it is shared with physics, not math-only. See docs/SUBJECT_SEPARATION_TICKETS.md
(S2). What is left here is genuinely math-specific: how to render an equation's
roots or a system's solution set as text.
"""

from __future__ import annotations

import re

_TEMPERATURE_NAMES = {
    "c": "°C", "celsius": "°C", "centigrade": "°C", "degc": "°C",
    "f": "°F", "fahrenheit": "°F", "degf": "°F",
    "kelvin": "K",
}  # fmt: skip


def format_quantity(answer: str, unit: str) -> str:
    """Keep a unit upright in the answer's existing math renderer."""
    # Unit strings have already passed a solver or the measurement vocabulary.
    # Normalize common unit powers; escape text-only TeX metacharacters.
    unit = unit.replace("**", "^").replace("²", "^{2}").replace("³", "^{3}")
    # "72 fahrenheit in celsius" shows °C, however the unit was typed.
    unit = _TEMPERATURE_NAMES.get(unit.casefold(), unit)
    # Keep powers outside \mathrm: the native text fallback also understands
    # \mathrm{cm}^{3}, while nested braces inside \mathrm are not portable.
    unit = re.sub(
        r"[A-Za-zµμ°_][A-Za-z0-9µμ°_-]*",
        lambda match: r"\mathrm{" + match.group(0).replace("_", r"\_") + "}",
        unit,
    ).replace("%", r"\%")
    return rf"{answer}\ {unit}"


def _format_equation_answer(
    solutions_latex: list[str],
    solution_kind: str,
) -> str:
    if not solutions_latex:
        if solution_kind == "infinite":
            return r"\text{all real numbers}"
        return r"\text{no solution}"
    if len(solutions_latex) == 1:
        return solutions_latex[0]
    # Two real roots in an aligned KaTeX pill: the gray box was 48px tall
    # (one stacked frac) and overflow:hidden clipped the second row — live
    # "x = 1/2" with "x = 3" hidden. Join with "or" so both stay on native
    # MathText and wrap. Three+ compact roots (x^6=1) still need aligned
    # so they don't clip off the side of the box.
    if len(solutions_latex) == 2:
        return r" \text{ or } ".join(solutions_latex)
    rows: list[str] = []
    for item in solutions_latex:
        if " = " in item:
            left, right = item.split(" = ", 1)
            rows.append(f"{left} &= {right}")
        else:
            rows.append(item)
    return "\\begin{aligned}\n" + " \\\\\n".join(rows) + "\n\\end{aligned}"


def _format_system_answer(
    solutions: list[dict[str, str]],
    solution_kind: str,
) -> str:
    if solutions:
        sets = [", ".join(f"{k} = {v}" for k, v in sol.items()) for sol in solutions]
        if solution_kind == "infinite":
            return (
                r"\text{infinitely many solutions},\quad "
                + "; ".join(sets)
                + r"\quad\text{(one free variable)}"
            )
        return "; ".join(sets)
    if solution_kind == "infinite":
        return r"\text{infinitely many solutions}"
    return r"\text{no solution}"
