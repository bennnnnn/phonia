"""Trigonometry extractor and verified block: interval equations, angles and expressions."""

from __future__ import annotations

import re
from dataclasses import replace

from app.core.config import Settings
from app.modules.math import match as mtm
from app.modules.math import school as math_school
from app.modules.math.function_names import TRIG, function_name_alternation
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.expr_rewrite import math_expr_or_none
from app.modules.math.tools.school.coordinate import extract_sas_area, sas_area_block
from app.modules.math.tools.school.teaching import _attach_picture
from app.modules.math.tools.school.trig_equations import bounded_equation_block
from app.services.number_text import DECIMAL_LITERAL, SIGNED_DECIMAL
from app.services.workout import Workout, math_line, render_workout

# The keypad's trig row: sin, cos, tan and their reciprocals sec, csc, cot.
_TRIG_FUNCS = (
    "sine", "cosine", "tangent", "secant", "cosecant", "cotangent",
    "sin", "cos", "tan", "sec", "csc", "cot",
)  # fmt: skip
_TRIG_CANON = {
    "sine": "sin",
    "cosine": "cos",
    "tangent": "tan",
    "secant": "sec",
    "cosecant": "csc",
    "cotangent": "cot",
}
_TRIG_PREFIXES = (
    "find the exact value of",
    "find exact value of",
    "exact value of",
    "what is",
    "what's",
    "whats",
    "evaluate",
    "compute",
    "calculate",
    "find",
    "the value of",
    "please",
    "can you",
    "could you",
)


_DEGREE_TRIG_CALL = re.compile(
    rf"(?<![A-Za-z])({function_name_alternation(TRIG)})\s*\(\s*({SIGNED_DECIMAL})\s*(?:degrees?|deg|°)\s*\)",
    re.IGNORECASE,
)
_BOUNDED_DEGREE_DOMAIN = re.compile(
    rf"\bfor\s+({SIGNED_DECIMAL})\s*(?:degrees?|deg|°)?\s*(<=|<|≤)\s*"
    rf"([a-zA-Z])\s*(<=|<|≤)\s*({SIGNED_DECIMAL})\s*(?:degrees?|deg|°)"
    rf"(?=\s|[.?!]|$)",
    re.IGNORECASE,
)
_RADIAN_BOUND = (
    r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)?\s*\*?\s*(?:pi|π)"
    r"|[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
)
_BOUNDED_RADIAN_DOMAIN = re.compile(
    rf"\b(?:for|on)\s+({_RADIAN_BOUND})\s*(<=|<|≤)\s*"
    rf"([a-zA-Z])\s*(<=|<|≤)\s*({_RADIAN_BOUND})(?=\s|[.?!]|$)",
    re.IGNORECASE,
)


def _unmarked_degree_bounds(lower: str, upper: str) -> bool:
    """``0 <= x <= 360`` with no degree sign: a bound of 90 or more without pi is degrees.

    No school question asks for the solutions up to 360 radians.
    """
    if any(mark in bound.lower() for bound in (lower, upper) for mark in ("pi", "π")):
        return False
    try:
        return max(abs(float(lower)), abs(float(upper))) >= 90
    except ValueError:
        return False


def _extract_trig_intent(cleaned: str) -> MathIntent | None:
    sas = extract_sas_area(cleaned)
    if sas is not None:
        return sas
    domain = _BOUNDED_DEGREE_DOMAIN.search(cleaned)
    if domain is not None and any(name in cleaned.lower() for name in TRIG):
        from app.modules.math import solve as math_solve

        pairs = math_solve.try_extract_equations_from_text(cleaned)
        if len(pairs) == 1:
            lhs, rhs = pairs[0]
            return MathIntent(
                kind="trig",
                school_op="bounded_degree_equation",
                lhs=lhs,
                rhs=rhs,
                variable=domain.group(3),
                comparator="<=" if domain.group(2) in {"<=", "≤"} else "<",
                comparator_upper="<=" if domain.group(4) in {"<=", "≤"} else "<",
                integral_lower=domain.group(1),
                integral_upper=domain.group(5),
                operation="solve",
            )
    radian_domain = _BOUNDED_RADIAN_DOMAIN.search(cleaned)
    if radian_domain is not None and any(
        name in cleaned.lower() for name in ("sin", "cos", "tan", "sec", "csc", "cot")
    ):
        from app.modules.math import solve as math_solve

        variable = radian_domain.group(3)
        pairs = math_solve.try_extract_equations_from_text(cleaned)
        if len(pairs) == 1:
            lhs, rhs = pairs[0]
        elif "sec" in cleaned.lower() and "undefined" in cleaned.lower():
            lhs, rhs = f"cos({variable})", "0"
        else:
            lhs = rhs = ""
        if lhs and rhs:

            def normalize_bound(value: str) -> str:
                return re.sub(r"(?<=\d)\s*(?=(?:pi|π)\b)", "*", value.replace("π", "pi"))

            bounds = (radian_domain.group(1), radian_domain.group(5))
            return MathIntent(
                kind="trig",
                school_op=(
                    "bounded_degree_equation"
                    if _unmarked_degree_bounds(*bounds)
                    else "bounded_radian_equation"
                ),
                lhs=lhs,
                rhs=rhs,
                variable=variable,
                comparator="<=" if radian_domain.group(2) in {"<=", "≤"} else "<",
                comparator_upper=("<=" if radian_domain.group(4) in {"<=", "≤"} else "<"),
                integral_lower=normalize_bound(radian_domain.group(1)),
                integral_upper=normalize_bound(radian_domain.group(5)),
                operation="solve",
            )
    if mtm.has_equation(cleaned):
        return None
    if mtm.calc_op(cleaned) is not None:
        return None
    expression = cleaned.strip().rstrip(".?!")
    for prefix in _TRIG_PREFIXES:
        if expression.lower().startswith(prefix + " "):
            expression = expression[len(prefix) :].lstrip()
            break
    rewritten, count = _DEGREE_TRIG_CALL.subn(
        lambda match: f"{match.group(1).lower()}(({match.group(2)})*pi/180)",
        expression,
    )
    if count >= 2:
        parsed = math_expr_or_none(rewritten)
        if parsed is not None:
            return MathIntent(
                kind="trig",
                school_op="expression",
                expr=parsed,
                operation="solve",
            )
    # The same complete-expression path for exact radian inputs. Degree calls
    # are handled above because their unit must be converted explicitly;
    # ``pi``/``π`` already denotes radians and needs no per-call special case.
    radian_expression = expression.replace("π", "pi")
    trig_call_count = sum(
        len(re.findall(rf"\b{name}\s*\(", radian_expression, re.IGNORECASE)) for name in _TRIG_FUNCS
    )
    if trig_call_count >= 2 and re.search(r"\bpi\b", radian_expression, re.IGNORECASE):
        parsed = math_expr_or_none(radian_expression)
        if parsed is not None:
            return MathIntent(
                kind="trig",
                school_op="expression",
                expr=parsed,
                operation="solve",
            )
    lower = cleaned.lower()
    padded = f" {lower} "
    func = None
    for name in _TRIG_FUNCS:
        if (
            padded.startswith(f" {name}(")
            or padded.startswith(f" {name} ")
            or f" {name}(" in padded
            or f" {name} " in padded
        ):
            func = name
            break
    if func is None:
        return None
    if "identity" in lower or "law of sines" in lower or "law of cosines" in lower:
        # SSS already covers law of cosines; law of sines needs more sides/angles
        # than we parse here — leave identities to the LLM.
        if "law of sines" in lower:
            return None
        if "identity" in lower:
            return None
    idx = lower.find(func)
    prefix = lower[:idx].strip()
    while prefix:
        for cue in _TRIG_PREFIXES:
            if prefix == cue or prefix.startswith(cue + " "):
                prefix = prefix[len(cue) :].strip()
                break
        else:
            break
    if prefix:
        return None
    rest = cleaned[idx + len(func) :].strip().rstrip(".?!")
    # "sin of 30 degrees" / "sine of 30" — English, not sin(30).
    if rest.lower().startswith("of"):
        rest = rest[2:].lstrip()
    if rest.startswith("("):
        depth = 0
        close = None
        for i, char in enumerate(rest):
            depth += (char == "(") - (char == ")")
            if depth == 0:
                close = i
                break
        if close is None:
            return None
        suffix = rest[close + 1 :].strip()
        if suffix and suffix.lower() not in {
            "degrees",
            "degree",
            "deg",
            "radians",
            "radian",
            "rad",
            "°",
        }:
            # Do not certify the first call after dropping +cos(...) etc.
            return None
        rest = (rest[1:close] + " " + suffix).strip()
    angle_unit = None
    for unit in ("degrees", "degree", "deg", "radians", "radian", "rad", "°"):
        if rest.lower().endswith(unit):
            angle_unit = "degrees" if unit in {"degrees", "degree", "deg", "°"} else "radians"
            rest = rest[: -len(unit)].strip()
            break
    arg = math_expr_or_none(rest)
    if arg is None:
        return None
    canon = _TRIG_CANON.get(func, func)
    numeric = DECIMAL_LITERAL.fullmatch(arg)
    if angle_unit == "degrees" or (angle_unit is None and numeric is not None):
        # Keep the established school shorthand sin 30 = sin(30 degrees).
        return MathIntent(
            kind="trig",
            school_op=canon,
            percent_base=float(arg) if numeric is not None else None,
            expr=f"{canon}(({arg})*pi/180)",
            operation="solve",
        )
    if angle_unit is None and "pi" not in arg and arg != "e":
        return None
    return MathIntent(
        kind="trig",
        school_op=canon,
        expr=f"{canon}({arg})",
        operation="solve",
    )


def _verified_block_trig(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    if (
        intent.school_op in {"bounded_degree_equation", "bounded_radian_equation"}
        and intent.lhs
        and intent.rhs
        and intent.integral_lower is not None
        and intent.integral_upper is not None
    ):
        return bounded_equation_block(
            intent,
            lines,
            lhs_text=intent.lhs,
            rhs_text=intent.rhs,
            lower=intent.integral_lower,
            upper=intent.integral_upper,
        )
    if (
        intent.school_op == "sas_area"
        and intent.percent_base is not None
        and intent.percent_rate is not None
        and intent.point_x is not None
    ):
        return sas_area_block(intent, lines)
    if intent.school_op and intent.percent_base is not None:
        return _angle_value_block(intent, intent.school_op, intent.percent_base, lines)
    if intent.expr:
        answer = math_school.evaluate_trig_expr(intent.expr)
        lines.append(f"Result: {answer}")
        return finish_with_answer(lines, answer)
    return None


def _angle_value_block(
    intent: MathIntent, op: str, degrees: float, lines: list[str]
) -> VerifiedMathBlock:
    """``sin 30°``: the exact value, on the unit circle or by the angle-sum identity."""
    answer = math_school.evaluate_trig_degrees(op, degrees)
    if "exact" in (intent._request_text or "").lower() and intent.expr:
        from sympy import latex, simplify, together

        from app.modules.math import solve as math_solve

        answer = latex(together(simplify(math_solve.parse_expression(intent.expr, []))))
    lines.append(f"{op}({degrees:g}°) = {answer}")
    block = finish_with_answer(lines, answer)
    if op in {"sin", "cos", "tan"} and float(degrees).is_integer():
        from app.modules.math.solve.teaching_algebra import standard_degrees, unit_circle_spec

        angle = int(degrees)
        if standard_degrees(angle) is not None and abs(angle) <= 360:
            circle = unit_circle_spec(angle, answer)
            fields = (
                {"sin": circle.sine, "cos": circle.cosine, "tan": circle.tangent} if circle else {}
            )
            if circle is not None and fields.get(op) == answer:
                return _attach_picture(block, circle, intent, direct=True)
    if op in {"sin", "cos"} and float(degrees).is_integer():
        identity = _angle_sum_identity(block, op, degrees, answer)
        if identity is not None:
            return identity
    return block


def _angle_sum_identity(
    block: VerifiedMathBlock, op: str, degrees: float, answer: str
) -> VerifiedMathBlock | None:
    """``sin 75° = sin(45° + 30°)``, worked by the angle-sum identity over two standard angles."""
    from sympy import cos, latex, pi, simplify, sin

    angle = int(degrees)
    standards = (-90, -60, -45, -30, 30, 45, 60, 90)
    pair = next(
        ((first, second) for first in standards for second in standards if first + second == angle),
        None,
    )
    if pair is not None:
        first, second = pair
        trig = cos if op == "cos" else sin
        sign = "-" if op == "cos" else "+"
        left_first = "cos" if op == "cos" else "sin"
        left_second = "cos"
        right_first = "sin" if op == "cos" else "cos"
        right_second = "sin"
        complementary = sin if op == "cos" else cos
        components = (
            trig(first * pi / 180),
            cos(second * pi / 180),
            complementary(first * pi / 180),
            sin(second * pi / 180),
        )
        signed_second = (
            simplify(components[0] * components[1] - components[2] * components[3])
            if op == "cos"
            else simplify(components[0] * components[1] + components[2] * components[3])
        )
        direct = render_workout(
            Workout(
                given=(math_line(f"{angle}^\\circ = {first}^\\circ + {second}^\\circ"),),
                find=(math_line(f"\\{op}({angle}^\\circ)"),),
                formula=(
                    math_line(
                        f"\\{op}(A + B) = \\{left_first} A\\,\\{left_second} B "
                        f"{sign} \\{right_first} A\\,\\{right_second} B",
                        "Angle-sum identity",
                    ),
                ),
                # One short value per line stays readable on a narrow phone.
                substitution=(
                    math_line(f"\\{left_first}({first}^\\circ)={latex(components[0])}"),
                    math_line(f"\\{left_second}({second}^\\circ)={latex(components[1])}"),
                    math_line(f"\\{right_first}({first}^\\circ)={latex(components[2])}"),
                    math_line(f"\\{right_second}({second}^\\circ)={latex(components[3])}"),
                    math_line(f"\\{op}({angle}^\\circ) = {latex(signed_second)}"),
                ),
            ),
            answer,
        )
        return replace(block, direct_reply=direct)
    return None
