"""Vector extractors and verified block."""

from __future__ import annotations

import re
from dataclasses import replace

from app.core.config import Settings
from app.modules.math import school as math_school
from app.modules.math.match.coordinate_vector import literal_math_tuples
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.services.text_match import word_index

_ANGLE_BETWEEN_VECTORS = re.compile(
    r"\bangle\s+between\s+(?:the\s+)?(?:two\s+)?vectors\b", re.IGNORECASE
)


def extract_vector_formulas(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    vecs = literal_math_tuples(cleaned, "<", ">") or []
    if not vecs and _ANGLE_BETWEEN_VECTORS.search(cleaned):
        # "angle between the vectors (1,0) and (1,1)": named as vectors, so the
        # round brackets are vectors, not points.
        vecs = literal_math_tuples(cleaned, "(", ")") or []
    if not vecs:
        return None
    if "unit vector" in lower:
        if len(vecs) != 1:
            return None
        return MathIntent(kind="vector", school_op="unit", vec_a=vecs[0], operation="solve")
    if word_index(lower, "projection") != -1 or word_index(lower, "proj") != -1:
        if len(vecs) != 2 or len(vecs[0]) != len(vecs[1]):
            return None
        return MathIntent(
            kind="vector",
            school_op="projection",
            vec_a=vecs[0],
            vec_b=vecs[1],
            operation="solve",
        )
    if word_index(lower, "angle") != -1:
        if len(vecs) != 2 or len(vecs[0]) != len(vecs[1]):
            return None
        return MathIntent(
            kind="vector",
            school_op="angle",
            vec_a=vecs[0],
            vec_b=vecs[1],
            operation="solve",
        )
    return None


def _extract_vector_intent(cleaned: str) -> MathIntent | None:
    extra = extract_vector_formulas(cleaned)
    if extra is not None:
        return extra
    lower = cleaned.lower()
    op: str | None = None
    if "cross" in lower:
        op = "cross"
    elif "dot" in lower:
        op = "dot"
    elif "magnitude" in lower or "norm of" in lower:
        op = "magnitude"
    if op is None:
        return None
    vecs = _angle_vectors(cleaned)
    if not vecs:
        return None
    if op == "magnitude":
        if len(vecs) != 1:
            return None
        return MathIntent(kind="vector", school_op=op, vec_a=vecs[0], operation="solve")
    if len(vecs) != 2 or len(vecs[0]) != len(vecs[1]):
        return None
    return MathIntent(kind="vector", school_op=op, vec_a=vecs[0], vec_b=vecs[1], operation="solve")


def _angle_vectors(text: str) -> list[list[float]]:
    """``<3, 4>``, or ``(3, 4)`` when no angle-bracket vector is written."""
    return literal_math_tuples(text, "<", ">") or literal_math_tuples(text, "(", ")") or []


def _number(value: float) -> str:
    return f"{value:g}"


def _component(value: float) -> str:
    """A component inside a sum of squares or products: ``(-2)``, bare otherwise."""
    return f"\\left({_number(value)}\\right)" if value < 0 else _number(value)


def _vector_working(intent: MathIntent) -> str | None:
    """One working line before the answer.

    ``|v| = \\sqrt{3^2 + 4^2} = \\sqrt{25}``;
    ``a \\cdot b = (1)(4) + (2)(5) + (3)(6) = 4 + 10 + 18``.
    """
    a = intent.vec_a or []
    if intent.school_op == "magnitude":
        squares = " + ".join(f"{_component(value)}^2" for value in a)
        total = sum(value * value for value in a)
        return rf"|\vec{{v}}| = \sqrt{{{squares}}} = \sqrt{{{_number(total)}}}"
    if intent.school_op == "dot" and intent.vec_b:
        products = " + ".join(
            f"({_number(x)})({_number(y)})" for x, y in zip(a, intent.vec_b, strict=True)
        )
        terms = " + ".join(_number(x * y) for x, y in zip(a, intent.vec_b, strict=True))
        return rf"\vec{{a}} \cdot \vec{{b}} = {products} = {terms}".replace("+ -", "- ")
    return None


def _verified_block_vector(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if not intent.vec_a:
        return None
    if intent.school_op == "magnitude":
        answer = math_school.vector_magnitude(intent.vec_a)
    elif intent.school_op == "unit":
        from app.modules.math import formulas as math_formulas

        answer = math_formulas.vector_unit(intent.vec_a)
    elif intent.school_op == "dot" and intent.vec_b:
        answer = math_school.vector_dot(intent.vec_a, intent.vec_b)
    elif intent.school_op == "cross" and intent.vec_b:
        answer = math_school.vector_cross(intent.vec_a, intent.vec_b)
    elif intent.school_op == "angle" and intent.vec_b:
        from app.modules.math import formulas as math_formulas

        answer = math_formulas.vector_angle_degrees(intent.vec_a, intent.vec_b)
    elif intent.school_op == "projection" and intent.vec_b:
        from app.modules.math import formulas as math_formulas

        answer = math_formulas.vector_projection(intent.vec_a, intent.vec_b)
    else:
        return None
    lines.append(f"{intent.school_op}: {answer}")
    working = _vector_working(intent)
    if working is None:
        return finish_with_answer(lines, answer)

    from app.services.workout import math_line

    lines.append(f"Working: ${working}$")
    return replace(
        finish_with_answer(lines, answer),
        worked_reply=f"{math_line(working)}\n\n```answer\n{answer}\n```\n",
    )
