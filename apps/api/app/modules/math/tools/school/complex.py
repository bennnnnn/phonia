"""Complex-number extractor and verified block."""

from __future__ import annotations

import re
from dataclasses import replace

from app.core.config import Settings
from app.modules.math import match as mtm
from app.modules.math import school as math_school
from app.modules.math.function_names import variable_letters
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.text_match import word_index

# ``i^23`` is a power of the imaginary unit, as in ``(1 + i)/(1 - i)``; read as a
# letter it was left unsimplified behind a verified card.
_POWER_OF_I = re.compile(r"(?<![A-Za-z_])i\s*\^\s*\(?\s*-?\d")
# "and write in the form a + bi:", "in standard form a+bi": the answer's shape, said of
# a complex number. The clause is no part of the expression.
_FORM_CLAUSE = re.compile(
    r"[,;]?[ \t]?(?:\band\s+)?(?:\b(?:write|express|give|leave|put|present)\s+"
    r"(?:it\s+|them\s+|(?:the|your)\s+(?:answer|result)\s+)?)?"
    r"\bin\s+(?:the\s+)?(?:standard\s+|rectangular\s+|cartesian\s+)?form\s+a\s*\+\s*b\s*i\b\s*:?",
    re.IGNORECASE,
)
# "a complex fraction" is a fraction of fractions, not a complex number.
_COMPLEX_WORDS = re.compile(r"\bcomplex\b(?!\s+fractions?\b)|\bimaginary\b", re.IGNORECASE)
# "where i is the imaginary unit": a definition, no part of the expression.
_UNIT_CLAUSE = re.compile(
    r"[,;]?[ \t]?\b(?:where|with|given)\s+i\s*(?:is|=|denotes)\s*(?:the\s+)?"
    r"(?:imaginary\s+unit|√\s*(?:\(\s*)?-\s*1\s*\)?|sqrt\s*\(\s*-\s*1\s*\))",
    re.IGNORECASE,
)
# ``x_i`` is a name with a subscript, never a product with i.
_LONE_I = re.compile(r"(?<![A-Za-z_])i(?![A-Za-z_0-9])")
_SUBSCRIPT_I = re.compile(r"_\s*[{(]?\s*i\b")
# Positive evidence that i is an index or a quantity, not the imaginary unit: a running
# index (for i = 1 to n, Σ, over i, the i-th), a circuit's current or the power it
# dissipates, or an interest rate (P(1 + i)^n grows by a rate i each period).
_INDEX_OR_QUANTITY = re.compile(
    r"\bfor\s+(?:each\s+|every\s+|all\s+)?i\b|\bi\s*=\s*\d|\bover\s+i\b|[Σ∑]"
    r"|\bi(?:\s*-)?\s*th\b|\bith\b"
    r"|\b(?:currents?|circuits?|resistors?|resistances?|ohms?|amperes?|amps?|volts?|voltages?)\b"
    r"|\bdissipat\w*|\bpower\s+(?:loss|lost|consumed|delivered|developed)\b"
    r"|\b(?:interest|rates?|compound\w*|annuit\w*|principal|invest\w*|loans?|deposit\w*)\b"
    r"|\(\s*1\s*[+-]\s*i\s*\)\s*\^\s*(?:\(\s*)?(?:-\s*)?[a-hj-z]"
    r"|\b(?:let|where)\s+i\s+(?:be|is|denotes?)\b(?!\s+(?:the\s+)?imaginary)",
    re.IGNORECASE,
)
# i beside j (or k with them) is a unit vector, never the imaginary unit; so is any i in a
# question about vectors.
_LONE_J = re.compile(r"(?<![A-Za-z_])j(?![A-Za-z_0-9])")
_VECTOR_WORDS = re.compile(r"\bvectors?\b|[îĵ]|\b[ijk]-?hat\b", re.IGNORECASE)


def lone_i(expression: str) -> bool:
    """An i on its own in the expression, not inside a name or under a subscript."""
    return _LONE_I.search(expression) is not None


def without_form_clause(text: str) -> str:
    """The request without "in the form a + bi" or "where i is the imaginary unit": a
    complex answer is printed in that form, and the clause is no part of the expression."""
    return " ".join(_UNIT_CLAUSE.sub(" ", _FORM_CLAUSE.sub(" ", text)).split())


def imaginary_unit_meant(text: str, expression: str) -> bool:
    """A bare i in ``expression`` is the imaginary unit, as it is in every school book.

    It is a unit vector beside j, or in any question about vectors (3i + 4j is never 7i).
    It is a letter on positive evidence: a subscript (``x_i``), a running index ("for
    i = 1 to n", Σ, "the i-th"), a circuit's current, or an interest rate. Otherwise a
    word that names complex numbers or asks for a + bi settles it, and so does nothing."""
    if _LONE_I.search(expression) is None or _SUBSCRIPT_I.search(expression):
        return False
    if _LONE_J.search(expression) or _VECTOR_WORDS.search(text):
        return False
    if _FORM_CLAUSE.search(text) or _COMPLEX_WORDS.search(text):
        return True
    return _INDEX_OR_QUANTITY.search(text) is None


def _complex_op(lower: str) -> str | None:
    if word_index(lower, "modulus") != -1 or word_index(lower, "magnitude") != -1:
        return "modulus"
    if word_index(lower, "argument") != -1 or word_index(lower, "arg") != -1:
        return "argument"
    if word_index(lower, "conjugate") != -1:
        return "conjugate"
    if "polar" in lower:
        return "polar"
    return None


def _extract_complex_intent(cleaned: str) -> MathIntent | None:
    asked = cleaned
    form_asked = _FORM_CLAUSE.search(cleaned) is not None
    cleaned = without_form_clause(cleaned)
    lower = cleaned.lower()
    op = _complex_op(lower)
    has_complex_token = (
        form_asked
        or "complex" in lower
        or "imaginary" in lower
        or "i)" in lower
        or "+ i" in lower
        or "- i" in lower
        or _POWER_OF_I.search(lower) is not None
    )
    if mtm.has_equation(cleaned) and "solve" in lower:
        return None
    expr = cleaned.strip().rstrip("?.!").rstrip()
    # "Expand (x+3i)^2": the requested operation, in complex numbers.
    expanding = op is None and expr.lower().startswith("expand ")
    if expanding:
        expr = expr[len("expand ") :].lstrip()
    while True:
        for prefix in (
            "what is",
            "what's",
            "whats",
            "find",
            "calculate",
            "simplify",
            "evaluate",
            "compute",
            "express",
            "write",
            "modulus of",
            "modulus",
            "magnitude of",
            "magnitude",
            "argument of",
            "argument",
            "arg of",
            "conjugate of",
            "conjugate",
            "polar form of",
            "polar form",
            "polar of",
            "the complex number",
            "complex",
        ):
            if expr.lower().startswith(prefix + " "):
                expr = expr[len(prefix) :].lstrip()
                break
        else:
            break
    # "Simplify 1/i": i is the only letter, so it can only be the imaginary unit.
    if op is None and not has_complex_token and variable_letters(expr) != {"i"}:
        return None
    if op is None and not mtm.looks_like_math_expr(expr):  # "Solve over the complex numbers"
        return None
    if (_LONE_I.search(expr) or _SUBSCRIPT_I.search(expr)) and not imaginary_unit_meant(
        asked, expr
    ):
        return None  # "x_i^2 + 2x_i", "3i + 2j - i", interest at a rate i: not complex
    school_op = op or ("expand" if expanding else "eval")
    return MathIntent(kind="complex", school_op=school_op, expr=expr, operation="solve")


def _verified_block_complex(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.expr:
        return None
    from app.modules.math import formulas as math_formulas

    if intent.school_op == "modulus":
        answer = math_formulas.complex_modulus(intent.expr)
    elif intent.school_op == "argument":
        answer = math_formulas.complex_argument(intent.expr)
    elif intent.school_op == "conjugate":
        answer = math_formulas.complex_conjugate(intent.expr)
    elif intent.school_op == "polar":
        answer = math_formulas.complex_polar(intent.expr)
    else:
        answer = math_school.evaluate_complex(intent.expr, expanded=intent.school_op == "expand")
        if math_school.restates_complex(intent.expr, answer):
            return None  # a card equal to the question certifies nothing
    lines.append(f"Result: {answer}")
    working = _binomial_working(intent.expr) if intent.school_op == "eval" else None
    if working is None:
        return finish_with_answer(lines, answer)

    from app.services.workout import math_line

    lines.append(f"Working: ${working}$ (i^2 = -1)")
    note = "using $i^2 = -1$" if "i^{2}" in working else None
    return replace(
        finish_with_answer(lines, answer),
        worked_reply=f"{math_line(working, note)}\n\n```answer\n{answer}\n```\n",
    )


_PART = r"(-?\d+(?:\.\d+)?)\s*([+-])\s*(\d+(?:\.\d+)?)?\s*i"
_PRODUCT = re.compile(rf"\(\s*{_PART}\s*\)\s*(\*|/)?\s*\(\s*{_PART}\s*\)")


def _complex_tex(real: str, sign: str, imaginary: str | None) -> str:
    return f"{real} {sign} {'' if imaginary in (None, '1') else imaginary}i"


def _binomial_working(expr: str) -> str | None:
    """``(2 + 3i)(1 - i) = 2 - 2i + 3i - 3i^{2}``; a quotient times the conjugate over itself.

    The answer line then reads the result with ``i^2 = -1`` applied.
    """
    match = _PRODUCT.fullmatch(expr.strip())
    if match is None:
        return None
    a, sign_b, b_text, operator, c, sign_d, d_text = match.groups()
    b = float(b_text or 1) * (1 if sign_b == "+" else -1)
    d = float(d_text or 1) * (1 if sign_d == "+" else -1)
    real_a, real_c = float(a), float(c)
    left = _complex_tex(a, sign_b, b_text)
    right = _complex_tex(c, sign_d, d_text)

    def term(value: float, suffix: str) -> str:
        coefficient = f"{abs(value):g}"
        if suffix and coefficient == "1":
            coefficient = ""
        return f"{'-' if value < 0 else '+'} {coefficient}{suffix}"

    if operator == "/":
        conjugate = _complex_tex(c, "-" if sign_d == "+" else "+", d_text)
        top_real, top_imaginary = real_a * real_c + b * d, b * real_c - real_a * d
        bottom = real_c**2 + d**2
        top = f"{top_real:g} {term(top_imaginary, 'i')}"
        return (
            rf"\frac{{{left}}}{{{right}}} \times \frac{{{conjugate}}}{{{conjugate}}} = "
            rf"\frac{{{top}}}{{{real_c:g}^{{2}} + {abs(d):g}^{{2}}}} = \frac{{{top}}}{{{bottom:g}}}"
        )
    expanded = (
        f"{real_a * real_c:g} {term(real_a * d, 'i')} {term(b * real_c, 'i')} "
        f"{term(b * d, 'i^{2}')}"
    )
    collected = f"{real_a * real_c:g} {term(real_a * d + b * real_c, 'i')} {term(-b * d, '')}"
    return f"({left})({right}) = {expanded} = {collected}"
