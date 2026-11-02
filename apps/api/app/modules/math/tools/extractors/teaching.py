"""Whole-request extractors for typed teaching pictures."""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent
from app.modules.math.solve.teaching import build_teaching

_PREFIXES = (
    "please ",
    "show me ",
    "show ",
    "explain ",
    "what is the ",
    "what's the ",
    "whats the ",
    "what is ",
    "what's ",
    "whats ",
    "find the ",
    "find ",
)
_PLACE_DIGIT = re.compile(r"place value of (?:the )?(\d) in (\d+(?:\.\d+)?)$")
_EXPANDED = re.compile(r"(?:(\d+(?:\.\d+)?) in expanded form|expanded form of (\d+(?:\.\d+)?))$")
_BLOCKS = re.compile(r"base[- ]ten blocks (?:for|of) (\d{1,3})$")
_BOND = re.compile(r"(\d{1,2}) = (\d{1,2}) \+ (\d{1,2})$")
_FRAME = re.compile(r"ten frames? (?:for|of) (\d) \+ (\d)$")
_ARRAY = re.compile(r"(?:an? )?(?:equal groups|array) (?:for|of) (\d{1,2}) (?:by|x|\*) (\d{1,2})$")
_FRACTION_LINE = re.compile(r"(\d{1,2})/(\d{1,2}) on (?:a |the )?number line$")
_COMPARE = re.compile(
    r"(?:which is (larger|smaller|bigger|greater)[:,]?|compare) "
    r"(\d+(?:\.\d+)?) (?:or|and) (\d+(?:\.\d+)?)$"
)
_ROUND = re.compile(
    r"round (\d+(?:\.\d+)?) to the nearest "
    r"(thousandths|thousandth|thousands|thousand|hundredths|hundredth|"
    r"hundreds|hundred|tenths|tenth|tens|ten|ones|one)$"
)
_ROUND_NAME = {
    "one": "ones",
    "ones": "ones",
    "tenth": "tenths",
    "tenths": "tenths",
    "hundredth": "hundredths",
    "hundredths": "hundredths",
    "thousandth": "thousandths",
    "thousandths": "thousandths",
    "ten": "tens",
    "tens": "tens",
    "hundred": "hundreds",
    "hundreds": "hundreds",
    "thousand": "thousands",
    "thousands": "thousands",
}
_DIVIDE = re.compile(
    r"(synthetic division|polynomial long division|long division|divide) (?:of )?(.+) by (.+)$"
)
_CIRCLE = re.compile(r"unit circle (?:for|of) (-?\d+)(?: degrees|°)?$")
_BOX = re.compile(r"box(?: and whisker)? plot of ([0-9, .\-]+)$")
_FREQUENCY = re.compile(r"frequency table of ([0-9, .\-]+)$")
_STEM = re.compile(r"stem and leaf (?:of|for) ([0-9, ]+)$")
_HISTOGRAM = re.compile(r"histogram of ([0-9, \-]+)$")
_SCATTER = re.compile(r"scatter plot of (.+)$")
_COIN = re.compile(r"probability tree for (?:a |one )?fair coin$")
_COINS = re.compile(r"probability tree for two fair coin flips$")
_DIE = re.compile(r"probability tree for (?:a |one )?fair (?:die|dice)$")
_TRANSLATE = re.compile(r"translate (?:the )?(?:point |points )?(.+) by (.+)$")
_REFLECT = re.compile(
    r"reflect (?:the )?(?:point |points )?(.+) (?:across|over|in) the (x-axis|y-axis|origin)$"
)
_ROTATE = re.compile(
    r"rotate (?:the )?(?:point |points )?(.+) (90|180|270) degrees "
    r"(?:about|around) the origin$"
)
_DILATE = re.compile(
    r"dilate (?:the )?(?:point |points )?(.+) by (?:a )?scale factor (?:of )?(-?\d+(?:/\d+)?) "
    r"about the origin$"
)
_POINT = re.compile(r"(-?\d+(?:\.\d+)?(?:/\d+)?)\s*,\s*(-?\d+(?:\.\d+)?(?:/\d+)?)")


def closed_teaching_declined(cleaned: str) -> bool:
    """A teaching sentence whose picture is impossible must not become another problem."""
    matched = _matched(cleaned)
    if matched is None:
        return False
    operation, payload = matched
    if build_teaching(operation, payload) is not None:
        return False
    # A signed jump that does not fit the picture is still ordinary arithmetic.
    return operation != "number_line_move"


def extract_teaching_intent(cleaned: str) -> MathIntent | None:
    matched = _matched(cleaned)
    if matched is None or closed_teaching_declined(cleaned):
        return None
    operation, payload = matched
    if build_teaching(operation, payload) is None:
        return None
    fields: dict[str, object] = {
        "kind": "arithmetic",
        "teaching_op": operation,
        "teaching_payload": payload,
        "operation": "solve",
    }
    if operation == "number_line_move":
        start, change = payload.split("|", 1)
        fields["expr"] = f"({start})+({change})"
    return MathIntent.model_validate(fields)


def _matched(cleaned: str) -> tuple[str, str] | None:
    text = _closed(cleaned)
    if not text:
        return None
    return _match(text)


def _closed(text: str) -> str:
    value = " ".join(text.strip().rstrip(".?!").split()).lower().replace("\u00d7", "x")
    for _ in range(3):
        for prefix in _PREFIXES:
            if value.startswith(prefix):
                value = value[len(prefix) :].lstrip()
                break
        else:
            break
    return value


def _match(text: str) -> tuple[str, str] | None:
    if (found := _PLACE_DIGIT.fullmatch(text)) is not None:
        return "place_value", f"{found.group(1)}|{found.group(2)}"
    if (found := _EXPANDED.fullmatch(text)) is not None:
        return "place_value", found.group(1) or found.group(2)
    if (found := _BLOCKS.fullmatch(text)) is not None:
        return "base_ten", found.group(1)
    if (found := _BOND.fullmatch(text)) is not None:
        return "number_bond", f"{found.group(1)}|{found.group(2)}|{found.group(3)}"
    if (found := _FRAME.fullmatch(text)) is not None:
        return "ten_frame", f"{found.group(1)}|{found.group(2)}"
    if (found := _ARRAY.fullmatch(text)) is not None:
        return "array", f"{found.group(1)}|{found.group(2)}"
    if (found := _FRACTION_LINE.fullmatch(text)) is not None:
        return "fraction_line", f"{found.group(1)}|{found.group(2)}"
    if (found := _COMPARE.fullmatch(text)) is not None:
        ask = found.group(1) or "compare"
        if ask in {"bigger", "greater"}:
            ask = "larger"
        return "decimal_compare", f"{found.group(2)}|{found.group(3)}|{ask}"
    if (found := _ROUND.fullmatch(text)) is not None:
        return "round_place", f"{found.group(1)}|{_ROUND_NAME[found.group(2)]}"
    if (found := _DIVIDE.fullmatch(text)) is not None:
        operation = (
            "synthetic_division"
            if found.group(1).startswith("synthetic")
            else "polynomial_division"
        )
        if "x" not in found.group(2) + found.group(3):
            return None
        return operation, f"{found.group(2)}|{found.group(3)}"
    if (found := _CIRCLE.fullmatch(text)) is not None:
        return "unit_circle", found.group(1)
    if (found := _BOX.fullmatch(text)) is not None:
        return "box_plot", _comma_list(found.group(1))
    if (found := _FREQUENCY.fullmatch(text)) is not None:
        return "frequency_table", _comma_list(found.group(1))
    if (found := _STEM.fullmatch(text)) is not None:
        return "stem_leaf", _comma_list(found.group(1))
    if (found := _HISTOGRAM.fullmatch(text)) is not None:
        return "histogram", _comma_list(found.group(1))
    if (found := _SCATTER.fullmatch(text)) is not None:
        points = _encoded_points(found.group(1))
        return None if points is None else ("scatter", points)
    if _COIN.fullmatch(text):
        return "probability_tree", "coin"
    if _COINS.fullmatch(text):
        return "probability_tree", "coins2"
    if _DIE.fullmatch(text):
        return "probability_tree", "die"
    if (found := _TRANSLATE.fullmatch(text)) is not None:
        return _transform("translation", found.group(1), found.group(2))
    if (found := _REFLECT.fullmatch(text)) is not None:
        return _transform("reflection", found.group(1), found.group(2))
    if (found := _ROTATE.fullmatch(text)) is not None:
        return _transform("rotation", found.group(1), found.group(2))
    if (found := _DILATE.fullmatch(text)) is not None:
        return _transform("dilation", found.group(1), found.group(2))
    return None


def _comma_list(value: str) -> str:
    return ",".join(part for part in value.replace(" ", "").split(",") if part)


def _encoded_points(value: str, *, minimum: int = 2) -> str | None:
    found = _POINT.findall(value)
    if not minimum <= len(found) <= 12:
        return None
    return ";".join(f"{x},{y}" for x, y in found)


def _transform(kind: str, points: str, detail: str) -> tuple[str, str] | None:
    encoded = _encoded_points(points, minimum=1) or _encoded_points(f"({points})", minimum=1)
    if kind == "translation":
        shift = _encoded_points(detail, minimum=1) or _encoded_points(f"({detail})", minimum=1)
        if encoded is None or shift is None or ";" in shift:
            return None
        return "transformation", f"translation|{encoded}|{shift}"
    if encoded is None:
        return None
    return "transformation", f"{kind}|{encoded}|{detail}"
