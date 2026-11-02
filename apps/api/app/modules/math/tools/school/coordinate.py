"""Coordinate geometry extractors and verified blocks, and the SAS triangle area."""

from __future__ import annotations

import re
from dataclasses import replace

from app.core.config import Settings
from app.modules.math import school as math_school
from app.modules.math.match.coordinate_vector import literal_math_tuples
from app.modules.math.response_intent import strip_ask_frame
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import _exactly_n_numbers
from app.services.number_text import DECIMAL_LITERAL, finite_match_value
from app.services.text_match import word_index
from app.services.workout import Workout, math_line, render_workout


def _linear_abc(cleaned: str) -> tuple[float, float, float] | None:
    from sympy import Symbol, diff

    from app.modules.math.solve import try_extract_equation_from_text
    from app.modules.math.solve.parse import parse_expression

    extracted = try_extract_equation_from_text(cleaned)
    if extracted is None:
        return None
    parsed = parse_expression(f"({extracted.lhs})-({extracted.rhs})", ["x", "y"])
    x, y = Symbol("x"), Symbol("y")
    if parsed.free_symbols - {x, y}:
        return None
    if diff(parsed, x, 2) != 0 or diff(parsed, y, 2) != 0 or diff(parsed, x, y) != 0:
        return None
    a = float(parsed.coeff(x))
    b = float(parsed.coeff(y))
    c = float(parsed.subs({x: 0, y: 0}))
    if a == 0 and b == 0:
        return None
    return a, b, c


# A question about two points is read whole: with the points and their labels taken out,
# every word left must belong to the ask. "The line through (1, 2) and (3, 4) is shifted
# 3 units to the right", "the line 2 units above it", "the line through the origin and
# their midpoint" or "its x-intercept" leave words the ask has no place for.
_POINT = re.compile(
    r"(?:\b[A-Za-z][\'\u2019\u2032]?\s*)?\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)"
)
_ASK_WORDS = frozenset(
    """
    a an the find calculate compute determine write give state work out what s is are of and
    points point two segment line straight through thru joining joins join joined passing
    passes pass going goes connecting connects connect containing contains between from to its
    with where whose given if that which coordinates coordinate plane grid on in units unit
    endpoints end ends please explain show working steps step by hint only how why formula
    method briefly me
    """.split()
)
_OP_WORDS = {
    "line": frozenset({"equation"}),
    "distance": frozenset({"distance", "how", "far", "apart", "length"}),
    "midpoint": frozenset({"midpoint", "mid"}),
    "slope": frozenset({"slope", "gradient"}),
}
# The form the card is written in may be asked for; any other form may not.
_CARD_FORM = re.compile(
    r"\bin\s+(?:the\s+)?(?:slope|gradient)[- ]intercept\s+form\b"
    r"|\bin\s+(?:the\s+)?(?:form\s+)?y\s*=\s*mx\s*\+\s*[bc](?:\s+form)?\b",
    re.IGNORECASE,
)
# A line named by its two labelled points: "the line through P and P'", "line AB".
_BY_LABELS = re.compile(
    r"\bline\s+(?:(?:through|thru|joining|connecting|passing\s+through)\s+)?([A-Z])"
    r"[\'\u2019\u2032]?\s*(?:and\s+)?([A-Z])[\'\u2019\u2032]?(?![A-Za-z])"
)
# How a labelled point came to be: "the image of P(3, 10) under reflection in line L is
# P'(7, 2)". The coordinates are stated, so the line through P and P' is that line.
_POINT_STORY = frozenset(
    "image under reflection reflected reflecting rotation rotated translation translated "
    "mapped maps onto mirror".split()
)


def _read_whole(cleaned: str, op: str) -> bool:
    framed = strip_ask_frame(cleaned)
    if op == "line":
        framed = _CARD_FORM.sub(" ", framed)
    labels: list[str] = []

    def blank(point: re.Match[str]) -> str:
        if point.group(0)[0].isalpha():
            labels.append(point.group(0)[0])
        return " "

    rest = _POINT.sub(blank, framed)
    words = _ASK_WORDS | _OP_WORDS[op]
    by_labels = _BY_LABELS.search(rest)
    if op == "line" and by_labels and set(by_labels.groups()) == set(labels):
        words |= _POINT_STORY
    named = "".join(labels).lower()  # "the distance AB" names it by its points
    return all(
        token.lower() in words
        or (len(token) <= 3 and token.isupper())  # labels: "midpoint M", "where A is", "AB"
        or (len(token) > 1 and token.lower() == named)
        for token in re.findall(r"[A-Za-z]+|\d+", rest)
    )


def extract_coord_formulas(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    points = literal_math_tuples(cleaned, "(", ")")
    if any(word_index(lower, word) != -1 for word in ("slope", "gradient", "midpoint")):
        return None
    if points is not None and len(points) == 2 and all(len(pt) == 2 for pt in points):
        if word_index(lower, "distance") != -1:
            return None
        if "line" not in lower and "equation" not in lower:
            return None
        if not _read_whole(cleaned, "line"):
            return None
        (x1, y1), (x2, y2) = (points[0][0], points[0][1]), (points[1][0], points[1][1])
        return MathIntent(
            kind="coord",
            school_op="line",
            point_x=x1,
            point_y=y1,
            x2=x2,
            y2=y2,
            operation="solve",
        )
    if word_index(lower, "distance") == -1:
        return None
    if points is None or len(points) != 1 or len(points[0]) != 2:
        return None
    coeffs = _linear_abc(cleaned)
    if coeffs is None:
        return None
    return MathIntent(
        kind="coord",
        school_op="point_to_line",
        point_x=points[0][0],
        point_y=points[0][1],
        vec_a=[coeffs[0], coeffs[1], coeffs[2]],
        operation="solve",
    )


def _extract_coord_intent(cleaned: str) -> MathIntent | None:
    extra = extract_coord_formulas(cleaned)
    if extra is not None:
        return extra
    lower = cleaned.lower()
    op: str | None = None
    if "distance" in lower or "how far" in lower:
        op = "distance"
    elif "midpoint" in lower:
        op = "midpoint"
    elif "slope" in lower or re.search(r"\bgradient\b", lower):
        # "gradient of the line joining (-1, 4) and (3, -4)" is its slope.
        op = "slope"
    if op is None:
        return None
    # Literal pairs use Euclidean geometry; spherical/geodesic requests
    # require domain information that these operands do not contain.
    if op == "distance" and re.search(r"\b(?:sphere|spherical|geodesic)\b", lower):
        return None
    pts = _two_points(cleaned)
    if pts is None or not _read_whole(cleaned, op):
        return None
    (x1, y1), (x2, y2) = pts
    return MathIntent(
        kind="coord",
        school_op=op,
        point_x=x1,
        point_y=y1,
        x2=x2,
        y2=y2,
        operation="solve",
    )


def _two_points(text: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    found = literal_math_tuples(text, "(", ")")
    if found is None or len(found) != 2 or any(len(point) != 2 for point in found):
        return None
    return (found[0][0], found[0][1]), (found[1][0], found[1][1])


def extract_sas_area(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "area" not in lower or "triangle" not in lower:
        return None
    if "angle" not in lower:
        return None
    if word_index(lower, "sides") == -1 and "included" not in lower:
        return None
    values = _exactly_n_numbers(cleaned, 3)
    if values is None:
        return None
    angle = None
    for cue in ("angle", "included"):
        idx = word_index(lower, cue)
        if idx == -1:
            continue
        after = DECIMAL_LITERAL.search(cleaned, idx)
        if after is not None:
            angle = finite_match_value(after)
            break
    if angle is None:
        return None
    sides = [value for value in values if value != angle]
    if len(sides) != 2:
        return None
    return MathIntent(
        kind="trig",
        school_op="sas_area",
        percent_base=sides[0],
        percent_rate=sides[1],
        point_x=angle,
        operation="solve",
    )


def sas_area_block(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    """The area from two sides and the angle between them; the trig block dispatches here."""
    if intent.percent_base is None or intent.percent_rate is None or intent.point_x is None:
        return None
    from app.modules.math import formulas as math_formulas

    answer = math_formulas.sas_triangle_area(
        intent.percent_base, intent.percent_rate, intent.point_x
    )
    lines.append(f"SAS area = {answer}")
    return finish_with_answer(lines, answer)


def _verified_block_coord(
    intent: MathIntent, settings: Settings, lines: list[str]
) -> VerifiedMathBlock | None:
    from app.modules.math import formulas as math_formulas

    if (
        intent.school_op == "point_to_line"
        and intent.point_x is not None
        and intent.point_y is not None
        and intent.vec_a
        and len(intent.vec_a) == 3
    ):
        answer = math_formulas.point_to_line(
            intent.point_x, intent.point_y, intent.vec_a[0], intent.vec_a[1], intent.vec_a[2]
        )
        lines.append(f"point_to_line: {answer}")
        return finish_with_answer(lines, answer)
    if None in (intent.point_x, intent.point_y, intent.x2, intent.y2):
        return None
    x1, y1, x2, y2 = intent.point_x, intent.point_y, intent.x2, intent.y2
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return None
    if intent.school_op == "line":
        answer = math_formulas.line_through(x1, y1, x2, y2)
    elif intent.school_op == "midpoint":
        answer = math_school.coord_midpoint(x1, y1, x2, y2)
    elif intent.school_op == "slope":
        answer = math_school.coord_slope(x1, y1, x2, y2)
    else:
        answer = math_school.coord_distance(x1, y1, x2, y2)
    lines.append(f"{intent.school_op}: {answer}")
    block = finish_with_answer(lines, answer)
    working = _coordinate_working(intent.school_op or "distance", (x1, y1), (x2, y2), answer)
    return replace(block, worked_reply=working) if working else block


def _coordinate_working(
    op: str, first: tuple[float, float], second: tuple[float, float], answer: str
) -> str | None:
    """The formula, then the two points put into it, for distance, slope and midpoint."""
    from sympy import latex, nsimplify, sqrt

    a, b = (nsimplify(value) for value in first)
    c, d = (nsimplify(value) for value in second)

    def term(value: object) -> str:
        """A negative coordinate is bracketed where it is subtracted or added."""
        tex = str(latex(value))
        return f"\\left({tex}\\right)" if tex.startswith("-") else tex

    given = (
        math_line(f"\\left({latex(a)}, {latex(b)}\\right)", "first point"),
        math_line(f"\\left({latex(c)}, {latex(d)}\\right)", "second point"),
    )
    if op == "distance":
        dx, dy = c - a, d - b
        squares = dx**2 + dy**2
        value = sqrt(squares)
        root = rf"\sqrt{{{latex(squares)}}}"
        # ``\sqrt{25} = 5``; ``\sqrt{34} \approx 5.831`` (no ``\sqrt{34} = \sqrt{34}``).
        exact = "" if latex(value) == root else f" = {latex(value)}"
        shown = exact if value.is_Integer else f"{exact} \\approx {float(value):.4g}"
        formula = math_line(r"d = \sqrt{(x_2 - x_1)^2 + (y_2 - y_1)^2}", "Distance formula")
        substitution: tuple[str, ...] = (
            math_line(
                rf"d = \sqrt{{\left({latex(c)} - {term(a)}\right)^2 + "
                rf"\left({latex(d)} - {term(b)}\right)^2}}"
            ),
            math_line(rf"= \sqrt{{{term(dx)}^2 + {term(dy)}^2}} = {root}{shown}"),
        )
        find = math_line("d", "distance")
    elif op == "slope":
        if c == a:
            return None
        value = (d - b) / (c - a)
        formula = math_line(r"m = \frac{y_2 - y_1}{x_2 - x_1}", "Slope formula")
        ratio = rf"\frac{{{latex(d - b)}}}{{{latex(c - a)}}}"
        reduced = "" if latex(value) == ratio else f" = {latex(value)}"
        substitution = (
            math_line(
                rf"m = \frac{{{latex(d)} - {term(b)}}}{{{latex(c)} - {term(a)}}} = {ratio}{reduced}"
            ),
        )
        find = math_line("m", "slope")
    elif op == "midpoint":
        mx, my = (a + c) / 2, (b + d) / 2
        value = None
        formula = math_line(
            r"M = \left(\frac{x_1 + x_2}{2}, \frac{y_1 + y_2}{2}\right)", "Midpoint formula"
        )
        substitution = (
            math_line(
                rf"M = \left(\frac{{{latex(a)} + {term(c)}}}{{2}}, "
                rf"\frac{{{latex(b)} + {term(d)}}}{{2}}\right) = "
                rf"\left({latex(mx)}, {latex(my)}\right)"
            ),
        )
        find = math_line("M", "midpoint")
        if f"({float(mx):g}, {float(my):g})" != answer:
            return None
    else:
        return None
    worked = {"distance": math_school.coord_distance, "slope": math_school.coord_slope}.get(op)
    if worked is not None and worked(*first, *second) != answer:
        return None
    return render_workout(
        Workout(given=given, find=(find,), formula=(formula,), substitution=substitution),
        answer,
    )
