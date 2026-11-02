"""Construct SymPy objects by walking a bounded AST, never eval or sympify strings."""

from __future__ import annotations

import ast
import math
import re
from typing import Any

import sympy as sp

from app.services.solving import SolveServiceError

_FUNCTIONS = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "exp": sp.exp,
    # School notation: ``log`` is base 10 and ``ln`` the natural log, as in math.
    "log": lambda arg: sp.log(arg, 10),
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
}
_CONSTANTS = {"pi": sp.pi, "I": sp.I}
MAX_NODES = 160
MAX_SYMBOLS = 16


class ModelParser:
    """One namespace and domain-condition list for every equation of a request."""

    def __init__(self, dependent: str | None = None, variable: str | None = None) -> None:
        self.symbols: dict[str, Any] = {}
        self.conditions: list[Any] = []
        self.dependent = dependent
        self.variable = variable
        self.source = ""

    def symbol(self, name: str) -> Any:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,23}", name):
            raise SolveServiceError("invalid model symbol")
        if name in _FUNCTIONS or name in _CONSTANTS or re.fullmatch(r"C\d+", name):
            raise SolveServiceError("reserved model symbol")
        if name not in self.symbols:
            if len(self.symbols) >= MAX_SYMBOLS:
                raise SolveServiceError("too many model symbols")
            self.symbols[name] = sp.Symbol(name)
        return self.symbols[name]

    def parse(self, expression: str) -> Any:
        if len(expression) > 512:
            raise SolveServiceError("model expression too long")
        if "#" in expression:
            raise SolveServiceError("comments are not model expressions")
        if self.dependent is not None:
            name = re.escape(self.dependent)
            if re.search(r"\bDerivative(?:One|Two)\b", expression):
                raise SolveServiceError("reserved derivative name")
            expression = re.sub(rf"\b{name}('{{1,2}})(?!')", self._derivative_name, expression)
        try:
            self.source = expression.replace("^", "**")
            tree = ast.parse(self.source, mode="eval").body
        except (SyntaxError, RecursionError) as exc:
            raise SolveServiceError("invalid model expression") from exc
        if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
            raise SolveServiceError("model expression too complex")
        return self._value(tree)

    @staticmethod
    def _derivative_name(match: re.Match[str]) -> str:
        return "DerivativeOne" if len(match[1]) == 1 else "DerivativeTwo"

    def _value(self, node: ast.AST) -> Any:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int | float)
            and not isinstance(node.value, bool)
        ):
            # AST floats are already rounded. Read the original decimal token
            # so an exact stated model cannot silently change before solving.
            token = (ast.get_source_segment(self.source, node) or "").replace("_", "")
            match = re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?", token)
            if match is None or (match[1] is not None and abs(int(match[1])) > 100):
                raise SolveServiceError("only bounded decimal numbers are supported")
            value = sp.Rational(token)
            if not math.isfinite(float(node.value)) or abs(value) > 10**100:
                raise SolveServiceError("model number outside bounds")
            return value
        if isinstance(node, ast.Name):
            if node.id in _CONSTANTS:
                return _CONSTANTS[node.id]
            if self.dependent and node.id in {self.dependent, "DerivativeOne", "DerivativeTwo"}:
                function = sp.Function(self.dependent)(self.symbol(self.variable or "t"))
                order = {self.dependent: 0, "DerivativeOne": 1, "DerivativeTwo": 2}[node.id]
                return sp.diff(function, self.symbol(self.variable or "t"), order)
            return self.symbol(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
            value = self._value(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = self._value(node.left), self._value(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                self.conditions.append(sp.Ne(right, 0))
                return left / right
            if isinstance(node.op, ast.Pow):
                if not right.is_Rational or abs(right) > 16:
                    raise SolveServiceError("only bounded numeric powers are supported")
                if right < 0:
                    self.conditions.append(sp.Ne(left, 0))
                return left**right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FUNCTIONS and len(node.args) == 1 and not node.keywords:
                return _FUNCTIONS[node.func.id](self._value(node.args[0]))
        if isinstance(node, ast.List) and 1 <= len(node.elts) <= 4:
            return [self._value(element) for element in node.elts]
        raise SolveServiceError("unsupported model expression")

    def scalar(self, expression: str) -> Any:
        value = self.parse(expression)
        if not isinstance(value, sp.Expr) or value.has(sp.zoo, sp.nan, sp.oo, -sp.oo):
            raise SolveServiceError("a finite scalar expression is required")
        return value

    def equation(self, expression: str) -> Any:
        sides = expression.split("=")
        if len(sides) != 2:
            raise SolveServiceError("an equation needs exactly one equals sign")
        return self.scalar(sides[0].strip()) - self.scalar(sides[1].strip())

    def vector(self, expression: str) -> Any:
        value = self.parse(expression)
        if not isinstance(value, list) or len(value) != 3:
            raise SolveServiceError("a Cartesian vector needs three components")
        if not all(isinstance(item, sp.Expr) for item in value):
            raise SolveServiceError("vector components must be scalars")
        return sp.Matrix(value)

    def matrix(self, expression: str) -> Any:
        value = self.parse(expression)
        if not isinstance(value, list) or not 2 <= len(value) <= 4:
            raise SolveServiceError("matrix order must be between two and four")
        if not all(isinstance(row, list) and len(row) == len(value) for row in value):
            raise SolveServiceError("a square matrix is required")
        if not all(isinstance(item, sp.Expr) for row in value for item in row):
            raise SolveServiceError("matrix entries must be scalars")
        return sp.Matrix(value)
