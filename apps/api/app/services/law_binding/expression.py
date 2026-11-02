"""Evaluate and typeset the arithmetic of an expression operation.

A catalog expression is plain arithmetic in the operation's variable names:
``v - a*t``, ``sqrt(v**2 - 2*a*d)``. It is parsed once into a small tree of
numbers, names, the four operations, powers and a closed list of functions,
and anything else is refused when the catalog loads. Nothing is executed:
the tree is walked. The same tree prints the rearranged formula with the
law's symbols and the substitution with the values the solver used, so the
two can never disagree with the number.

A subject brings its ``Notation``: the constants its expressions may name and how
it prints a number. π is every subject's.

One condition is allowed, ``a if x > 0 else b`` with a single comparison, for a
formula with a special case (a loan at 0% pays amount ÷ months). ``to_tree`` writes
the checked tree as JSON for a client that evaluates it (docs/money.md).
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache

from app.services.times_sign import times

_FUNCTIONS: dict[str, Callable[[float], float]] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "exp": math.exp,
    "log": math.log,
    "abs": abs,
}
_FUNCTION_LATEX = {
    "sin": r"\sin",
    "cos": r"\cos",
    "tan": r"\tan",
    "asin": r"\arcsin",
    "acos": r"\arccos",
    "atan": r"\arctan",
    "log": r"\ln",
}
_PI = "pi"


@dataclass(frozen=True, slots=True)
class Notation:
    """What one subject's expressions may name, and how they print a number."""

    # Constants by the name an expression uses: (value, the symbol the formula shows).
    constants: Mapping[str, tuple[float, str]]
    # A given or working value as the substitution prints it.
    number: Callable[[float], str]

    def constant(self, name: str) -> tuple[float, str] | None:
        if name == _PI:
            return math.pi, r"\pi"
        return self.constants.get(name)


_BINARY = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_UNARY = (ast.USub, ast.UAdd)
_COMPARE: dict[type[ast.cmpop], str] = {
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Eq: "==",
}
_TREE_OPS: dict[type[ast.operator], str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Pow: "^",
}


class ExpressionError(ValueError):
    """A catalog expression uses something this module does not evaluate."""


@lru_cache(maxsize=512)
def parse(expression: str) -> ast.expr:
    """The checked tree of one expression. Raises on anything not arithmetic."""
    try:
        tree = ast.parse(expression, mode="eval").body
    except SyntaxError as exc:
        raise ExpressionError(f"not an expression: {expression}") from exc
    tests = {id(node.test) for node in ast.walk(tree) if isinstance(node, ast.IfExp)}
    for node in ast.walk(tree):
        _check(node, expression)
        if isinstance(node, ast.Compare) and id(node) not in tests:
            raise ExpressionError(f"a comparison only chooses a branch in {expression}")
    return tree


def _check(node: ast.AST, expression: str) -> None:
    if isinstance(node, ast.BinOp | ast.UnaryOp | ast.Name | ast.Load | ast.Call):
        if isinstance(node, ast.BinOp) and not isinstance(node.op, _BINARY):
            raise ExpressionError(f"operator not allowed in {expression}")
        if isinstance(node, ast.UnaryOp) and not isinstance(node.op, _UNARY):
            raise ExpressionError(f"operator not allowed in {expression}")
        if isinstance(node, ast.Call) and not (
            isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and len(node.args) == 1
            and not node.keywords
        ):
            raise ExpressionError(f"call not allowed in {expression}")
        return
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return
    if isinstance(node, ast.operator | ast.unaryop):
        return
    if isinstance(node, ast.IfExp):
        if not (
            isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1
            and type(node.test.ops[0]) in _COMPARE
        ):
            raise ExpressionError(f"a condition is one comparison in {expression}")
        return
    if isinstance(node, ast.Compare | ast.cmpop):
        return
    raise ExpressionError(f"{type(node).__name__} not allowed in {expression}")


def _number(node: ast.Constant) -> float:
    """A literal ``parse`` already checked is an int or a float."""
    if not isinstance(node.value, int | float) or isinstance(node.value, bool):
        raise ExpressionError(f"not a number: {node.value!r}")
    return float(node.value)


def evaluate(expression: str, values: Mapping[str, float], notation: Notation) -> float:
    """The number the expression gives. A domain error is a ValueError."""
    return _value(parse(expression), values, notation)


def _value(node: ast.expr, values: Mapping[str, float], notation: Notation) -> float:
    if isinstance(node, ast.Constant):
        return _number(node)
    if isinstance(node, ast.Name):
        constant = notation.constant(node.id)
        return constant[0] if constant is not None else values[node.id]
    if isinstance(node, ast.UnaryOp):
        operand = _value(node.operand, values, notation)
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _FUNCTIONS[node.func.id](_value(node.args[0], values, notation))
    if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Compare):
        holds = _compares(node.test, values, notation)
        return _value(node.body if holds else node.orelse, values, notation)
    if not isinstance(node, ast.BinOp):
        raise ExpressionError(f"cannot evaluate {type(node).__name__}")
    left, right = _value(node.left, values, notation), _value(node.right, values, notation)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        if right == 0:
            raise ValueError("division by zero")
        return left / right
    result = left**right
    if isinstance(result, complex):
        raise ValueError("no real power")
    return float(result)


def _compares(test: ast.Compare, values: Mapping[str, float], notation: Notation) -> bool:
    left = _value(test.left, values, notation)
    right = _value(test.comparators[0], values, notation)
    sign = _COMPARE[type(test.ops[0])]
    if sign == ">":
        return left > right
    if sign == ">=":
        return left >= right
    if sign == "<":
        return left < right
    if sign == "<=":
        return left <= right
    return left == right


def to_tree(expression: str) -> dict[str, object]:
    """The checked tree as JSON a client evaluates (docs/money.md): never text to parse.

    ``{"n": 2}`` a number, ``{"v": "rate"}`` a name, ``{"op": "+", "a": [l, r]}`` an
    operation (``neg`` for a minus sign), ``{"fn": "log", "a": [x]}`` a function and
    ``{"op": "if", "a": [{"cmp": ">", "a": [l, r]}, then, else]}`` the one condition.
    """
    return _tree(parse(expression))


def _tree(node: ast.expr) -> dict[str, object]:
    if isinstance(node, ast.Constant):
        return {"n": _number(node)}
    if isinstance(node, ast.Name):
        return {"v": node.id}
    if isinstance(node, ast.UnaryOp):
        operand = _tree(node.operand)
        return {"op": "neg", "a": [operand]} if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return {"fn": node.func.id, "a": [_tree(node.args[0])]}
    if isinstance(node, ast.IfExp) and isinstance(node.test, ast.Compare):
        test = node.test
        compared = {
            "cmp": _COMPARE[type(test.ops[0])],
            "a": [_tree(test.left), _tree(test.comparators[0])],
        }
        return {"op": "if", "a": [compared, _tree(node.body), _tree(node.orelse)]}
    if isinstance(node, ast.BinOp):
        return {"op": _TREE_OPS[type(node.op)], "a": [_tree(node.left), _tree(node.right)]}
    raise ExpressionError(f"cannot write {type(node).__name__} as a tree")


def names(expression: str) -> frozenset[str]:
    """Every name the expression reads (``pi`` included), not the functions it calls."""
    tree = parse(expression)
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    return frozenset(
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and id(node) not in called
    )


def to_latex(
    expression: str,
    symbols: Mapping[str, str],
    values: Mapping[str, float] | None = None,
    *,
    notation: Notation,
    degrees: frozenset[str] = frozenset(),
) -> str:
    """The expression typeset: with the law's symbols, or with ``values`` plugged in.

    ``degrees`` names the angles whose values (radians, as the arithmetic needs) are
    shown in degrees: ``\\sin(30^\\circ)``, never ``\\sin(0.523599)``. A result turned
    into degrees by ``*180/pi`` is shown without the turn: the answer states its unit.
    """
    tree = _without_degree_turn(parse(expression))
    return _latex(tree, symbols, values, notation, degrees)


def _without_degree_turn(node: ast.expr) -> ast.expr:
    """``asin(x)*180/pi`` → ``asin(x)``: the radians-to-degrees step is arithmetic, not law."""
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Name)
        and node.right.id == _PI
        and isinstance(node.left, ast.BinOp)
        and isinstance(node.left.op, ast.Mult)
        and isinstance(node.left.right, ast.Constant)
        and _number(node.left.right) == 180
    ):
        return node.left.left
    return node


_PRECEDENCE = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Pow: 4}


def _precedence(node: ast.expr) -> int:
    if isinstance(node, ast.BinOp):
        return _PRECEDENCE[type(node.op)]
    if isinstance(node, ast.UnaryOp):
        return 3
    return 5


def _plugged(node: ast.expr, values: Mapping[str, float] | None) -> bool:
    """A leaf shown as a number: a literal, or a name with a value plugged in."""
    return isinstance(node, ast.Constant) or (
        isinstance(node, ast.Name) and values is not None and node.id != _PI
    )


def _negative_leaf(node: ast.expr, values: Mapping[str, float] | None) -> bool:
    if isinstance(node, ast.Constant):
        return _number(node) < 0
    return (
        isinstance(node, ast.Name)
        and values is not None
        and node.id in values
        and values[node.id] < 0
    )


def _wrapped(
    node: ast.expr,
    symbols: Mapping[str, str],
    values: Mapping[str, float] | None,
    above: int,
    notation: Notation,
    degrees: frozenset[str],
) -> str:
    text = _latex(node, symbols, values, notation, degrees)
    if _precedence(node) < above or (above >= 2 and _negative_leaf(node, values)):
        return f"({text})"
    return text


def _latex(
    node: ast.expr,
    symbols: Mapping[str, str],
    values: Mapping[str, float] | None,
    notation: Notation,
    degrees: frozenset[str] = frozenset(),
) -> str:
    if isinstance(node, ast.Constant):
        return notation.number(_number(node))
    if isinstance(node, ast.Name):
        constant = notation.constant(node.id)
        if constant is not None:
            value, symbol = constant
            # A substitution shows a constant's value, as every solver row does; π stays π.
            return notation.number(value) if values is not None and node.id != _PI else symbol
        if values is not None:
            if node.id in degrees:
                return rf"{notation.number(math.degrees(values[node.id]))}^\circ"
            return notation.number(values[node.id])
        return symbols.get(node.id, node.id)
    if isinstance(node, ast.UnaryOp):
        operand = _wrapped(node.operand, symbols, values, 3, notation, degrees)
        return f"-{operand}" if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.IfExp):
        # The general case is the formula; the special case is arithmetic.
        return _latex(node.body, symbols, values, notation, degrees)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        inner = _latex(node.args[0], symbols, values, notation, degrees)
        name = node.func.id
        if name == "sqrt":
            return rf"\sqrt{{{inner}}}"
        if name == "exp":
            return rf"e^{{{inner}}}"
        if name == "abs":
            return rf"\left|{inner}\right|"
        return f"{_FUNCTION_LATEX[name]}({inner})"
    if not isinstance(node, ast.BinOp):
        raise ExpressionError(f"cannot typeset {type(node).__name__}")
    if isinstance(node.op, ast.Div):
        top = _latex(node.left, symbols, values, notation, degrees)
        bottom = _latex(node.right, symbols, values, notation, degrees)
        return rf"\frac{{{top}}}{{{bottom}}}"
    if isinstance(node.op, ast.Pow):
        base = _wrapped(node.left, symbols, values, 5, notation, degrees)
        # A plugged value in scientific form carries its own power: 6.371e6
        # squared is (6.371 \times 10^{6})^{2}, never 6.371 \times 10^{6}^{2}.
        if (
            _plugged(node.left, values)
            and not base.startswith("(")
            and ("^" in base or "\\times" in base)
        ):
            base = f"({base})"
        return f"{base}^{{{_latex(node.right, symbols, values, notation, degrees)}}}"
    if isinstance(node.op, ast.Mult):
        left = _wrapped(node.left, symbols, values, 2, notation, degrees)
        right = _wrapped(node.right, symbols, values, 2, notation, degrees)
        # Numbers side by side need \\times (``times_sign``), and so does a number before a
        # function ("1 \\times \\sin(30^\\circ)") or a fraction ("5 \\times \\frac{19.62}{7}",
        # never read as the mixed number 5 19.62/7); symbols are written together.
        follows = _leftmost(node.right)
        joined = _plugged(_rightmost(node.left), values) and (
            _plugged(follows, values)
            or (values is not None and isinstance(follows, ast.Call))
            or (values is not None and isinstance(follows, ast.BinOp))
        )
        return times(left, right) if joined else f"{left} {right}"
    operator = "+" if isinstance(node.op, ast.Add) else "-"
    left = _latex(node.left, symbols, values, notation, degrees)
    # a - (b + c) keeps its brackets, and so does a negative number after a sign.
    right = _wrapped(node.right, symbols, values, 2 if operator == "-" else 1, notation, degrees)
    if _negative_leaf(node.right, values):
        right = f"({right})"
    return f"{left} {operator} {right}"


def _leftmost(node: ast.expr) -> ast.expr:
    while isinstance(node, ast.BinOp) and not isinstance(node.op, ast.Div):
        node = node.left
    return node


def _rightmost(node: ast.expr) -> ast.expr:
    while isinstance(node, ast.BinOp) and not isinstance(node.op, ast.Div | ast.Pow):
        node = node.right
    return node
