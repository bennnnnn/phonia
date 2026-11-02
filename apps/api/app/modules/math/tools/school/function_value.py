"""A function's value at a number.

``if f(x) = 2x^2 - 3, find f(4)``, ``f(g(2))`` with two definitions, and the
expression first: ``evaluate 2x^2 - 3 when x = 4``. Read as an equation, the
definition ``f(x) = ...`` used to be solved for ``f``.

The working writes the call once with the value substituted beside it
(``f(4) = 2(4)^{2} - 3 = 32 - 3``) and leaves the result to the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock, finish_with_answer
from app.modules.math.tools.school._parse import request_body
from app.services.workout import math_line

_MAX = 300
_DEFINITION = re.compile(r"(?<![A-Za-z])(?P<name>[a-z])\s*\(\s*(?P<var>[a-z])\s*\)\s*=\s*")
_ASK = r"(?:find|what\s+is|what's|whats|evaluate|calculate|compute|determine|work\s+out)"
_CALL_START = re.compile(rf"\b{_ASK}\s+(?:the\s+value\s+of\s+)?(?P<name>[a-z])\s*\(", re.I)
# A definition's body runs to the next clause.
_CLAUSE_END = re.compile(rf"\s*(?:[,;]|\.\s|\band\b|\bthen\b|\b{_ASK}\b|$)", re.I)
# Words that only join the definitions to the question.
_JOINING_WORDS = frozenset(
    {"if", "given", "let", "and", "suppose", "that", "then", "so", "where", "for"}
)
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:/\d+)?")
_AT_VALUE = re.compile(
    rf"^(?:(?:{_ASK})\s+(?:the\s+value\s+of\s+)?)?(?P<expr>[^=]+?)\s+"
    r"(?:when|at|for|if|where)\s+(?P<var>[a-z])\s*=\s*(?P<value>-?\d+(?:\.\d+)?(?:/\d+)?)$",
    re.I,
)
# Several given values: "x = 3 and y = -2", "x = 1, y = 2, z = 3".
_ONE_VALUE = r"[a-z]\s*=\s*-?\d+(?:\.\d+)?(?:/\d+)?"
_GIVEN_VALUES = rf"{_ONE_VALUE}(?:\s*(?:,\s*(?:and\s+)?|and\s+){_ONE_VALUE}){{0,3}}"
_VALUE_PAIR = re.compile(r"(?P<var>[a-z])\s*=\s*(?P<value>-?\d+(?:\.\d+)?(?:/\d+)?)", re.I)
# "if x = 3 and y = -2, find x^2 - 2xy + y^2": the values first, then the ask.
_VALUES_FIRST = re.compile(
    rf"^(?:if|given|let|when|for|with)\s+(?P<given>{_GIVEN_VALUES})\s*[,.;:]?\s*(?:then\s+)?"
    rf"(?:{_ASK})\s+(?:the\s+value\s+of\s+)?(?P<expr>[^=]+?)$",
    re.I,
)
# "evaluate x^2 - 2xy + y^2 when x = 3 and y = -2".
_VALUES_AFTER = re.compile(
    rf"^(?:(?:{_ASK})\s+(?:the\s+value\s+of\s+)?)?(?P<expr>[^=]+?)\s+"
    rf"(?:when|at|for|if|where|given)\s+(?P<given>{_GIVEN_VALUES})$",
    re.I,
)


def _balanced_call(text: str, open_at: int) -> int | None:
    """Index just past the ``)`` that closes ``text[open_at]``."""
    depth = 0
    for index in range(open_at, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


@dataclass(frozen=True)
class _Call:
    name: str
    argument: _Call | str


def _parse_call(text: str) -> _Call | None:
    """``f(g(2))`` -> f of (g of 2). Arguments are numbers or further calls."""
    compact = text.replace(" ", "")
    match = re.fullmatch(r"^([a-z])\((.+)\)", compact)
    if match is None:
        return None
    inner = match[2]
    if _NUMBER.fullmatch(inner):
        return _Call(match[1], inner)
    nested = _parse_call(inner)
    return _Call(match[1], nested) if nested is not None else None


def _call_names(call: _Call) -> set[str]:
    inner = call.argument
    return {call.name} | (_call_names(inner) if isinstance(inner, _Call) else set())


def _only_joining_words(leftover: str) -> bool:
    words = re.findall(r"[a-z']+", leftover.lower())
    return all(word in _JOINING_WORDS for word in words)


def extract_function_value_intent(text: str) -> MathIntent | None:
    if not text or len(text) > _MAX:
        return None
    body = request_body(text)
    definitions: list[tuple[str, str]] = []
    used: list[tuple[int, int]] = []
    for match in _DEFINITION.finditer(body):
        end = _CLAUSE_END.search(body, match.end())
        stop = end.start() if end is not None else len(body)
        expression = body[match.end() : stop].strip()
        if _parse(expression, match["var"]) is None:
            return None
        definitions.append((f"{match['name']}({match['var']})", expression))
        used.append((match.start(), stop))
    if not definitions:
        return _expression_value_intent(body)
    ask = _CALL_START.search(body)
    if ask is None:
        return None
    open_at = body.index("(", ask.start("name"))
    close = _balanced_call(body, open_at)
    if close is None:
        return None
    call = _parse_call(body[ask.start("name") : close])
    if call is None or not _call_names(call) <= {lhs[0] for lhs, _ in definitions}:
        return None
    used.append((ask.start(), close))
    leftover = list(body)
    for start, stop in used:
        leftover[start:stop] = [" "] * (stop - start)
    if not _only_joining_words("".join(leftover)):
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="function_value",
        expr=body[ask.start("name") : close].replace(" ", ""),
        system_equations=definitions,
        operation="solve",
    )


def _expression_value_intent(body: str) -> MathIntent | None:
    """``evaluate 2x^2 - 3 when x = 4``; ``if x = 3 and y = -2, find x^2 - 2xy + y^2``."""
    match = _AT_VALUE.fullmatch(body)
    if match is None:
        return _several_values_intent(body)
    if re.match(r"^\s*solve\b", match["expr"], re.I):
        return None
    # "the derivative of x^2 at x = 3" is calculus, not a value to substitute.
    expression = _parse(match["expr"], match["var"])
    if expression is None or not expression.free_symbols:
        return None
    return MathIntent(
        kind="arithmetic",
        school_op="expression_value",
        expr=match["expr"].strip(),
        variable=match["var"],
        evaluation_point=match["value"],
        operation="solve",
    )


def _several_values_intent(body: str) -> MathIntent | None:
    """Every letter given a value, then the expression evaluated.

    Read as equations, ``x = 3 and y = -2`` was a system and its answer was
    the values themselves; the expression asked for was dropped.
    """
    match = _VALUES_FIRST.fullmatch(body) or _VALUES_AFTER.fullmatch(body)
    if match is None or re.match(r"^\s*solve\b", match["expr"], re.I):
        return None
    values: dict[str, str] = {}
    for pair in _VALUE_PAIR.finditer(match["given"]):
        if pair["var"] in values:
            return None
        values[pair["var"]] = pair["value"]
    expression = _parse_in(match["expr"], list(values))
    if expression is None:
        return None
    if {str(symbol) for symbol in expression.free_symbols} != set(values):
        # A given the expression never uses means the request was misread.
        return None
    if len(values) == 1:
        ((variable, value),) = values.items()
        return MathIntent(
            kind="arithmetic",
            school_op="expression_value",
            expr=match["expr"].strip(),
            variable=variable,
            evaluation_point=value,
            operation="solve",
        )
    return MathIntent(
        kind="arithmetic",
        school_op="expression_value",
        expr=match["expr"].strip(),
        system_equations=list(values.items()),
        operation="solve",
    )


def _parse(expression: str, variable: str) -> Any | None:
    return _parse_in(expression, [variable])


def _parse_in(expression: str, variables: list[str]) -> Any | None:
    from app.modules.math import solve as math_solve
    from app.services.solving import SolveServiceError

    try:
        parsed = math_solve.parse_expression(expression, variables)
    except (SolveServiceError, SyntaxError, TypeError, ValueError):
        return None
    if isinstance(parsed, tuple):
        return None
    if not {str(symbol) for symbol in parsed.free_symbols} <= set(variables):
        return None
    return parsed


def _substituted_tex(expression: Any, variable: Any, value: Any) -> str:
    """``2 x^{2} - 3`` at 4 -> ``2 \\left(4\\right)^{2} - 3``: the number in the variable's place.

    It takes brackets where it multiplies a coefficient or carries a power, and
    always when it is negative or a fraction.
    """
    from sympy import latex

    tex = str(latex(expression))
    shown = str(latex(value))
    plain = bool(value.is_Integer and value >= 0)

    def put(match: re.Match[str]) -> str:
        before = tex[: match.start()].rstrip()
        after = tex[match.end() :]
        needs = not plain or after.startswith("^") or (before[-1:] in set("0123456789})"))
        return rf"\left({shown}\right)" if needs else shown

    return re.sub(rf"(?<![\\A-Za-z]){re.escape(str(variable))}(?![A-Za-z])", put, tex)


def _substituted_values_tex(expression: Any, values: dict[str, Any]) -> str:
    """Each given letter replaced by its value: ``2xy`` at 3, -2 → ``2(3)(-2)``.

    As for one letter, and a value beside another value takes brackets too.
    """
    from sympy import latex

    tex = str(latex(expression))
    names = "".join(re.escape(name) for name in values)

    def put(match: re.Match[str]) -> str:
        given = values[match.group(0)]
        shown = str(latex(given))
        plain = bool(given.is_Integer and given >= 0)
        before = tex[: match.start()].rstrip()
        after = tex[match.end() :].lstrip()
        needs = (
            not plain
            or after.startswith("^")
            or before[-1:] in set("0123456789})")
            or after[:1] in values
            or after[:1].isdigit()
        )
        return rf"\left({shown}\right)" if needs else shown

    return re.sub(rf"(?<![\\A-Za-z])[{names}](?![A-Za-z])", put, tex)


def _termwise_tex(expression: Any, values: dict[str, Any]) -> str | None:
    """``32 - 3``: each term of a sum worked out, before they are combined."""
    from sympy import latex

    terms = expression.as_ordered_terms()
    if len(terms) < 2:
        return None
    parts: list[str] = []
    by_symbol = {
        symbol: values[str(symbol)] for symbol in expression.free_symbols if str(symbol) in values
    }
    for index, term in enumerate(terms):
        worked = term.subs(by_symbol)
        if not worked.is_number:
            return None
        if index == 0:
            parts.append(str(latex(worked)))
        elif worked.could_extract_minus_sign():
            parts.append(f"- {latex(-worked)}")
        else:
            parts.append(f"+ {latex(worked)}")
    return " ".join(parts)


def _value_line(left: str, expression: Any, values: dict[str, Any]) -> tuple[str, Any]:
    """``left = substituted = term by term`` and the value it comes to."""
    if len(values) == 1:
        ((name, value),) = values.items()
        substituted = _substituted_tex(expression, name, value)
    else:
        substituted = _substituted_values_tex(expression, values)
    chain = [left, substituted]
    termwise = _termwise_tex(expression, values)
    if termwise is not None:
        chain.append(termwise)
    by_symbol = {
        symbol: values[str(symbol)] for symbol in expression.free_symbols if str(symbol) in values
    }
    return " = ".join(dict.fromkeys(chain)), expression.subs(by_symbol)


def _call_tex(call: _Call) -> str:
    """``f(g(2))``; a fraction argument is typeset, ``f\\left(\\frac{1}{2}\\right)``."""
    from sympy import latex, sympify

    inner = call.argument
    if isinstance(inner, _Call):
        return f"{call.name}({_call_tex(inner)})"
    if "/" in inner:
        return rf"{call.name}\left({latex(sympify(inner))}\right)"
    return f"{call.name}({inner})"


def _block_function_value(intent: MathIntent, lines: list[str]) -> VerifiedMathBlock | None:
    from sympy import latex, sympify

    from app.modules.math.solve.display import format_verified_latex

    if intent.school_op == "expression_value" and intent.system_equations:
        given = {name: sympify(number) for name, number in intent.system_equations}
        expression = _parse_in(intent.expr or "", list(given))
        if expression is None:
            return None
        working, value = _value_line(str(latex(expression)), expression, given)
        stated = ", ".join(f"{name} = {latex(number)}" for name, number in given.items())
        rows = [stated, working]
    elif intent.school_op == "expression_value":
        expression = _parse(intent.expr or "", intent.variable)
        if expression is None or intent.evaluation_point is None:
            return None
        point = sympify(intent.evaluation_point)
        working, value = _value_line(str(latex(expression)), expression, {intent.variable: point})
        rows = [working]
    else:
        call = _parse_call(intent.expr or "")
        functions = {}
        for lhs, rhs in intent.system_equations or []:
            parsed = _parse(rhs, lhs[2])
            if parsed is None:
                return None
            functions[lhs[0]] = (lhs[2], parsed)
        if call is None:
            return None
        rows, value = _worked_call(call, functions)
    if value is None or not value.is_number or not value.is_finite:
        return None
    answer = format_verified_latex(value)
    lines.extend(f"Working: ${row}$" for row in rows)
    lines.append(f"Result: {answer}")
    block = finish_with_answer(lines, answer)

    shown = "  \n".join(math_line(row) for row in rows)
    return replace(block, worked_reply=f"{shown}\n\n```answer\n{answer}\n```\n")


def _worked_call(call: _Call, functions: dict[str, tuple[str, Any]]) -> tuple[list[str], Any]:
    """Innermost call first: ``g(2) = (2)^{2} = 4``, then ``f(g(2)) = f(4) = 4 + 1``."""
    from sympy import latex, sympify

    variable, expression = functions[call.name]
    inner = call.argument
    if isinstance(inner, _Call):
        rows, inner_value = _worked_call(inner, functions)
        # An inner value is used again, so its row ends in that value.
        rows[-1] = f"{rows[-1]} = {latex(inner_value)}"
        argument = inner_value
        left = f"{_call_tex(call)} = {call.name}({latex(inner_value)})"
    else:
        rows = []
        argument = sympify(inner)
        left = _call_tex(call)
    row, value = _value_line(left, expression, {variable: argument})
    return [*rows, row], value
