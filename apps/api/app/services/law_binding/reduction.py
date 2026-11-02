"""A substitution worked one step at a time down to its number.

``a = \\frac{27.7778 - 0}{8}`` stops where a student still has arithmetic to do.
This reads the substituted right side (numbers, the four operations, powers,
roots, trig and logs, degrees and π: what solvers write) into the same tree
``expression.py`` walks, and evaluates every innermost operation whose operands
are all numbers, one layer per row:

    \\frac{27.7778 - 0}{8}  →  \\frac{27.7778}{8}  →  3.47222

A number the row wrote keeps its spelling in later rows (``299792458`` never turns
into ``2.99792 \\times 10^{8}``); a worked value is printed as a given is. An angle
stays in degrees, and an inverse sine gives one. Anything outside that grammar
returns None: the caller keeps the row as the solver wrote it.
"""

from __future__ import annotations

import ast
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.services.law_binding.expression import Notation, _latex

_FUNCTIONS = {
    "sin": "sin",
    "cos": "cos",
    "tan": "tan",
    "arcsin": "asin",
    "arccos": "acos",
    "arctan": "atan",
    "ln": "log",
    "exp": "exp",
}
_INVERSE = frozenset({"asin", "acos", "atan"})
_TRIG = frozenset({"sin", "cos", "tan"})
_EVALUATE: dict[str, Callable[[float], float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "exp": math.exp,
    "sqrt": math.sqrt,
    "abs": abs,
}
_FRACTIONS = frozenset({"frac", "tfrac", "dfrac"})
_SPACING = frozenset({"!", ",", ";", ":", " ", "left", "right"})
_MOST_STEPS = 8
_TOKEN = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?|\.\d+)"
    r"|\\(?P<command>[A-Za-z]+|[!,;: ])"
    r"|(?P<symbol>[-+\u2212*/^(){}\[\]|]))"
)
_SCIENTIFIC = re.compile(r"\s*\\times\s*10\^\{?(?P<power>[-\u2212]?\d+)\}?")
_MINUS = "\u2212"
_DEGREE = re.compile(r"\s*\^\s*\{?\s*\\circ\s*\}?")


class _Unreadable(ValueError):
    """The row holds something this reader does not evaluate."""


@dataclass
class _Reading:
    """What the tree's leaves stand for: a written number's spelling, an angle's degrees."""

    spellings: dict[float, str] = field(default_factory=dict)
    angles: dict[str, float] = field(default_factory=dict)

    def angle(self, radians: float) -> ast.Name:
        name = f"angle{len(self.angles)}"
        self.angles[name] = radians
        return ast.Name(id=name, ctx=ast.Load())

    def notation(self, number: Callable[[float], str]) -> Notation:
        return Notation(
            constants={}, number=lambda value: self.spellings.get(value) or number(value)
        )


class _Parser:
    def __init__(self, tex: str, reading: _Reading) -> None:
        self.tex = tex
        self.at = 0
        self.reading = reading

    # Tokens -------------------------------------------------------------------------

    def _peek(self) -> tuple[str, str] | None:
        while True:
            match = _TOKEN.match(self.tex, self.at)
            if match is None:
                if self.tex[self.at :].strip():
                    raise _Unreadable(self.tex[self.at :])
                return None
            kind = match.lastgroup or ""
            value = match.group(kind)
            if kind == "command" and value in _SPACING:
                self.at = match.end()
                continue
            return kind, value

    def _take(self) -> tuple[str, str]:
        token = self._peek()
        if token is None:
            raise _Unreadable("ended early")
        match = _TOKEN.match(self.tex, self.at)
        if match is None:
            raise _Unreadable("ended early")
        self.at = match.end()
        return token

    def _expect(self, symbol: str) -> None:
        if self._take() != ("symbol", symbol):
            raise _Unreadable(f"expected {symbol}")

    def _closing(self, opener: str) -> str:
        return {"(": ")", "{": "}", "[": "]"}[opener]

    # Grammar ------------------------------------------------------------------------

    def read(self) -> ast.expr:
        tree = self._sum()
        if self._peek() is not None:
            raise _Unreadable(self.tex[self.at :])
        return tree

    def _sum(self) -> ast.expr:
        node = self._product()
        while (token := self._peek()) in {("symbol", "+"), ("symbol", "-"), ("symbol", _MINUS)}:
            self._take()
            operator: ast.operator = ast.Add() if token == ("symbol", "+") else ast.Sub()
            node = ast.BinOp(left=node, op=operator, right=self._product())
        return node

    def _product(self) -> ast.expr:
        node = self._signed()
        while (token := self._peek()) is not None:
            if token in {("command", "cdot"), ("command", "times"), ("symbol", "*")}:
                self._take()
                node = ast.BinOp(left=node, op=ast.Mult(), right=self._signed())
            elif token == ("symbol", "/"):
                self._take()
                node = ast.BinOp(left=node, op=ast.Div(), right=self._signed())
            elif self._starts_factor(token):
                # Written side by side: 20^{2} \sin^{2}(30^\circ).
                node = ast.BinOp(left=node, op=ast.Mult(), right=self._power())
            else:
                break
        return node

    def _starts_factor(self, token: tuple[str, str]) -> bool:
        kind, value = token
        if kind == "symbol":
            return value in "({["
        return kind == "number" or (kind == "command" and value not in {"cdot", "times"})

    def _signed(self) -> ast.expr:
        token = self._peek()
        if token in {("symbol", "-"), ("symbol", _MINUS)}:
            self._take()
            following = self._peek()
            if following is not None and following[0] == "number":
                # (-8) is a number, not an operation a row has to do.
                return self._number(self._take()[1], negative=True)
            return ast.UnaryOp(op=ast.USub(), operand=self._signed())
        if token == ("symbol", "+"):
            self._take()
            return self._signed()
        return self._power()

    def _power(self) -> ast.expr:
        node = self._atom()
        if self._peek() == ("symbol", "^"):
            self._take()
            node = ast.BinOp(left=node, op=ast.Pow(), right=self._exponent())
        return node

    def _exponent(self) -> ast.expr:
        if self._peek() == ("symbol", "{"):
            self._take()
            node = self._sum()
            self._expect("}")
            return node
        kind, value = self._take()
        if kind != "number" or len(value) != 1:
            raise _Unreadable("exponent")
        return ast.Constant(value=int(value))

    def _group(self) -> ast.expr:
        """``{…}``, or one atom where TeX allows a bare argument (``\\sqrt 2``)."""
        if self._peek() == ("symbol", "{"):
            self._take()
            node = self._sum()
            self._expect("}")
            return node
        return self._atom()

    def _atom(self) -> ast.expr:
        kind, value = self._take()
        if kind == "number":
            return self._number(value)
        if kind == "symbol" and value in "({[":
            node = self._sum()
            self._expect(self._closing(value))
            return node
        if kind == "symbol" and value == "|":
            node = self._sum()
            self._expect("|")
            return self._call("abs", node)
        if kind != "command":
            raise _Unreadable(value)
        if value in _FRACTIONS:
            top = self._group()
            return ast.BinOp(left=top, op=ast.Div(), right=self._group())
        if value == "sqrt":
            return self._call("sqrt", self._group())
        if value == "pi":
            return ast.Name(id="pi", ctx=ast.Load())
        if value in _FUNCTIONS:
            return self._function(_FUNCTIONS[value])
        raise _Unreadable(f"\\{value}")

    def _function(self, name: str) -> ast.expr:
        # \sin^{2}(x) is (\sin x)^2.
        power: ast.expr | None = None
        if self._peek() == ("symbol", "^"):
            self._take()
            power = self._exponent()
        token = self._peek()
        argument = self._atom() if token in {("symbol", "("), ("symbol", "{")} else self._power()
        call = self._call(name, argument)
        return call if power is None else ast.BinOp(left=call, op=ast.Pow(), right=power)

    def _call(self, name: str, argument: ast.expr) -> ast.expr:
        return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=[argument], keywords=[])

    def _number(self, digits: str, *, negative: bool = False) -> ast.expr:
        digits = f"-{digits}" if negative else digits
        spelled = digits
        value = float(digits)
        scientific = _SCIENTIFIC.match(self.tex, self.at)
        if scientific is not None:
            power = int(scientific.group("power").replace(_MINUS, "-"))
            value *= 10.0**power
            spelled = rf"{digits} \times 10^{{{power}}}"
            self.at = scientific.end()
        if (degree := _DEGREE.match(self.tex, self.at)) is not None:
            self.at = degree.end()
            self.reading.spellings.setdefault(value, digits)
            return self.reading.angle(math.radians(value))
        self.reading.spellings.setdefault(value, spelled)
        return ast.Constant(value=value)


# Evaluation -------------------------------------------------------------------------


def _leaf(node: ast.expr) -> bool:
    """A number, or an angle; π stays a symbol until it is worked into a number."""
    return isinstance(node, ast.Constant) or (isinstance(node, ast.Name) and node.id != "pi")


def _is_angle(node: ast.expr, reading: _Reading) -> bool:
    return isinstance(node, ast.Name) and node.id in reading.angles


def _value(node: ast.expr, reading: _Reading) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.Name):
        return math.pi if node.id == "pi" else reading.angles[node.id]
    raise _Unreadable("not a leaf")


def _worked(node: ast.expr, reading: _Reading) -> ast.expr:
    """One operation of leaves, done: a number, or an angle when it gives one."""
    if isinstance(node, ast.UnaryOp):
        value = -_value(node.operand, reading)
        angle = _is_angle(node.operand, reading)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        value = _EVALUATE[node.func.id](_value(node.args[0], reading))
        angle = node.func.id in _INVERSE
        # cos 90° is 0, not the 6.1e-17 floating point leaves.
        if node.func.id in _TRIG and abs(value) < 1e-12:
            value = 0.0
    elif isinstance(node, ast.BinOp):
        left, right = _value(node.left, reading), _value(node.right, reading)
        operations: dict[type[ast.operator], Callable[[float, float], float]] = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b,
            ast.Pow: lambda a, b: a**b,
        }
        value = operations[type(node.op)](left, right)
        angles = (_is_angle(node.left, reading), _is_angle(node.right, reading))
        # 30° · 2 is an angle; sin(30°)² and 30°/30° are not.
        angle = (any(angles) and not all(angles) and isinstance(node.op, ast.Mult | ast.Div)) or (
            all(angles) and isinstance(node.op, ast.Add | ast.Sub)
        )
    else:
        raise _Unreadable("operation")
    if isinstance(value, complex) or not math.isfinite(value):
        raise _Unreadable("no real value")
    return reading.angle(value) if angle else ast.Constant(value=value)


_SUMS = (ast.Add, ast.Sub)


def _number_chain(node: ast.expr, kinds: tuple[type[ast.operator], ...]) -> bool:
    """``a + b - c`` (or ``a · b · c``) of numbers alone: added up in one row, as by hand."""
    if _leaf(node) or _is_pi(node):
        return True
    return (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, kinds)
        and _number_chain(node.left, kinds)
        and _number_chain(node.right, kinds)
    )


def _whole_chain(node: ast.expr, reading: _Reading) -> ast.expr:
    if not isinstance(node, ast.BinOp):
        return node
    left, right = _whole_chain(node.left, reading), _whole_chain(node.right, reading)
    return _worked(ast.BinOp(left=left, op=node.op, right=right), reading)


def _layer(node: ast.expr, reading: _Reading) -> ast.expr:
    """Every operation whose operands are all leaves, done at once; a run of sums or of
    products of numbers alone is one operation."""
    if _leaf(node) or _is_pi(node):
        return node
    if isinstance(node, ast.BinOp) and (
        _number_chain(node, _SUMS) or _number_chain(node, (ast.Mult,))
    ):
        return _whole_chain(node, reading)
    children: list[ast.expr]
    if isinstance(node, ast.UnaryOp):
        children = [node.operand]
    elif isinstance(node, ast.Call):
        children = list(node.args)
    elif isinstance(node, ast.BinOp):
        children = [node.left, node.right]
    else:
        raise _Unreadable("node")
    if all(_leaf(child) or _is_pi(child) for child in children):
        return _worked(node, reading)
    if isinstance(node, ast.UnaryOp):
        operand = _layer(node.operand, reading)
        # -(2 + 3) is -5 in the row that works out 2 + 3, not a row later.
        negated = ast.UnaryOp(op=node.op, operand=operand)
        return _worked(negated, reading) if _leaf(operand) else negated
    if isinstance(node, ast.Call):
        argument = _layer(node.args[0], reading)
        call = ast.Call(func=node.func, args=[argument], keywords=[])
        # |0.42| is 0.42 in the row that works out 0.42, like a sign.
        bars = isinstance(node.func, ast.Name) and node.func.id == "abs"
        return _worked(call, reading) if bars and _leaf(argument) else call
    if not isinstance(node, ast.BinOp):
        raise _Unreadable("node")
    return ast.BinOp(left=_layer(node.left, reading), op=node.op, right=_layer(node.right, reading))


def _is_pi(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "pi"


@dataclass(frozen=True)
class Reduction:
    """The rows after the substitution, and the number they reach."""

    rows: tuple[str, ...]
    value: float
    # The value is an angle, in degrees.
    in_degrees: bool


def reduce_substitution(
    symbol: str, substituted: str, number: Callable[[float], str]
) -> Reduction | None:
    """``\\frac{27.7778 - 0}{8}`` → rows ``a = \\frac{27.7778}{8}`` and the value 3.47222.

    The last layer, the number itself, is not a row: the caller writes the answer
    there as the solver verified it. ``number`` prints a worked value.
    """
    reading = _Reading()
    try:
        tree = _Parser(substituted, reading).read()
        notation = reading.notation(number)
        rows: list[str] = []
        for _ in range(_MOST_STEPS):
            if _leaf(tree):
                break
            tree = _layer(tree, reading)
            if not _leaf(tree):
                shown = _latex(tree, {}, reading.angles, notation, frozenset(reading.angles))
                rows.append(f"{symbol} = {shown}")
        else:
            return None
        if _is_pi(tree):
            return None
        degrees = _is_angle(tree, reading)
        value = _value(tree, reading)
    except (_Unreadable, ValueError, ZeroDivisionError, OverflowError, KeyError):
        return None
    return Reduction(
        rows=tuple(rows), value=math.degrees(value) if degrees else value, in_degrees=degrees
    )
