"""The rule behind each worked step, and the number work a student typed.

A step says what to do ("Subtract 25 from both sides"); its rule says why that
is allowed ("Subtraction property of equality"). The rule is read from the
step's label, so every equation trace (linear, quadratic, radical, log, …)
gets one without each builder carrying it.

``3x^2 + 5^2 = 25`` used to start at ``3x^2 + 25 = 25``: the 5² became 25
with no step. ``evaluate_powers_label`` names that move so it is shown.
"""

from __future__ import annotations

import re
from functools import partial
from typing import Any

from sympy import Eq, Pow, Symbol, latex, preorder_traversal, simplify, solve

from app.modules.math.solve.declines import sympy_decline

# 5^2 is shown as 5 · 5; 2^10 is shown only as its value.
_SHOW_REPEATED = 4

# First match wins; a label that names no rule ("Simplify", "Solve") gets none.
_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), rule)
    for pattern, rule in (
        (r"^Add\b.*\bto both sides", "Addition property of equality"),
        (r"^Subtract\b.*\bfrom both sides", "Subtraction property of equality"),
        (r"^Multiply both sides", "Multiplication property of equality"),
        (r"^Divide both sides", "Division property of equality"),
        (
            r"^(?:Square root|Take (?:the )?square roots?)",
            r"Square root property: $x^2 = k \Rightarrow x = \pm\sqrt{k}$",
        ),
        (r"^Raise both sides", "Power property of equality"),
        (r"^Square (?:both sides|again|and isolate)", "Squaring both sides; check every root"),
        (r"^Take\b.*\bof both sides", "Same operation on both sides"),
        (r"^Evaluate\b", r"Exponent: $a^n$ is $a$ multiplied by itself $n$ times"),
        (r"^Expand\b", r"Distributive property: $a(b + c) = ab + ac$"),
        (r"^Collect like terms", "Combine like terms"),
        (
            r"^Set each factor equal to zero",
            r"Zero product property: $ab = 0 \Rightarrow a = 0$ or $b = 0$",
        ),
        (r"^Factor\b", "Factoring"),
        (
            r"^Quadratic formula",
            r"Quadratic formula: $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$",
        ),
        (r"^Discriminant", r"Discriminant: $b^2 - 4ac$"),
        (r"^Use the zero-exponent law", r"Zero exponent: $a^0 = 1$ for $a \ne 0$"),
        (r"^Equal bases", r"Equal bases: $a^m = a^n \Rightarrow m = n$"),
        (r"^Write\b.*\bas a power of", "Rewrite with the same base"),
        (r"^Combine logarithms", r"Product rule for logs: $\log a + \log b = \log(ab)$"),
        (
            r"^Convert to exponential form",
            r"Definition of a logarithm: $\log_b y = x \Leftrightarrow b^x = y$",
        ),
        (
            r"^Split the absolute-value equation",
            r"Absolute value: $|u| = k \Rightarrow u = k$ or $u = -k$",
        ),
        (r"^Check\b", "Substitute back into the original equation"),
        # Calculus
        (r"^Product rule", r"Product rule: $(uv)' = u'v + uv'$"),
        (r"^Quotient rule", r"Quotient rule: $\left(\frac{u}{v}\right)' = \frac{u'v - uv'}{v^2}$"),
        (r"^Chain rule", r"Chain rule: $\frac{d}{dx} f(g(x)) = f'(g(x)) \, g'(x)$"),
        (
            r"^Apply integration by parts",
            r"Integration by parts: $\int u \, dv = uv - \int v \, du$",
        ),
        (r"^Choose\b", "Integration by parts: pick the $u$ that gets simpler when differentiated"),
        (
            r"^(?:Let\b|Rewrite the integral in\b|Integrate in\b)",
            r"Substitution: $u = g(x)$, so $du = g'(x) \, dx$",
        ),
        (r"^Put back\b", "Substitution: write the answer in the original variable"),
        # Systems of equations
        (r"^Solve equation \(\d+\) for\b", "Isolate one variable"),
        (
            r"^Substitute into equation\b",
            "Substitution method: replace the variable with its equal",
        ),
        (r"^Substitute\b.*\bback\b", "Substitute the value you found"),
        # Domains and roots
        (r"^Domain restrictions?\b", "Domain: exclude values that make an expression undefined"),
        (r"^Use the real odd-root", r"Odd roots of real numbers are real: $\sqrt[3]{-8} = -2$"),
        (r"^Multiply the numbers", "Multiply before adding (order of operations)"),
    )
)


_POWER_RULE = re.compile(r"^Power rule\b", re.IGNORECASE)
_INEQUALITY = re.compile(r"<|>|\\le\b|\\ge\b|\\leq\b|\\geq\b|\\lt\b|\\gt\b")


def step_rule(label: str, formula: str = "") -> str | None:
    """The named rule a step uses, or None when it is plain arithmetic.

    The same move on an inequality is a property of inequality, not equality.
    """
    text = label.strip()
    if _POWER_RULE.search(text):
        if "\\int" in formula:
            return r"Power rule: $\int x^n \, dx = \frac{x^{n+1}}{n+1} + C$"
        return r"Power rule: $\frac{d}{dx} x^n = n x^{n-1}$"
    for pattern, rule in _RULES:
        if pattern.search(text):
            if _INEQUALITY.search(formula):
                return rule.replace("property of equality", "property of inequality")
            return rule
    return None


def evaluate_powers(*written_sides: Any) -> tuple[str, str] | None:
    """The step for numbers raised to a power the student typed: (label, working).

    The label stays plain text: the phone draws a step badge only when the bold
    heading has no maths in it. One power shows its repeated multiplication,
    ``5^{2} = 5 \\cdot 5 = 25``, which the lesson splits one ``=`` per line.
    """
    shown: list[str] = []
    for side in written_sides:
        for node in preorder_traversal(side):
            if not _typed_power(node):
                continue
            value = latex(node.doit())
            repeated = (
                r" \cdot ".join([latex(node.base)] * int(node.exp))
                if node.exp.is_Integer and 1 < int(node.exp) <= _SHOW_REPEATED and node.base >= 0
                else None
            )
            tex = (
                f"{latex(node)} = {value}"
                if repeated is None
                else f"{latex(node)} = {repeated} = {value}"
            )
            if tex not in shown:
                shown.append(tex)
    if not shown:
        return None
    if len(shown) == 1:
        return "Evaluate the power", shown[0]
    # Several statements on one line; split_equality_chain leaves a ``\quad`` line whole.
    return "Evaluate the powers", r",\quad ".join(
        part.split(" = ")[0] + " = " + part.split(" = ")[-1] for part in shown
    )


def with_powers_evaluated(written_tex: str, side: Any) -> str:
    """The typed side with each number's power swapped for its value: ``2(x + 9)``.

    The swap is on the typed LaTeX. Rebuilding the expression lets SymPy
    distribute and reorder (``18 + 2x``), which hides the next step.
    """
    out = written_tex
    powers = {node for node in preorder_traversal(side) if _typed_power(node)}
    for node in sorted(powers, key=lambda power: -len(latex(power))):
        pattern = r"(?<![\d.])" + re.escape(str(latex(node)))
        value = str(latex(node.doit()))
        out = re.sub(pattern, value.replace("\\", r"\\"), out)
    return out


_MAX_CHECKED_ROOTS = 4


def substitution_check(
    written_left_tex: str,
    written_right_tex: str,
    lhs: Any,
    rhs: Any,
    variable: str,
) -> str | None:
    """Each answer put back into the equation as typed, worked to a true line.

    ``2(x + 3) = 14`` with ``x = 4`` checks as ``2(4 + 3) = 14``, then
    ``14 = 14``. Several answers each get a "For x = …" line. Lines are joined
    with newlines; the lesson draws one per row. None when a root is not exact.
    The swap is on the typed LaTeX: rebuilding the expression would reorder it
    and evaluate the 5² the student wrote.
    """
    var = next(
        (s for s in getattr(lhs - rhs, "free_symbols", set()) if str(s) == variable),
        Symbol(variable),
    )
    with sympy_decline() as declined:
        roots = solve(Eq(lhs, rhs), var)
    if declined or not roots or len(roots) > _MAX_CHECKED_ROOTS:
        return None
    letter = re.compile(rf"(?<![A-Za-z\\]){re.escape(variable)}(?![A-Za-z])")
    lines: list[str] = []
    for root in roots:
        if not getattr(root, "is_number", False):
            return None
        with sympy_decline() as declined:
            left_value = simplify(lhs.subs(var, root))
            right_value = simplify(rhs.subs(var, root))
            exact = simplify(left_value - right_value) == 0
        if declined or not exact:
            return None
        if len(roots) > 1:
            lines.append(rf"\text{{For }} {latex(var)} = {latex(root)}:")
        swap = partial(_substituted, root=root)
        left = letter.sub(swap, written_left_tex)
        right = letter.sub(swap, written_right_tex)
        lines.append(f"{left} = {right}")
        lines.append(rf"{latex(left_value)} = {latex(right_value)} \quad \text{{(true)}}")
    return "\n".join(lines)


def _substituted(hit: re.Match[str], root: Any) -> str:
    """``x`` → ``4`` inside ``(x + 3)``; ``(4)`` after a coefficient or before a power.

    A negative number, fraction or root is always bracketed.
    """
    tex = str(latex(root))
    before = hit.string[: hit.start()].rstrip()
    after = hit.string[hit.end() :].lstrip()
    plain = bool(getattr(root, "is_Integer", False)) and root >= 0
    if plain and not (
        before[-1:].isdigit() or before.endswith(("}", ")")) or after.startswith("^")
    ):
        return tex
    return rf"\left({tex}\right)"


def _typed_power(node: Any) -> bool:
    """``5^2`` or ``4^{1/2}``; ``1/2`` (which SymPy holds as ``2^{-1}``) is a fraction."""
    return bool(
        isinstance(node, Pow)
        and node.base.is_Number
        and node.exp.is_Number
        and node.exp.is_positive
        and node.exp != 1
    )
