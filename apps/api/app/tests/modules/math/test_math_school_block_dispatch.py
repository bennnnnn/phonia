"""Which arithmetic and trig school block answers an intent, and what happens when it cannot.

An operation whose fields are missing falls through to the expression the intent
carries; one that has them answers alone, even with ``None``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.solve import SolveServiceError
from app.modules.math.tools.school.arithmetic import _verified_block_arithmetic
from app.modules.math.tools.school.trig import _verified_block_trig

_SETTINGS = Settings(math_tools_enabled=True)


def _arithmetic(**fields: Any) -> tuple[Any, list[str]]:
    lines: list[str] = []
    block = _verified_block_arithmetic(MathIntent(kind="arithmetic", **fields), _SETTINGS, lines)
    return block, lines


def _trig(**fields: Any) -> tuple[Any, list[str]]:
    lines: list[str] = []
    block = _verified_block_trig(MathIntent(kind="trig", **fields), _SETTINGS, lines)
    return block, lines


@pytest.mark.parametrize(
    "fields",
    [
        {"school_op": "percent"},
        {"school_op": "ratio_split", "percent_base": 10},
        {"school_op": "mixture", "vec_a": [1.0], "vec_b": [2.0]},
        {"school_op": "sequence_sum", "stats_numbers": [1.0, 2.0]},
        {"school_op": "column_addition", "arithmetic_operands": ["2"]},
        {"school_op": "fraction_add"},
        {"school_op": None},
    ],
)
def test_arithmetic_op_it_cannot_build_evaluates_the_expression(fields: dict[str, Any]) -> None:
    block, lines = _arithmetic(expr="2+3", **fields)
    assert block.canonical_answer == "5"
    assert block.display_answer == "2 + 3 = 5"
    assert lines == ["Result: 5", "Verified result: 5"]


def test_arithmetic_op_with_its_fields_answers_alone() -> None:
    block, lines = _arithmetic(school_op="percent", percent_rate=20, percent_base=50, expr="2+3")
    assert block.canonical_answer == "10"
    assert lines == ["20% of 50 = 10", "Verified result: 10"]
    # A block that declines is the answer: the expression is not tried.
    assert _arithmetic(school_op="change_from_payment", expr="2+3") == (None, [])
    assert _arithmetic(school_op="percent") == (None, [])


def test_arithmetic_written_method_and_expression_tail() -> None:
    written, lines = _arithmetic(school_op="column_addition", expr="12+30")
    assert written.canonical_fences and written.display_answer == "12 + 30 = 42"
    assert lines[0] == "Verified addition procedure:"
    power, _ = _arithmetic(school_op="symbolic_power", expr="x^3")
    assert power.canonical_answer == "x^{3}" and power.direct_reply
    exact, _ = _arithmetic(school_op="eval_exact_decimal", expr="sqrt(2)")
    assert exact.canonical_answer == r"\sqrt{2}" and "1.41421" in exact.direct_reply
    factorial, lines = _arithmetic(school_op="eval", expr="6!/4!")
    assert factorial.worked_reply and lines[0].startswith("Working:")
    undefined, _ = _arithmetic(school_op="eval", expr="5/0")
    assert undefined.display_answer == r"5 ÷ 0 \text{ is undefined}"


def test_trig_bounded_equation_and_its_fall_through() -> None:
    block, lines = _trig(
        school_op="bounded_degree_equation",
        lhs="sin(x)",
        rhs="1/2",
        integral_lower="0",
        integral_upper="360",
        comparator="<=",
        comparator_upper="<=",
    )
    assert block.canonical_answer == r"x = 30^\circ,\;150^\circ"
    assert lines[1] == r"Domain: 0^\circ \le x \le 360^\circ"
    # Without its equation the op reaches the angle reader, which has no such function.
    with pytest.raises(SolveServiceError, match="unsupported trig function"):
        _trig(school_op="bounded_degree_equation", percent_base=30)
    with pytest.raises(SolveServiceError, match="unsupported trig function"):
        _trig(school_op="sas_area", percent_base=30)
    fallback, _ = _trig(school_op="bounded_radian_equation", expr="sin(pi/6)")
    assert fallback.canonical_answer == r"\frac{1}{2}"
    assert _trig() == (None, [])


@pytest.mark.parametrize(
    ("function", "degrees", "answer", "identity", "picture"),
    [
        ("sin", 30, r"\frac{1}{2}", True, True),
        ("sin", 75, r"\frac{\sqrt{2}}{4} + \frac{\sqrt{6}}{4}", True, False),
        ("cos", 15, r"\frac{\sqrt{2}}{4} + \frac{\sqrt{6}}{4}", True, False),
        ("tan", 75, r"\sqrt{3} + 2", False, False),
    ],
)
def test_trig_angle_value_picture_and_angle_sum(
    function: str, degrees: int, answer: str, identity: bool, picture: bool
) -> None:
    block, lines = _trig(school_op=function, percent_base=degrees)
    assert block.canonical_answer == answer
    assert lines[0] == f"{function}({degrees}°) = {answer}"
    assert bool(block.direct_reply) is identity
    assert bool(block.canonical_fences) is picture
    if identity and not picture:
        assert "Angle-sum identity" in block.direct_reply
