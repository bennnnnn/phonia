"""Judge a maths answer card against a worked answer, using SymPy and no app code.

The STEM sweep's maths corpus gives each question a ``check``: a kind and the
answer worked independently. This module reads the card the way a student
would (the right side of each ``=``, split on "or", "and" and commas) and
compares with SymPy, so a solver bug cannot also hide in its own judge.

check kinds:
  num       value: a SymPy number; some value on the card equals it (0.5%)
  num_any   value: several numbers; the card holds one of them
  nums      value: several numbers; the card holds every one ("176 R2" is 176 and 2)
  expr      value: a SymPy expression in x; some card piece equals it exactly
  anti      value: an antiderivative; some card piece differs by a constant
  anti_any  value: several antiderivatives; the card holds one of them
  set       value: a SymPy set in x; the card's inequalities or intervals equal it
  regex     value: a regex over the lowercased card and reply
  matrix    value: rows of numbers; the card lists them in order
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

from sympy import (
    E,
    Expr,
    I,
    Interval,
    N,
    S,
    Set,
    Union,
    diff,
    oo,
    pi,
    simplify,
    symbols,
    sympify,
)
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

x, y, a, b, m = symbols("x y a b m")
_TRANSFORMS = (*standard_transformations, implicit_multiplication_application, convert_xor)
_NAMES: dict[str, Any] = {
    "E": E,
    "I": I,
    "pi": pi,
    "oo": oo,
    "x": x,
    "y": y,
    "a": a,
    "b": b,
    "m": m,
}


def latex_plain(text: str) -> str:
    """``\\frac{3}{2} \\cdot x^{2}`` → ``((3)/(2)) * x**(2)``."""
    t = text.replace("\\left", "").replace("\\right", "")
    # "\$10.95": the dollar sign is the unit, not maths.
    t = re.sub(r"\\?\$(?=\s*-?\d)", " ", t)
    for space in ("\\,", "\\;", "\\ "):
        t = t.replace(space, " ")
    t = t.replace("\\quad", " ; ").replace("\\approx", "=")
    t = re.sub(r"\\mathrm\{[^{}]*\}(\^\{?\d\}?)?", "", t)
    # "x = 2 \text{ or } x = 3" keeps its "or"; a word ("minimum") is not a value.
    t = re.sub(r"\\text\{\s*(or|and)\s*\}", r" \1 ", t)
    t = re.sub(r"\\text\{[^{}]*\}", " ", t)
    t = re.sub(r"\^\{?\\circ\}?", "", t).replace("°", "")
    for _ in range(4):
        t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", t)
        t = re.sub(r"\\sqrt\{([^{}]*)\}", r"sqrt(\1)", t)
        # A student reads an odd root of a negative number as real: ∛(-8) is -2.
        t = re.sub(r"\\sqrt\[(\d+)\]\{([^{}]*)\}", r"real_root(\2, \1)", t)
        t = re.sub(r"\^\{([^{}]*)\}", r"**(\1)", t)
        t = re.sub(r"\\(ln|log|sin|cos|tan|exp)\{([^{}]*)\}", r"\\\1(\2)", t)
    for latex, plain in (
        ("\\pi", " pi "),
        ("\\infty", " oo "),
        ("\\ln", " log"),
        ("\\cdot", "*"),
        ("\\times", "*"),
        ("×", "*"),
        ("÷", "/"),
        ("−", "-"),
    ):
        t = t.replace(latex, plain)
    t = re.sub(r"\\(sin|cos|tan|log|exp)", r" \1", t)
    t = t.replace("{", "(").replace("}", ")").replace("\\", " ")
    t = re.sub(r"\be\*\*", "E**", t)
    return re.sub(r"\be\b", "E", t)


def pieces(card: str) -> list[Any]:
    """Each value the card states: the right side of each ``=``, ± expanded."""
    out: list[Any] = []
    for part in re.split(r"\bor\b|\band\b|;|,(?![^()]*\))|\n", latex_plain(card)):
        rhs = part.strip().split("=")[-1].strip()
        if not rhs:
            continue
        rhs = re.sub(r"\bapprox\b.*$", "", rhs).strip()
        rhs = re.sub(r"\b(units|radians|cm|m|km|h)\b", "", rhs)
        rhs = re.sub(r"\+\s*C\b", "", rhs).replace("%", "")
        alts = [rhs.replace("pm", "+"), rhs.replace("pm", "-")] if "pm" in rhs else [rhs]
        for alt in alts:
            alt = re.sub(r"(?<![a-zA-Z])i(?![a-zA-Z])", "I", alt)
            try:
                value = parse_expr(alt, transformations=_TRANSFORMS, local_dict=dict(_NAMES))
            except Exception:  # noqa: S112 - a piece that is not maths ("units", a word)
                continue
            # A point "(0, 5)" states both coordinates.
            out.extend(value if isinstance(value, tuple) else [value])
    return out


def close(value: Any, want: Any) -> bool:
    # A set or a relation is not subtractable; it can still be numeric below.
    with contextlib.suppress(Exception):
        if simplify(value - want) == 0:
            return True
    try:
        got, target = complex(N(value)), complex(N(want))
    except Exception:
        return False
    return abs(got - target) <= max(0.005 * abs(target), 0.006)


_RELATION = re.compile(r"(<=|>=|<|>)")
_INTERVAL = re.compile(r"^([\[(])(.+),(.+)([\])])$")


def _interval(piece: str) -> Set | None:
    match = _INTERVAL.match(piece.replace(" ", ""))
    if not match:
        return None
    left, low, high, right = match.groups()
    return Interval(
        sympify(low),
        sympify(high),
        left_open=left == "(",
        right_open=right == ")",
    )


def _chain(piece: str) -> Set | None:
    """``-2 < x < 2`` or ``x >= 3`` as a set of x."""
    tokens = [token.strip() for token in _RELATION.split(piece)]
    if len(tokens) < 3:
        return None
    result: Set = S.Reals
    for left, op, right in zip(tokens[0::2], tokens[1::2], tokens[2::2], strict=False):
        relation = sympify(f"({left}) {op} ({right})", locals=dict(_NAMES))
        result = result.intersect(relation.as_set())
    return result


def read_set(card: str) -> Set | None:
    """The set a card states, in inequalities (``x < -3 or x > 3``) or intervals."""
    text = card.replace("\\left", "").replace("\\right", "")
    for latex, plain in (
        ("\\ge", ">="),
        ("\\le", "<="),
        ("≥", ">="),
        ("≤", "<="),
        ("\\infty", "oo"),
        ("∞", "oo"),
        ("\\cup", " U "),
        ("∪", " U "),
        ("\\;", ""),
        ("\\,", ""),
        ("−", "-"),
    ):
        text = text.replace(latex, plain)
    text = re.sub(r"\\text\{\s*or\s*\}", " or ", text)
    parts = re.split(r"\s+or\s+|\s+U\s+", text.strip())
    found: list[Set] = []
    for part in parts:
        piece = part.strip().strip("$").strip()
        piece = re.sub(r"^x\s*\\in\s*", "", piece)
        try:
            read = _interval(piece) or _chain(piece)
        except Exception:
            return None
        if read is None:
            return None
        found.append(read)
    return Union(*found) if found else None


def judge_check(check: tuple[str, Any], card: str, body: str) -> bool:
    """Whether the card (and, for ``regex``, the reply) holds the worked answer."""
    kind, value = check
    found = pieces(card)
    if kind == "num":
        return any(close(v, sympify(value)) for v in found)
    if kind == "num_any":
        return any(close(v, sympify(want)) for v in found for want in value)
    if kind == "nums":
        # A remainder is written "176 R2" in school: the quotient and the remainder.
        spread_card = re.sub(r"(?<=\d)\s*R\s*(?=\d)", " , ", card)
        spread = found + pieces(
            spread_card.replace("(", " ").replace(")", " ").replace(",", " , ").replace(":", " , ")
        )
        return all(any(close(v, sympify(want)) for v in spread) for want in value)
    if kind == "expr":
        want = sympify(value, locals=dict(_NAMES))
        return any(simplify(v - want) == 0 for v in found if isinstance(v, Expr))
    if kind in {"anti", "anti_any"}:
        wants = [
            sympify(w, locals=dict(_NAMES)) for w in (value if kind == "anti_any" else [value])
        ]
        return any(
            isinstance(v, Expr) and v.has(x) and simplify(diff(v - want, x)) == 0
            for v in found
            for want in wants
        )
    if kind == "set":
        stated = read_set(card)
        return stated is not None and stated == sympify(value, locals={"x": x, "oo": oo})
    if kind == "regex":
        return bool(re.search(value, f"{card}\n{body}".lower()))
    if kind == "matrix":
        flat = re.sub(r"-\s+", "-", latex_plain(card))
        numbers = [sympify(n) for n in re.findall(r"-?\(\(\d+\)/\(\d+\)\)|-?\d+", flat)]
        cells = [sympify(cell) for row in value for cell in row]
        return len(numbers) >= len(cells) and all(
            close(n, cell) for n, cell in zip(numbers, cells, strict=False)
        )
    raise ValueError(f"unknown check kind {kind!r}")
