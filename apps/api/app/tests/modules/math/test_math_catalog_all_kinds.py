"""One end-to-end verified example for every public math intent kind."""

from __future__ import annotations

from typing import get_args

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathIntent, WordProblemSetup
from app.modules.math.tools.block import _build_verified_block
from app.modules.math.tools.extract import extract_math_intent

_CASES = [
    ("equation", "solve 2x+3=7", "x = 2", "answer"),
    ("rectangle", "area of rectangle 3 cm by 4 cm", "12", "rectangle"),
    ("square", "area of square with side 5 cm", "25", "square"),
    ("triangle", "area of triangle base 3 cm height 4 cm", "6", "triangle"),
    (
        "right_triangle",
        "Find the hypotenuse of a right triangle legs 3 and 4",
        "5",
        "right_triangle",
    ),
    ("circle", "area of circle radius 3 cm", "28.27", "circle"),
    ("point", "plot point (2,3)", "(2, 3)", "function"),
    ("graph", "graph y=x^2", None, "function"),
    ("vertical", "graph x=4", None, "vertical"),
    ("calculus", "differentiate x^3", "3 x^{2}", "answer"),
    ("limit", "limit of sin(x)/x as x approaches 0", "1", "answer"),
    ("series", "sum 1/n^2 from n=1 to infinity", r"\frac{\pi^{2}}{6}", "answer"),
    ("system", "solve x+y=5; x-y=1", "x = 3, y = 2", "answer"),
    (
        "numerical_method",
        "use newton's method to solve x^2-2=0 starting at 1",
        "1.41421",
        "answer",
    ),
    (
        "inequality",
        "solve x^2-4>0",
        r"x < -2 \text{ or } x > 2",
        "number_line",
    ),
    ("statistics", "mean of 1,2,3,4", "2.5", "answer"),
    ("combinatorics", "5 choose 2", "10", "answer"),
    ("number_theory", "gcd of 12 and 18", "6", "answer"),
    ("matrix", "determinant [[1,2],[3,4]]", "-2", "answer"),
    ("triangle_sides", "area of a triangle with sides 3,4,5", "6", "triangle_sides"),
    (
        "trapezoid",
        "area of a trapezoid with bases 3 cm and 5 cm and height 4 cm",
        "16",
        "trapezoid",
    ),
    (
        "parallelogram",
        "area of parallelogram base 5 cm height 3 cm",
        "15",
        "parallelogram",
    ),
    ("sector", "area of sector radius 3 cm angle 60 degrees", "4.7124", "sector"),
    ("graph_pair", "graph y=x^2 and y=2x", None, "function"),
    ("solid", "volume of cube side 3 cm", r"27\ \mathrm{cm}^{3}", "answer"),
    ("arithmetic", "7*8", "56", "answer"),
    ("trig", "sin(30 degrees)", r"\frac{1}{2}", "answer"),
    ("coord", "distance between (1,2) and (4,6)", "5", "answer"),
    ("vector", "magnitude of <3,4>", "5", "answer"),
    ("probability", "binomial n=5 k=2 p=0.5", "0.3125", "answer"),
    ("complex", "modulus of 3+4i", "5", "answer"),
    ("unit", "convert 1 km to m", r"1000\ \mathrm{m}", "answer"),
    ("work_check", "check my work: 2x+3=11, 2x=8, x=4", "x = 4", "answer"),
]


# Kinds only a structured model translation produces (no regex extractor
# claims them): one prebuilt intent each, still closed by the SymPy builder.
_STRUCTURED_CASES: dict[str, tuple[MathIntent, str]] = {
    "word_problem": (
        MathIntent(
            kind="word_problem",
            operation="solve",
            word_problem=WordProblemSetup.model_validate(
                {
                    "found": True,
                    "unknowns": [{"symbol": "n", "meaning": "the number"}],
                    "equations": [{"equation": "n + 7 = 19"}],
                    "targets": [{"expr": "n", "meaning": "the number"}],
                }
            ),
        ),
        "12",
    ),
}


def test_catalog_has_one_case_for_every_math_intent_kind() -> None:
    declared = set(get_args(MathIntent.model_fields["kind"].annotation))
    covered = {kind for kind, *_ in _CASES} | set(_STRUCTURED_CASES)
    assert covered == declared


@pytest.mark.parametrize("kind", sorted(_STRUCTURED_CASES))
def test_every_structured_kind_builds_a_verified_result(kind: str) -> None:
    intent, answer = _STRUCTURED_CASES[kind]
    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.canonical_answer == answer
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == "answer"


@pytest.mark.parametrize("kind,query,answer,fence_type", _CASES)
def test_every_math_kind_builds_a_verified_result(
    kind: str, query: str, answer: str | None, fence_type: str
) -> None:
    intent = extract_math_intent(query)
    assert intent is not None
    assert intent.kind == kind

    verified = _build_verified_block(intent, Settings(math_tools_enabled=True))
    assert verified is not None
    assert verified.canonical_answer == answer
    assert verified.canonical_fence is not None
    assert verified.canonical_fence["type"] == fence_type
