"""A message that is only an algebra expression: "3x", "3x + 2", "x^2 + 3x + 2".

"3x" was answered "3 times 3 is 9", "4x" "4 times 4 is 16" and "3x+2" "3 times 2 plus 2 is 8"
(2026-10-24): no rule read an expression with no instruction as maths, so the model got it
bare and guessed. The server now answers it itself: what the expression means (a number
written right before a letter multiplies it), its value for an example x, and what the user
can ask next, each in words the maths engine solves ("3x when x = 4", "3x = 12", "graph
y = 3x", "factor x^2 + 3x + 2").

An expression has a digit or an operator besides its letters, and its letters are
variables: x, y or z, or any lowercase letter in a sum or product with an operator ("a +
b", "2n + 1"). "4K", "5G", "3D", "A4", "B12", "x86", "4x4", "2x4", "5k", "3pm", "co2"
and a lone "x" are not expressions; nor is anything with i or e, which are numbers
("i^2" is the maths engine's). No SymPy: the example is whole-number arithmetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from app.services.md_fence_scan import has_closed_fence, without_fences
from app.services.text_normalize import collapse_ws
from app.services.times_sign import with_times

# "What is 3x", "what does 3x mean", "meaning of 3x", "3x meaning".
_LEAD_IN = re.compile(
    r"^(?:what\s+is|what's|whats|what\s+does|meaning\s+of|explain)\s+(?:the\s+meaning\s+of\s+)?",
    re.IGNORECASE,
)
_TAIL = re.compile(r"\s+(?:mean|means|meaning)$", re.IGNORECASE)
# Superscript powers, the minus sign, the times sign and the middle dot, typed as they read.
_SUPERSCRIPTS = str.maketrans(
    {"\u00b2": "^2", "\u00b3": "^3", "\u2212": "-", "\u00d7": "*", "\u00b7": "*"}
)
_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([a-zA-Z]+)|([-+*/^()]))")
_XYZ = frozenset("xyz")
_CONSTANTS = frozenset("ie")
# Values the example gives the variables, in the order they first appear.
_EXAMPLE_VALUES = (4, 2, 3)
_MAX_POWER = 6
_MAX_VALUE = 10**9
# A maths question the last reply asked: "3x" after "What is 2x + x?" is the user's answer.
_QUESTION = re.compile(r"[^.!?\n]*\?")
_MATH_ASK = re.compile(
    r"\d|[=+*/^]|\b(?:simplify|solve|factor|expand|evaluate|calculate|work\s+out|answer)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Num:
    value: Fraction
    text: str


@dataclass(frozen=True)
class _Var:
    name: str


@dataclass(frozen=True)
class _Op:
    """``+ - * /`` and ``^`` between two parts; ``implicit`` for "3x", "2(x + 1)"."""

    op: str
    left: _Node
    right: _Node
    implicit: bool = False


@dataclass(frozen=True)
class _Neg:
    part: _Node


@dataclass(frozen=True)
class _Group:
    part: _Node


_Node = _Num | _Var | _Op | _Neg | _Group


class _NotAnExpression(Exception):
    pass


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.at = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise _NotAnExpression
        self.at += 1
        return token

    def sum(self) -> _Node:
        node = self.product()
        while self.peek() in {("op", "+"), ("op", "-")}:
            _kind, op = self.take()
            node = _Op(op, node, self.product())
        return node

    def product(self) -> _Node:
        node = self.signed()
        while (token := self.peek()) is not None:
            if token in {("op", "*"), ("op", "/")}:
                self.take()
                node = _Op(token[1], node, self.signed())
            elif token[0] == "var" or token == ("op", "("):
                # "3x", "xy", "2(x + 1)", "(x + 1)(x - 1)": written side by side, multiplied.
                node = _Op("*", node, self.power(), implicit=True)
            else:
                break
        return node

    def signed(self) -> _Node:
        if self.peek() == ("op", "-"):
            self.take()
            return _Neg(self.signed())
        return self.power()

    def power(self) -> _Node:
        base = self.atom()
        if self.peek() == ("op", "^"):
            self.take()
            return _Op("^", base, self.signed())
        return base

    def atom(self) -> _Node:
        kind, text = self.take()
        if kind == "num":
            # A number straight after a letter or a bracket ("x86", "x2", "4x4") is no term.
            node: _Node = _Num(Fraction(text), text)
        elif kind == "var":
            node = _Var(text)
        elif text == "(":
            node = _Group(self.sum())
            if self.take() != ("op", ")"):
                raise _NotAnExpression
        else:
            raise _NotAnExpression
        following = self.peek()
        if following is not None and following[0] == "num":
            raise _NotAnExpression
        return node


def _tokens(text: str) -> list[tuple[str, str]] | None:
    tokens: list[tuple[str, str]] = []
    at = 0
    while at < len(text):
        match = _TOKEN.match(text, at)
        if match is None or match.end() == at:
            return None
        number, letter, op = match.groups()
        if number is not None:
            tokens.append(("num", number))
        elif letter is not None:
            # Upper case is a variable only as X, Y or Z: "4K", "5G", "A4" and "B12" are not.
            if any(char.isupper() and char.lower() not in _XYZ for char in letter):
                return None
            # Letters side by side are variables multiplied only as x, y and z ("xy");
            # any other run is a word: "integrate x e^x dx", "sin x", "10k run".
            if len(letter) > 1 and not _XYZ.issuperset(letter.lower()):
                return None
            tokens.extend(("var", char) for char in letter.lower())
        else:
            tokens.append(("op", op))
        at = match.end()
    return tokens


@dataclass(frozen=True)
class BareExpression:
    text: str
    tree: _Node
    variables: tuple[str, ...]


def read_bare_expression(message: str) -> BareExpression | None:
    """The expression a message is, with nothing asked of it; None for anything else."""
    text = collapse_ws(message.translate(_SUPERSCRIPTS)).strip(" ?.!")
    text = _TAIL.sub("", _LEAD_IN.sub("", text)).strip(" ?.!")
    if not text or "=" in text:
        return None
    tokens = _tokens(text)
    if not tokens:
        return None
    letters = [value for kind, value in tokens if kind == "var"]
    # i and e are numbers, not unknowns: "i^2" and "(2+3i)(1-i)" are the maths engine's.
    if _CONSTANTS.intersection(letters):
        return None
    operators = [value for kind, value in tokens if kind == "op" and value not in "()"]
    if not letters or (not any(kind == "num" for kind, _ in tokens) and not operators):
        return None
    if not operators and not _XYZ.intersection(letters):
        # "5k", "3pm", "2b", "4u": a number and a unit or a word, not algebra.
        return None
    parser = _Parser(tokens)
    try:
        tree = parser.sum()
    except _NotAnExpression:
        return None
    if parser.peek() is not None:
        return None
    return BareExpression(_written(tree), tree, tuple(dict.fromkeys(letters)))


def _written(node: _Node) -> str:
    """The expression as LaTeX, spaced: ``3x + 2``, ``x^{2}``, ``2(x + 1)``."""
    if isinstance(node, _Num):
        return node.text
    if isinstance(node, _Var):
        return node.name
    if isinstance(node, _Neg):
        return f"-{_written(node.part)}"
    if isinstance(node, _Group):
        return f"({_written(node.part)})"
    left, right = _written(node.left), _written(node.right)
    if node.op == "^":
        return f"{left}^{{{right}}}"
    if node.implicit:
        return f"{left}{right}"
    if node.op == "*":
        return f"{left} \\cdot {right}"
    if node.op == "/":
        return f"{left} / {right}"
    return f"{left} {node.op} {right}"


def _substituted(node: _Node, values: dict[str, int]) -> str:
    """The expression with each letter's example value: ``3 \\times 4 + 2``."""
    if isinstance(node, _Num):
        return node.text
    if isinstance(node, _Var):
        return str(values[node.name])
    if isinstance(node, _Neg):
        inner = _substituted(node.part, values)
        return f"-({inner})" if isinstance(node.part, _Var) else f"-{inner}"
    if isinstance(node, _Group):
        return f"({_substituted(node.part, values)})"
    left, right = _substituted(node.left, values), _substituted(node.right, values)
    if node.op == "^":
        return f"{left}^{{{right}}}"
    if node.op == "*":
        return f"{left} \\times {right}"
    if node.op == "/":
        return f"{left} \\div {right}"
    return f"{left} {node.op} {right}"


def _value(node: _Node, values: dict[str, int]) -> Fraction:
    if isinstance(node, _Num):
        return node.value
    if isinstance(node, _Var):
        return Fraction(values[node.name])
    if isinstance(node, _Neg):
        return -_value(node.part, values)
    if isinstance(node, _Group):
        return _value(node.part, values)
    left, right = _value(node.left, values), _value(node.right, values)
    if node.op == "^":
        if right.denominator != 1 or not 0 <= right <= _MAX_POWER:
            raise ArithmeticError
        result = left ** int(right)
    elif node.op == "*":
        result = left * right
    elif node.op == "/":
        result = left / right
    elif node.op == "+":
        result = left + right
    else:
        result = left - right
    if abs(result) > _MAX_VALUE:
        raise ArithmeticError
    return result


def _fraction_tex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    sign = "-" if value < 0 else ""
    return f"{sign}\\frac{{{abs(value.numerator)}}}{{{value.denominator}}}"


def _plain(value: Fraction) -> str:
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )


def _example(expression: BareExpression) -> tuple[dict[str, int], Fraction] | None:
    for shift in (0, 1, -2):
        values = {
            name: _EXAMPLE_VALUES[index % len(_EXAMPLE_VALUES)] + shift
            for index, name in enumerate(expression.variables)
        }
        try:
            return values, _value(expression.tree, values)
        except (ArithmeticError, ZeroDivisionError):
            continue
    return None


def _terms(node: _Node) -> list[tuple[str, _Node]] | None:
    """The sum's terms with their signs, or None when it is not a plain sum."""
    if isinstance(node, _Op) and node.op in {"+", "-"}:
        left = _terms(node.left)
        if left is None:
            return None
        return [*left, (node.op, node.right)]
    if isinstance(node, _Neg):
        return [("-", node.part)]
    return [("+", node)]


def _term_words(node: _Node) -> str | None:
    """Words for one term ("3 times x", "x squared", "x divided by 2"); None for a bracket."""
    if isinstance(node, _Num):
        return node.text
    if isinstance(node, _Var):
        return node.name
    if isinstance(node, _Neg):
        words = _term_words(node.part)
        return None if words is None else f"negative {words}"
    if isinstance(node, _Op) and node.op == "^" and isinstance(node.left, _Var):
        if isinstance(node.right, _Num) and node.right.text in {"2", "3"}:
            return f"{node.left.name} {'squared' if node.right.text == '2' else 'cubed'}"
        if isinstance(node.right, _Num):
            return f"{node.left.name} to the power {node.right.text}"
        return None
    if isinstance(node, _Op) and node.op in {"*", "/"}:
        left, right = _term_words(node.left), _term_words(node.right)
        if left is None or right is None:
            return None
        return f"{left} {'times' if node.op == '*' else 'divided by'} {right}"
    return None


def _words(expression: BareExpression) -> str | None:
    terms = _terms(expression.tree)
    if terms is None:
        return None
    spoken = ""
    for index, (sign, term) in enumerate(terms):
        words = _term_words(term)
        if words is None:
            return None
        if index == 0:
            spoken = f"negative {words}" if sign == "-" else words
            continue
        # "3 times x, plus 2" is not 3 times (x plus 2); "a plus b" needs no comma.
        joiner = ", " if " " in spoken.rsplit(", ", 1)[-1] else " "
        spoken += f"{joiner}{'plus' if sign == '+' else 'minus'} {words}"
    return spoken


def _implicit_products(node: _Node) -> list[_Op]:
    """Each product written side by side: "3x", "xy", "2(x + 1)"."""
    if isinstance(node, _Op):
        own = [node] if node.implicit else []
        return own + _implicit_products(node.left) + _implicit_products(node.right)
    if isinstance(node, _Neg | _Group):
        return _implicit_products(node.part)
    return []


def _degree(node: _Node, name: str) -> int:
    """The highest power of one letter in a sum of monomials (0 when it has none)."""
    if isinstance(node, _Var):
        return 1 if node.name == name else 0
    if isinstance(node, _Neg | _Group):
        return _degree(node.part, name)
    if isinstance(node, _Op):
        if node.op == "^" and isinstance(node.right, _Num):
            return _degree(node.left, name) * int(node.right.value)
        if node.op == "*":
            return _degree(node.left, name) + _degree(node.right, name)
        return max(_degree(node.left, name), _degree(node.right, name))
    return 0


def _plain_text(expression: BareExpression) -> str:
    """The expression as the user would type it again: ``x^2 + 3x + 2``."""
    return re.sub(r"\^\{([^{}]*)\}", r"^\1", expression.text).replace(" \\cdot ", " * ")


def _awaits_an_answer(prior_assistant: str | None) -> bool:
    """The last reply asked a maths question (a quiz card, or "What is 2x + x?")."""
    if not prior_assistant:
        return False
    if has_closed_fence(prior_assistant, "quiz"):
        return True
    questions = _QUESTION.findall(without_fences(prior_assistant))
    return bool(questions) and _MATH_ASK.search(questions[-1]) is not None


def bare_expression_reply(message: str, *, prior_assistant: str | None = None) -> str | None:
    """The server's reply to a message that is only an expression, else None. An answer
    to the maths question the last reply asked is the model's to check."""
    expression = read_bare_expression(message)
    if expression is None or _awaits_an_answer(prior_assistant):
        return None
    tex = expression.text
    words = _words(expression)
    lines = [f"**${tex}$** means **{words}**." if words else f"**${tex}$** is an expression."]
    products = _implicit_products(expression.tree)
    brackets = any(isinstance(product.right, _Group) for product in products)
    if any(isinstance(p.left, _Group) and isinstance(p.right, _Group) for p in products):
        lines[0] += " Two brackets written side by side are multiplied."
    elif brackets:
        lines[0] += " Written right before a bracket, a number multiplies everything in it."
    elif products:
        lines[0] += " Written right before a letter, a number multiplies it."
    example = _example(expression)
    typed = _plain_text(expression)
    suggestions: list[str] = []
    if example is not None:
        values, result = example
        given = ", ".join(f"{name} = {value}" for name, value in values.items())
        working = _substituted(expression.tree, values)
        lines += [
            "",
            f"For example, if ${given}$:",
            f"$${with_times(f'{tex} = {working}')} = {_fraction_tex(result)}$$",
        ]
        suggestions.append(f'find its value for a number: "{typed} when {given}"')
        if len(expression.variables) == 1:
            suggestions.append(f'solve an equation: "{typed} = {_plain(result)}"')
    if expression.variables == ("x",):
        suggestions.append(f'graph it: "graph y = {typed}"')
    terms = _terms(expression.tree) or []
    if brackets:
        suggestions.append(f'multiply out the brackets: "expand {typed}"')
    elif len(expression.variables) == 1 and len(terms) > 1:
        if _degree(expression.tree, expression.variables[0]) >= 2:
            suggestions.append(f'factor it: "factor {typed}"')
    lines += ["", "What would you like to do with it? You could:"]
    lines += [f"- {suggestion}" for suggestion in suggestions]
    return "\n".join(lines)
