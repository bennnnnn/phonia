"""The working line for arithmetic written with factorials: ``6!/4! = 720/24``.

The expression is written once, as the student wrote it, with each factorial
swapped for its value on the right. The result goes in the answer, so the
expression is never written out again on a second row.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

# 13! has ten digits; past 12! a written-out value stops being readable.
_LARGEST_SHOWN = 12
# ``100!/98!`` cancels to ``100 x 99``; a longer product is no shorter to read.
_MOST_CANCELLED_FACTORS = 6

_TOKEN = re.compile(r"\d+|[!+\-*/()]|\S")


@dataclass(frozen=True)
class _Number:
    value: int


@dataclass(frozen=True)
class _Factorial:
    n: int


@dataclass(frozen=True)
class _Group:
    inner: _Node


@dataclass(frozen=True)
class _Operation:
    # ``+ - * /``, or ``" "`` for terms written side by side (``3!5!``).
    op: str
    left: _Node
    right: _Node


_Node = _Number | _Factorial | _Group | _Operation


@dataclass(frozen=True)
class FactorialWorking:
    tex: str
    value: Fraction


class _Unreadable(ValueError):
    pass


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._at = 0

    def parse(self) -> _Node:
        node = self._sum()
        if self._peek() is not None:
            raise _Unreadable
        return node

    def _peek(self) -> str | None:
        return self._tokens[self._at] if self._at < len(self._tokens) else None

    def _take(self) -> str:
        piece = self._peek()
        if piece is None:
            raise _Unreadable
        self._at += 1
        return piece

    def _sum(self) -> _Node:
        node = self._product()
        while self._peek() in ("+", "-"):
            op = self._take()
            node = _Operation(op, node, self._product())
        return node

    def _product(self) -> _Node:
        node = self._term()
        while True:
            piece = self._peek()
            if piece in ("*", "/"):
                self._take()
                node = _Operation(piece, node, self._term())
            elif piece is not None and (piece.isdigit() or piece == "("):
                node = _Operation(" ", node, self._term())
            else:
                return node

    def _term(self) -> _Node:
        piece = self._take()
        node: _Node
        if piece == "(":
            node = _Group(self._sum())
            if self._take() != ")":
                raise _Unreadable
        elif piece.isdigit():
            node = _Number(int(piece))
        else:
            raise _Unreadable
        if self._peek() == "!":
            self._take()
            if not isinstance(node, _Number):
                raise _Unreadable
            node = _Factorial(node.value)
        return node


def _value(node: _Node) -> Fraction:
    if isinstance(node, _Number):
        return Fraction(node.value)
    if isinstance(node, _Factorial):
        return Fraction(math.factorial(node.n))
    if isinstance(node, _Group):
        return _value(node.inner)
    left, right = _value(node.left), _value(node.right)
    if node.op == "+":
        return left + right
    if node.op == "-":
        return left - right
    if node.op == "/":
        if right == 0:
            raise _Unreadable
        return left / right
    return left * right


def _factorials(node: _Node) -> list[int]:
    if isinstance(node, _Factorial):
        return [node.n]
    if isinstance(node, _Group):
        return _factorials(node.inner)
    if isinstance(node, _Operation):
        return _factorials(node.left) + _factorials(node.right)
    return []


def _bare(node: _Node) -> _Node:
    """A bracketed numerator or denominator loses its brackets under a fraction bar."""
    return node.inner if isinstance(node, _Group) else node


def _is_division(node: _Node) -> bool:
    return isinstance(node, _Operation) and node.op == "/"


def _tex(node: _Node, *, values: bool) -> str:
    if isinstance(node, _Number):
        return str(node.value)
    if isinstance(node, _Factorial):
        return str(math.factorial(node.n)) if values else f"{node.n}!"
    if isinstance(node, _Group):
        return rf"\left({_tex(node.inner, values=values)}\right)"
    left = _tex(node.left, values=values)
    if node.op == "/" and not _is_division(node.left) and not _is_division(node.right):
        top = _tex(_bare(node.left), values=values)
        bottom = _tex(_bare(node.right), values=values)
        return rf"\frac{{{top}}}{{{bottom}}}"
    right = _tex(node.right, values=values)
    if node.op == " ":
        # ``3!\,5!`` as written; once they are numbers, ``6 \times 120``.
        return rf"{left} \times {right}" if values else rf"{left}\,{right}"
    symbol = {"+": "+", "-": "-", "*": r"\times", "/": r"\div"}[node.op]
    return f"{left} {symbol} {right}"


def _cancelled(node: _Node) -> str | None:
    """``\\frac{100!}{98!} = 100 \\times 99``: what is left of a quotient of factorials."""
    if not (
        isinstance(node, _Operation)
        and node.op == "/"
        and isinstance(node.left, _Factorial)
        and isinstance(node.right, _Factorial)
    ):
        return None
    top, bottom = node.left.n, node.right.n
    if not 0 < top - bottom <= _MOST_CANCELLED_FACTORS:
        return None
    return r" \times ".join(str(factor) for factor in range(top, bottom, -1))


def factorial_working(expr: str) -> FactorialWorking | None:
    """``\\frac{6!}{4!} = \\frac{720}{24}`` for ``6!/4!``, with its exact value.

    None when the expression has no factorial or is not plain arithmetic on
    whole numbers.
    """
    tokens = _TOKEN.findall(expr)
    if not tokens or len(tokens) > 40:
        return None
    try:
        node = _Parser(tokens).parse()
        value = _value(node)
    except _Unreadable:
        return None
    factorials = _factorials(node)
    if not factorials:
        return None
    written = _tex(node, values=False)
    if max(factorials) <= _LARGEST_SHOWN:
        return FactorialWorking(f"{written} = {_tex(node, values=True)}", value)
    cancelled = _cancelled(node)
    if cancelled is None:
        return None
    return FactorialWorking(f"{written} = {cancelled}", value)
