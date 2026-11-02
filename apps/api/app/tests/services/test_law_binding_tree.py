"""The checked expression as a JSON tree, and the shared cases the phone's evaluator agrees on.

``docs/fixtures/formula_tree_cases.json`` holds trees, values and the server's result
(``null``: no number); ``apps/mobile/lib/formula/tree.ts`` must give the same. To accept
an intended change, regenerate the file:

    UPDATE_FORMULA_TREE_FIXTURE=1 uv run pytest app/tests/services/test_law_binding_tree.py
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import pytest

from app.modules.money.catalog import PRODUCTS, product
from app.services.law_binding.expression import (
    ExpressionError,
    Notation,
    evaluate,
    names,
    parse,
    to_latex,
    to_tree,
)

FIXTURE = Path(__file__).resolve().parents[5] / "docs" / "fixtures" / "formula_tree_cases.json"
_PLAIN = Notation(constants={}, number=lambda value: f"{value:g}")
_ABOUT = (
    "Formula trees and their values, held by the server (apps/api/app/services/law_binding/"
    "expression.py, to_tree) and the phone (apps/mobile/lib/formula/tree.ts) to one result; "
    "null is no number. Written by the server test with UPDATE_FORMULA_TREE_FIXTURE=1; see "
    "docs/money.md."
)


def _output(key: str, name: str) -> str:
    """The output's formula as a card sends it: its settings written in, usual values."""
    return next(item.expression for item in product(key).outputs_at() if item.name == name)


# (id, expression, values): the money catalog's formulas, then the language's edges.
_CASES: list[tuple[str, str, dict[str, float]]] = [
    ("loan-payment-1pct", _output("mortgage", "payment"), {"amount": 300000, "rate": 1, "years": 30}),
    ("loan-payment-6pct", _output("mortgage", "payment"), {"amount": 300000, "rate": 6.27, "years": 30}),
    ("loan-payment-zero-rate", _output("mortgage", "payment"), {"amount": 30000, "rate": 0, "years": 5}),
    ("card-months", _output("card", "months"), {"balance": 5000, "apr": 22.8, "payment": 200}),
    ("card-never", _output("card", "months"), {"balance": 5000, "apr": 24, "payment": 100}),
    ("savings-balance", _output("savings", "balance"), {"start": 1000, "deposit": 200, "rate": 4.5, "years": 10}),
    ("savings-zero-rate", _output("savings", "balance"), {"start": 1000, "deposit": 200, "rate": 0, "years": 10}),
    ("neg-sqrt-pi", "-sqrt(x) + pi", {"x": 16}),
    ("trig", "sin(x)*cos(x)", {"x": 0.7}),
    ("division-by-zero", "x/(x - x)", {"x": 3}),
    ("negative-fractional-power", "x**0.5", {"x": -4}),
    ("log-domain", "log(x)", {"x": -1}),
    ("compare-equal", "1 if x == 2 else 0", {"x": 2}),
    ("compare-less-equal", "1 if x <= 2 else 0", {"x": 3}),
    ("car-interest", _output("car", "interest"), {"amount": 32000, "rate": 7.5, "months": 72}),
    ("card-interest", _output("card", "interest"), {"balance": 5000, "apr": 22.8, "payment": 200}),
    ("card-zero-apr", _output("card", "months"), {"balance": 1200, "apr": 0, "payment": 100}),
    ("savings-interest", _output("savings", "interest"), {"start": 10000, "deposit": 500, "rate": 4, "years": 20}),
    # "Compounded quarterly" (2026-10-31): 3000 at 6% for 7 years is 3000·1.015^28.
    ("savings-quarterly", product("savings").outputs_at({"per_year": 4})[0].expression, {"start": 3000, "deposit": 100, "rate": 6, "years": 7}),
]  # fmt: skip


def _value(expression: str, values: dict[str, float]) -> float | None:
    try:
        result = evaluate(expression, values, _PLAIN)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    return result if math.isfinite(result) else None


def _current() -> dict[str, Any]:
    cases = [
        {"id": case, "tree": to_tree(expression), "values": values, "expected": _value(expression, values)}
        for case, expression, values in _CASES
    ]  # fmt: skip
    return {"about": _ABOUT, "cases": cases}


def _stored() -> dict[str, Any]:
    if os.environ.get("UPDATE_FORMULA_TREE_FIXTURE"):
        FIXTURE.write_text(json.dumps(_current(), indent=2) + "\n", encoding="utf-8")
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_stored_cases_are_the_servers() -> None:
    stored, current = _stored(), _current()
    assert [case["id"] for case in stored["cases"]] == [case["id"] for case in current["cases"]]
    for kept, now in zip(stored["cases"], current["cases"], strict=True):
        assert kept["tree"] == now["tree"], kept["id"]
        assert kept["values"] == now["values"], kept["id"]
        if now["expected"] is None:
            assert kept["expected"] is None, kept["id"]
        else:
            assert math.isclose(kept["expected"], now["expected"], rel_tol=1e-12), kept["id"]


def _walk(tree: dict[str, Any], values: dict[str, float]) -> float:
    """A reference walker of the JSON tree: the phone's job, done here to prove the format."""
    if "n" in tree:
        return float(tree["n"])
    if "v" in tree:
        return math.pi if tree["v"] == "pi" else values[tree["v"]]
    if "fn" in tree:
        return getattr(math, tree["fn"], abs)(_walk(tree["a"][0], values))
    op, args = tree["op"], tree["a"]
    if op == "neg":
        return -_walk(args[0], values)
    if op == "if":
        test = args[0]
        left, right = _walk(test["a"][0], values), _walk(test["a"][1], values)
        holds = {">": left > right, ">=": left >= right, "<": left < right}.get(
            test["cmp"], left <= right if test["cmp"] == "<=" else left == right
        )
        return _walk(args[1] if holds else args[2], values)
    left, right = _walk(args[0], values), _walk(args[1], values)
    return {"+": left + right, "-": left - right, "*": left * right}.get(op) or (
        left / right if op == "/" else left**right
    )


@pytest.mark.parametrize("item", [o for p in PRODUCTS for o in p.outputs], ids=lambda o: o.name)
def test_every_catalog_tree_walks_to_the_servers_number(item: Any) -> None:
    owner = next(p for p in PRODUCTS if item in p.outputs)
    values = {name: 1.0 for name in names(item.expression)}
    values.update({"rate": 5.0, "apr": 20.0, "payment": 500.0})
    values = {name: values[name] for name in names(item.expression)}
    assert owner.key
    assert math.isclose(
        _walk(to_tree(item.expression), values), evaluate(item.expression, values, _PLAIN)
    )


@pytest.mark.parametrize(
    ("expression", "values", "expected"),
    [
        ("a if a > 0 else b", {"a": 2, "b": 5}, 2.0),
        ("a if a > 0 else b", {"a": -2, "b": 5}, 5.0),
        ("a if a >= 2 else b", {"a": 2, "b": 5}, 2.0),
        ("a if a < 2 else b", {"a": 2, "b": 5}, 5.0),
        ("(a if a > 1 else b) if b > 0 else 0", {"a": 3, "b": 1}, 3.0),
    ],
)
def test_a_condition_takes_its_branch(
    expression: str, values: dict[str, float], expected: float
) -> None:
    assert evaluate(expression, values, _PLAIN) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "a if a > 0 and b > 0 else b",
        "a if 0 < a < 1 else b",
        "a if a else b",
        "a if a != 0 else b",
        "a < b",
    ],
)
def test_only_one_plain_comparison_may_choose(expression: str) -> None:
    with pytest.raises(ExpressionError):
        parse(expression)


def test_a_condition_typesets_its_general_case() -> None:
    latex = to_latex("a/n if n > 0 else 0", {"a": "A", "n": "n"}, notation=_PLAIN)
    assert latex == r"\frac{A}{n}"


def test_names_leave_out_the_functions_called() -> None:
    assert names("log(1 + r)/sqrt(x) + pi") == frozenset({"r", "x", "pi"})


def test_a_tree_writes_every_node_kind() -> None:
    assert to_tree("-x") == {"op": "neg", "a": [{"v": "x"}]}
    assert to_tree("+x") == {"v": "x"}
    assert to_tree("sqrt(2)") == {"fn": "sqrt", "a": [{"n": 2.0}]}
    assert to_tree("1 if x == 2 else 0") == {
        "op": "if",
        "a": [{"cmp": "==", "a": [{"v": "x"}, {"n": 2.0}]}, {"n": 1.0}, {"n": 0.0}],
    }
