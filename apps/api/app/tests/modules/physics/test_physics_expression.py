"""Catalog arithmetic: evaluated by walking a checked tree, typeset from the same tree."""

from __future__ import annotations

import math

import pytest

from app.modules.physics.catalog import CATALOG
from app.modules.physics.expression import (
    PHYSICS_NOTATION,
    ExpressionError,
    evaluate,
    parse,
    to_latex,
)
from app.tests.services.law_binding_support import names

_SYMBOLS = {"u": "u", "v": "v", "a": "a", "t": "t", "d": "s", "mu": r"\mu"}


@pytest.mark.parametrize(
    ("expression", "values", "value"),
    [
        ("v - a*t", {"v": 18, "a": 2, "t": 6}, 6.0),
        ("sqrt(v**2 - 2*a*d)", {"v": 20, "a": 2, "d": 50}, math.sqrt(200)),
        ("d/t - a*t/2", {"d": 100, "a": 2, "t": 5}, 15.0),
        ("2*pi*sqrt(d**3/t)", {"d": 4, "t": 1}, 2 * math.pi * 8),
        ("-u + 3", {"u": 1}, 2.0),
    ],
)
def test_evaluate(expression: str, values: dict[str, float], value: float) -> None:
    assert evaluate(expression, values) == pytest.approx(value)


@pytest.mark.parametrize(
    ("expression", "values"),
    [
        ("v/t", {"v": 1, "t": 0}),  # division by zero
        ("sqrt(v)", {"v": -1}),  # no real root
        ("v**0.5", {"v": -4}),  # no real power
    ],
)
def test_a_domain_error_is_a_value_error(expression: str, values: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        evaluate(expression, values)


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "a.b", "a[0]", "lambda: 1", "f(x)", "x if y else z", "True", "a < b"],
)
def test_anything_but_arithmetic_is_refused(expression: str) -> None:
    with pytest.raises(ExpressionError):
        parse(expression)


@pytest.mark.parametrize(
    ("expression", "formula", "substitution", "values"),
    [
        ("v - a*t", "v - a t", r"18 - 2 \times 6", {"v": 18, "a": 2, "t": 6}),
        (
            "sqrt(v**2 - 2*a*d)",
            r"\sqrt{v^{2} - 2 a s}",
            r"\sqrt{20^{2} - 2 \times 2 \times 50}",
            {"v": 20, "a": 2, "d": 50},
        ),
        (
            "(F - mu*m*g)/m",
            r"\frac{F - \mu m g}{m}",
            r"\frac{100 - 0.25 \times 20 \times 9.81}{20}",
            {"F": 100, "mu": 0.25, "m": 20, "g": 9.81},
        ),
        # A negative number after an operator keeps its brackets.
        ("v - a*t", "v - a t", r"-18 - (-2) \times 6", {"v": -18, "a": -2, "t": 6}),
        ("u + a*t", "u + a t", r"3 + (-2) \times 6", {"u": 3, "a": -2, "t": 6}),
    ],
)
def test_the_formula_and_the_substitution_print_the_same_tree(
    expression: str, formula: str, substitution: str, values: dict[str, float]
) -> None:
    assert to_latex(expression, _SYMBOLS) == formula
    assert to_latex(expression, _SYMBOLS, values) == substitution


def test_names_are_the_variables_read() -> None:
    assert names("2*pi*sqrt(d**3/(G*M))", PHYSICS_NOTATION) == {"d", "G", "M"}


def _expressions() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for spec in CATALOG.values():
        if spec.expression is not None:
            found.append((spec.id, spec.expression))
        found.extend((spec.id, v.expression) for v in spec.variants if v.expression is not None)
        if spec.binding is not None:
            found.extend((spec.id, condition) for condition in spec.binding.requires)
    return found


@pytest.mark.parametrize(("operation", "expression"), _expressions())
def test_every_catalog_expression_reads_only_its_declared_variables(
    operation: str, expression: str
) -> None:
    declared = {variable.name for variable in CATALOG[operation].variables}
    assert names(expression, PHYSICS_NOTATION) <= declared, operation
