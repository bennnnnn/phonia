"""The rules: each reads one stated question shape, in order, into an intent."""

from __future__ import annotations

import re

from app.modules.math.match.geometry import pi_value_set
from app.modules.math.response_intent import strip_ask_frame
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.school._parse import _SIDE_ASKED

_N = r"(-?\d+(?:\.\d+)?)"
_DEG = r"\s*(?:°|degrees?|deg)?"
# An angle in degrees. Not "\b": "°" is no word character, so "35°" at the end never met
# one, while "28°F" did. The next word is the angle's noun or the request's own ("and
# explain why", "step by step", "please"), never a noun the degrees describe: "a good
# complement to 35° weather" is no angle question.
_REQUEST_WORD = (
    r"(?:angles?|and|then|please|now|thanks?|thank|quickly|briefly|step|show|explain|just)\b"
)
_DEGREES = rf"\s*(?:°|degrees?|deg)(?![A-Za-z0-9])(?!\s+(?!{_REQUEST_WORD})[A-Za-z])"
_IS = r"\s*(?:of\s+|is\s+|=\s*|:\s*)?"
_UNIT = r"(?:\s*(mm|cm|km|m|in|ft))?"
_POINT = rf"\(\s*{_N}\s*,\s*{_N}\s*\)"
# A point with its label: "the point P(3, 10)", "P'(7, 2)", "(7, 2)".
_LABELLED = rf"(?:the\s+point\s+)?(?:\b[A-Za-z][\'\u2019\u2032]*\s*)?{_POINT}"
# One point and its image under a reflection, in the ways a book states it.
_IMAGE = (
    rf"(?:\bimage\s+of\s+{_LABELLED}\s+(?:is|=|was|will\s+be)\s+{_LABELLED}"
    rf"|{_LABELLED}\s+(?:is|was)\s+(?:reflected|mapped|sent|taken)\s+(?:on)?to\s+{_LABELLED}"
    rf"|\b(?:maps?|takes?|sends?|reflects?|carries)\s+{_LABELLED}\s+(?:on)?to\s+{_LABELLED})"
)
# Every word of a line-of-reflection question, with its two points taken out: "after a
# reflection and then a translation" or "a glide reflection" is another transformation.
_REFLECTION_WORDS = frozenset(
    """
    in a an the reflection reflected reflect reflects image of point is was will be to onto
    into find determine write give state what equation line mirror axis maps map mapped
    takes take taken sends send sent carries carry under its it this that which
    """.split()
)
_REFLECTION_LINE = (
    r"\b(?:(?:line|axis)\s+of\s+(?:the\s+)?reflection|(?:mirror|reflection|reflecting)\s+line)\b"
)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "semicircle",
        re.compile(
            rf"\b(area|perimeter|arc\s+length)\b.*?\bsemi-?circle\b.*?\b(radius|diameter){_IS}{_N}{_UNIT}",
            re.I,
        ),
    ),
    (
        "hemisphere",
        re.compile(
            rf"\b(volume|surface\s+area|curved\s+surface\s+area)\b.*?\bhemisphere\b.*?"
            rf"\b(radius|diameter){_IS}{_N}{_UNIT}",
            re.I,
        ),
    ),
    (
        "circle_from_circumference",
        re.compile(
            rf"\b(radius|diameter|area)\b.*?\bcircle\b.*?\bcircumference{_IS}{_N}{_UNIT}", re.I
        ),
    ),
    (
        "circle_from_area",
        re.compile(
            rf"\b(radius|diameter|circumference)\b.*?\bcircle\b.*?\barea{_IS}{_N}{_UNIT}", re.I
        ),
    ),
    (
        "square_from_diagonal",
        re.compile(rf"\b(area|side|perimeter)\b.*?\bsquare\b.*?\bdiagonal{_IS}{_N}{_UNIT}", re.I),
    ),
    (
        "rhombus",
        re.compile(
            rf"\barea\b.*?\b(?:rhombus|kite)\b.*?\bdiagonals?{_IS}{_N}{_UNIT}\s*(?:and|,)\s*{_N}",
            re.I,
        ),
    ),
    (
        "equilateral",
        re.compile(
            rf"\b(area|height|altitude|perimeter)\b.*?\bequilateral\s+triangle\b.*?"
            rf"\bsides?(?:\s+length)?{_IS}{_N}{_UNIT}",
            re.I,
        ),
    ),
    (
        "cube_diagonal",
        re.compile(
            rf"\bdiagonal\b.*?\bcube\b.*?\b(?:side|edge)(?:\s+length)?{_IS}{_N}{_UNIT}", re.I
        ),
    ),
    (
        "cuboid_diagonal",
        re.compile(
            rf"\bdiagonal\b.*?\b(?:cuboid|box|rectangular\s+(?:prism|box|solid))\b.*?"
            rf"{_N}\s*(?:by|x|\u00d7)\s*{_N}\s*(?:by|x|\u00d7)\s*{_N}{_UNIT}",
            re.I,
        ),
    ),
    (
        "extreme_angle",
        re.compile(
            rf"\btriangle\b.*?\bsides?\s+(?:of\s+|are\s+|measuring\s+)?{_N}\s*,\s*{_N}\s*,?\s*(?:and\s+)?{_N}"
            r".*?\b(largest|biggest|greatest|smallest)\s+angle\b",
            re.I,
        ),
    ),
    (
        "third_angle",
        re.compile(
            rf"\btriangle\b.*?{_N}{_DEG}\s*(?:and|,)\s*{_N}{_DEG}.*?\b(?:third|remaining|missing|other)\s+angle",
            re.I,
        ),
    ),
    (
        "isosceles",
        re.compile(
            rf"\bisosceles\b.*?\b(base|apex|vertex|top)\s+angles?{_IS}{_N}{_DEG}.*?"
            r"\b(apex|vertex|top|base)\s+angles?\b",
            re.I,
        ),
    ),
    # An angle only: "the complement of 0.3" is a probability.
    (
        "supplement",
        re.compile(rf"\bsupplement(?:ary\s+angle)?\s+(?:of|to|for)\s+{_N}{_DEGREES}", re.I),
    ),
    (
        "complement",
        re.compile(rf"\bcomplement(?:ary\s+angle)?\s+(?:of|to|for)\s+{_N}{_DEGREES}", re.I),
    ),
    (
        "polygon_sides",
        re.compile(
            rf"\bhow\s+many\s+sides\b.*?\b(interior|exterior)\s+angles?\s*(?:is|are|of|=|measures?)?"
            rf"\s*{_N}{_DEG}",
            re.I,
        ),
    ),
    (
        "polygon_sides",
        re.compile(
            rf"\b(interior|exterior)\s+angles?\s*(?:is|are|of|=|measures?)?\s*{_N}{_DEG}.*?"
            r"\bhow\s+many\s+sides\b",
            re.I,
        ),
    ),
    (
        "ladder",
        re.compile(
            rf"{_N}\s*(m|ft|metres?|meters?|feet)?\s*(?:long\s+)?ladder\b.*?"
            rf"\b(?:foot|base|bottom)\b.*?{_N}\s*(?:m|ft|metres?|meters?|feet)?\s*(?:away\s+)?from\s+the\s+wall"
            r".*?\b(?:how\s+high|height|how\s+far\s+up|reach)\b",
            re.I,
        ),
    ),
    (
        "circle_equation",
        re.compile(
            rf"\bequation\s+of\s+(?:a|the)\s+circle\b.*?\bcent(?:er|re)\s*(?:at\s+|of\s+)?{_POINT}"
            rf".*?\bradius{_IS}{_N}",
            re.I,
        ),
    ),
    (
        "circle_centre_radius",
        re.compile(
            r"\bcent(?:er|re)\s+and\s+(?:the\s+)?radius\s+of\s+(?:the\s+circle\s+)?(.+=.+)$", re.I
        ),
    ),
    (
        "triangle_vertices",
        re.compile(
            rf"\barea\s+of\s+(?:a|the)\s+triangle\s+(?:with\s+)?(?:vertices|corners|points)\s+(?:at\s+)?"
            rf"{_POINT}\s*,?\s*{_POINT}\s*,?\s*(?:and\s+)?{_POINT}",
            re.I,
        ),
    ),
    (
        "perpendicular_gradient",
        re.compile(
            r"\b(?:gradient|slope)\s+of\s+(?:a|the|any)\s+line\s+(perpendicular|parallel)\s+to\s+"
            r"(?:the\s+line\s+)?y\s*=\s*([^,;?]+)",
            re.I,
        ),
    ),
    # The line of reflection that takes a point to its image is the perpendicular bisector
    # of the two: "the image of P(3, 10) is P'(7, 2); find the line of reflection".
    (
        "reflection_line",
        re.compile(rf"{_IMAGE}.*?{_REFLECTION_LINE}|{_REFLECTION_LINE}.*?{_IMAGE}", re.I),
    ),
    (
        "perpendicular_bisector",
        re.compile(
            rf"\bperpendicular\s+bisector\s+of\s+(?:the\s+(?:line\s+)?(?:segment\s+)?"
            rf"(?:joining|between|from)\s+)?{_POINT}\s*(?:and|to)\s*{_POINT}",
            re.I,
        ),
    ),
)

# Two angles and a side, a side asked: "A = 40 degrees, B = 60 degrees, a = 10, find b".
_ANGLE_GIVEN = re.compile(rf"\b([A-C])\s*=\s*{_N}{_DEG}")
_SIDE_GIVEN = re.compile(rf"\b([a-c])\s*=\s*{_N}")

# Right-triangle trigonometry.
_RIGHT = re.compile(r"\bright(?:[- ]angled?)?\s+triangle\b", re.I)
_SIDE_NAMED = re.compile(rf"\b(opposite|adjacent|hypotenuse)(?:\s+side)?{_IS}{_N}", re.I)
_ANGLE_NAMED = re.compile(rf"\b(?:an?\s+)?angle\s*(?:of\s+|is\s+|=\s*)?{_N}{_DEG}", re.I)
_ASKED_NAMED = re.compile(
    r"\b(?:find|calculate|what\s+is|work\s+out)\s+(?:the\s+)?(?:length\s+of\s+the\s+)?"
    r"(angle|opposite|adjacent|hypotenuse)\b",
    re.I,
)


# A measure the rule did not read to its end: ``10π``, ``10/3``, ``10*2``.
_PI_AFTER = re.compile(r"\s*(?:\u03c0|\\pi\b|pi\b)(?:\s*(mm|cm|km|m|in|ft)\b)?", re.I)
_MORE_AFTER = re.compile(r"\s*(?:[*/^\u00d7\u00b7]|\d|sqrt|\u221a)", re.I)
_PI_OPS = {"circle_from_circumference", "circle_from_area"}


def extract_geometry_measure_intent(cleaned: str) -> MathIntent | None:
    body = " ".join(cleaned.split()).strip().rstrip("?.!")
    if not body or len(body) > 300 or pi_value_set(body):
        return None  # "use π = 22/7": the solvers work with π itself
    for op, pattern in _RULES:
        found = pattern.search(body)
        if found is None:
            continue
        if op == "reflection_line" and not _reflection_read_whole(body):
            return None
        tail = body[found.end() :]
        pi = _PI_AFTER.match(tail)
        if pi is not None:
            # "circumference 10π" is 10π, not 10; the π was once dropped.
            return _pi_intent(op, found, pi.group(1)) if op in _PI_OPS else None
        if _MORE_AFTER.match(tail):
            return None
        return _intent(op, found)
    return _sine_rule_intent(body) or _right_trig_intent(body)


def _reflection_read_whole(body: str) -> bool:
    rest = re.sub(_LABELLED, " ", strip_ask_frame(body), flags=re.IGNORECASE)
    return all(word in _REFLECTION_WORDS for word in re.findall(r"[a-z]+|\d+", rest.lower()))


def _pi_intent(op: str, found: re.Match[str], unit: str | None) -> MathIntent | None:
    """A circle measure given as a multiple of π: ``C = 10π``, ``A = 16π``."""
    asked, number, _unit_before_pi = found.groups()
    if found.group(3) is not None:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op=f"geometry_measure:{op}_pi",
        stats_numbers=[float(number)],
        trial_outcome="|".join(word for word in (asked.lower(), unit) if word),
        operation="solve",
    )


# The group that holds an expression, not a number or a word, for the rules that have one.
_EXPRESSION_GROUP = {"circle_centre_radius": 1, "perpendicular_gradient": 2}


def _intent(op: str, found: re.Match[str]) -> MathIntent | None:
    expression_group = _EXPRESSION_GROUP.get(op)
    numbers: list[float] = []
    words: list[str] = []
    for index, group in enumerate(found.groups(), start=1):
        if group is None or index == expression_group:
            continue
        try:
            numbers.append(float(group))
        except ValueError:
            words.append(group.lower())
    joined = "|".join(words)
    if len(joined) > 24:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op=f"geometry_measure:{op}",
        stats_numbers=numbers,
        trial_outcome=joined or None,
        expr=found.group(expression_group) if expression_group else None,
        operation="solve",
    )


def _sine_rule_intent(body: str) -> MathIntent | None:
    angles = {match.group(1): float(match.group(2)) for match in _ANGLE_GIVEN.finditer(body)}
    sides = {match.group(1): float(match.group(2)) for match in _SIDE_GIVEN.finditer(body)}
    asked = _SIDE_ASKED.search(body)
    if asked is None or len(angles) != 2 or len(sides) != 1:
        return None
    (known_side, known_value), target = next(iter(sides.items())), asked.group(1)
    if known_side.upper() not in angles or target.upper() not in angles or known_side == target:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="geometry_measure:sine_rule",
        stats_numbers=[known_value, angles[known_side.upper()], angles[target.upper()]],
        trial_outcome=f"{known_side}|{target}",
        operation="solve",
    )


def _right_trig_intent(body: str) -> MathIntent | None:
    if not _RIGHT.search(body):
        return None
    asked = _ASKED_NAMED.search(body)
    if asked is None:
        return None
    target = asked.group(1).lower()
    sides = {
        match.group(1).lower(): float(match.group(2))
        for match in _SIDE_NAMED.finditer(body[: asked.start()] + body[asked.end() :])
    }
    angle = _ANGLE_NAMED.search(body)
    if target == "angle":
        if len(sides) != 2:
            return None
        first, second = sorted(sides)
        return MathIntent(
            kind="arithmetic",
            school_op="geometry_measure:right_angle_from_sides",
            stats_numbers=[sides[first], sides[second]],
            trial_outcome=f"{first}|{second}",
            operation="solve",
        )
    if angle is None or len(sides) != 1 or target in sides:
        return None
    (known, value) = next(iter(sides.items()))
    return MathIntent(
        kind="arithmetic",
        school_op="geometry_measure:right_side_from_angle",
        stats_numbers=[float(angle.group(1)), value],
        trial_outcome=f"{known}|{target}",
        operation="solve",
    )
