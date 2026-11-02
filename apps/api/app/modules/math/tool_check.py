"""Is a sympy tool call about the problem the user actually wrote?

The model transcribes the user's problem into the tool's arguments. When it
mistypes (rhs 19 for "2x + 5 = 17") the tool faithfully solves the typo, and
that result used to become the turn's verified answer. A tool result is only
the verified answer when its equation or expression is one the user wrote,
compared with SymPy (``2x - 12 = 0`` matches ``2x + 5 = 17``), and its numeric
settings (bounds, the limit point, a radius) appear in the user's text.

The model's other reading, the structured extraction a turn falls back to when no regex
reader matched (``tools/llm_extract.py``), is held to the same test
(``intent_in_user_text``): "The polynomial f(x) = A(x - 1)^2 + B(x + 2)^2 is divided by
x + 1 and x - 2 …" was read as 9B = 3 and A + 16B = -15, and SymPy's checked card said
A = -61/3, B = 1/3 for A = 1, B = -1 (2026-11-01).

Runs inside the SymPy process pool (``run_sympy``); every failure is "no match",
which only withholds the green check, never the tool result itself.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from app.services.glyphs import OPERATOR_GLYPHS

logger = logging.getLogger(__name__)

_MAX_CANDIDATES = 24
_MAX_TEXT = 2000

# The operators are the shared table (services/glyphs.py); the rest are this check's.
_UNICODE = {
    "²": "^2",
    "³": "^3",
    "⁴": "^4",
    **OPERATOR_GLYPHS,
    "π": "pi",
    "√": "sqrt",
    "≤": "<=",
    "≥": ">=",
}
_FUNCTIONS = frozenset(
    {
        "sin",
        "cos",
        "tan",
        "sec",
        "csc",
        "cot",
        "asin",
        "acos",
        "atan",
        "arcsin",
        "arccos",
        "arctan",
        "sinh",
        "cosh",
        "tanh",
        "ln",
        "log",
        "exp",
        "sqrt",
        "abs",
        "pi",
        "e",
    }
)
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[A-Za-z]+|<=|>=|[-+*/^()=<>!,]|\s+|.")
_MATH_TOKEN = re.compile(r"[\d.]+|[-+*/^()=<>]|<=|>=")
_COMPARATORS = ("<=", ">=", "<", ">")
_APOSTROPHES = frozenset({"'", "\u2019"})
_INFINITY_WORDS = ("infinity", "∞", "oo", "inf")
# A minus that signs a number, not one that subtracts it ("x-1"): after a space, a bracket,
# an operator, a subscript mark ("∫_1^2") or the start.
_SIGNED = re.compile(r"(?<![A-Za-z0-9).])((?:-|minus\s+|negative\s+)?)\s*(\d+(?:\.\d+)?)")
_SIGNED_INFINITY = re.compile(
    r"(?<![\w).])((?:-|minus\s+|negative\s+)?)\s*(?:∞|\\infty|infinity|oo|inf)(?![a-z])"
)
_ORDER_WORDS = {2: ("second", "2nd", "d^2", "d²", "''"), 3: ("third", "3rd", "d^3", "'''")}


def _normalize(text: str) -> str:
    out = text[:_MAX_TEXT]
    for raw, plain in _UNICODE.items():
        out = out.replace(raw, plain)
    return out.replace("$", " ").replace("\\cdot", "*").replace("\\times", "*")


def _latex_as_typed(text: str) -> str:
    """LaTeX the keypad or a photo's reading writes, in the plain spelling runs read."""
    from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy
    from app.modules.math.tools.keyboard_notation import keyboard_math_to_plain

    plain = keyboard_math_to_plain(text[:_MAX_TEXT])
    # Twice: a fraction holding a braced power (\frac{x^{2}-1}{x-1}) opens on the second.
    return normalize_latex_to_sympy(normalize_latex_to_sympy(plain))


def _math_runs(text: str) -> list[str]:
    """Maximal runs of formula tokens; an English word or a comma ends a run.

    A letter that ends a word after an apostrophe is the word's: "balloon's", "let's" and
    "it's" made the message's ``s`` its formula, so a follow-up never read the problem
    before it (2026-10-24). A quoted formula ("plot 'x^2'") keeps its letters.
    """
    runs: list[str] = []
    current: list[str] = []
    depth = 0
    pieces = _TOKEN.findall(_normalize(text))
    for index, piece in enumerate(pieces):
        if piece.isalpha():
            mathy = (len(piece) == 1 and not _ends_a_word(pieces, index)) or (
                piece.lower() in _FUNCTIONS
            )
        elif not piece.strip():
            mathy = True  # spacing inside a formula
        elif piece == ",":
            mathy = depth > 0  # f(x, y) keeps its comma; a list ends the run
        else:
            mathy = _MATH_TOKEN.fullmatch(piece) is not None
        if mathy:
            depth += piece.count("(") - piece.count(")")
            current.append(piece)
            continue
        if current:
            runs.append("".join(current).strip())
        current = []
        depth = 0
    if current:
        runs.append("".join(current).strip())
    return [run for run in runs if run and any(ch.isdigit() or ch.isalpha() for ch in run)]


def _ends_a_word(pieces: list[str], index: int) -> bool:
    """The letter at ``index`` closes a contraction or possessive: a word, an apostrophe,
    then it, then no more letters."""
    return (
        index >= 2
        and pieces[index - 1] in _APOSTROPHES
        and pieces[index - 2].isalpha()
        and not (index + 1 < len(pieces) and pieces[index + 1].isalpha())
    )


def _parse(text: str) -> Any | None:
    """``text`` as an expression; a point ``(1, 2)``, ``True`` or a bare SymPy name is none."""
    from sympy import Expr

    from app.modules.math import solve as math_solve
    from app.modules.math.solve.declines import sympy_decline

    candidate = text.strip().strip(".,;:")
    if not candidate or len(candidate) > 200:
        return None
    with sympy_decline():
        parsed = math_solve.parse_expression(candidate)
        return parsed if isinstance(parsed, Expr) else None
    return None


def _split_relation(run: str) -> list[tuple[str, str, str]]:
    """``a = b = c`` → [(a, =, b), (b, =, c)]; ``a < b`` → [(a, <, b)]."""
    parts = re.split(r"(<=|>=|=|<|>)", run)
    out: list[tuple[str, str, str]] = []
    for index in range(1, len(parts) - 1, 2):
        out.append((parts[index - 1], parts[index], parts[index + 1]))
    return out


class _UserMath:
    """What the user wrote, parsed: expressions, equations, inequalities, numbers."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lower = text.lower()
        self.expressions: list[Any] = []
        self.equations: list[Any] = []
        self.inequalities: list[tuple[Any, str]] = []
        runs = _math_runs(text)
        if "\\" in text:
            # The keypad and a photo's reading type LaTeX: \frac{1}{x}, \int_{1}^{2}, x^{2}.
            runs += [run for run in _math_runs(_latex_as_typed(text)) if run not in runs]
        pairs = self._extracted_pairs(text)
        for run in runs[:_MAX_CANDIDATES]:
            relations = _split_relation(run)
            if not relations:
                self._add_expression(run)
                continue
            for left, op, right in relations:
                self._add_expression(left)
                self._add_expression(right)
                lhs, rhs = _parse(left), _parse(right)
                if lhs is None or rhs is None:
                    continue
                if op == "=":
                    self.equations.append(lhs - rhs)
                else:
                    self.inequalities.append((lhs - rhs, op))
        for left, right in pairs:
            lhs, rhs = _parse(left), _parse(right)
            if lhs is not None and rhs is not None:
                self.equations.append(lhs - rhs)
                self.expressions.extend([lhs, rhs])
        normalized = _normalize(text)
        self.numbers = {float(match) for match in re.findall(r"\d+(?:\.\d+)?", normalized)}
        # A number with its sign as written: "-1" or "minus 1" is no 1, and "1" no -1.
        signed = [(bool(m.group(1)), float(m.group(2))) for m in _SIGNED.finditer(normalized)]
        self.negatives = {value for minus, value in signed if minus}
        self.positives = {value for minus, value in signed if not minus}
        # "\infty" the keypad types, and infinity after a unicode minus, read as meant.
        self.infinities = {bool(m.group(1)) for m in _SIGNED_INFINITY.finditer(normalized.lower())}

    @staticmethod
    def _extracted_pairs(text: str) -> list[tuple[str, str]]:
        from app.modules.math.solve.declines import sympy_decline

        with sympy_decline():
            from app.modules.math.solve.extract_eq import try_extract_equations_from_text

            return try_extract_equations_from_text(text)[:_MAX_CANDIDATES]
        return []

    def _add_expression(self, text: str) -> None:
        parsed = _parse(text)
        if parsed is not None and len(self.expressions) < _MAX_CANDIDATES * 2:
            self.expressions.append(parsed)

    @property
    def empty(self) -> bool:
        return not (self.expressions or self.equations or self.inequalities)


def _zero(expr: Any) -> bool:
    from sympy import simplify

    from app.modules.math.solve.declines import sympy_decline

    with sympy_decline():
        return bool(simplify(expr) == 0)
    return False


def _ratio(a: Any, b: Any) -> Any | None:
    """``a / b`` when it is a nonzero constant, else None."""
    from sympy import simplify

    from app.modules.math.solve.declines import sympy_decline

    with sympy_decline() as declined:
        if _zero(b):
            return None
        ratio = simplify(a / b)
    if declined:
        return None
    if ratio.free_symbols or not ratio.is_number or _zero(ratio):
        return None
    return ratio


def _same_expression(expr: Any, candidates: Iterable[Any]) -> bool:
    return any(_zero(expr - candidate) for candidate in candidates)


def _same_equation(difference: Any, user: _UserMath) -> bool:
    return any(_ratio(difference, candidate) is not None for candidate in user.equations)


def _same_inequality(difference: Any, comparator: str, user: _UserMath) -> bool:
    flip = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}
    for candidate, op in user.inequalities:
        ratio = _ratio(difference, candidate)
        if ratio is None:
            continue
        if (ratio > 0 and op == comparator) or (ratio < 0 and op == flip[comparator]):
            return True
    return False


def _number_written(value: Any, user: _UserMath) -> bool:
    """``value`` is written in the user's text with its sign: a bound read as -1 from
    "between 1 and 2" certified 3 for 7/3, and -∞ for "0 and infinity" a sum that diverges."""
    text = str(value).strip().lower()
    if not text:
        return True
    negative = text.startswith("-")
    if text.lstrip("+-") in {"oo", "inf", "infinity"}:
        return any(sign == negative for sign in user.infinities)
    if text in {"pi", "e"}:
        return text in user.lower or "π" in user.text
    try:
        number = float(text)
    except ValueError:
        parsed = _parse(text)
        return parsed is not None and _same_expression(parsed, user.expressions)
    if number == 0:
        return True
    return abs(number) in (user.negatives if number < 0 else user.positives)


def _expression_arg(args: dict[str, Any], key: str, user: _UserMath) -> bool:
    parsed = _parse(str(args.get(key) or ""))
    return parsed is not None and _same_expression(parsed, user.expressions)


def _matches(args: dict[str, Any], user: _UserMath) -> bool:
    action = str(args.get("action") or "solve").strip().lower()
    if action == "solve":
        lhs, rhs = _parse(str(args.get("lhs") or "")), _parse(str(args.get("rhs") or "0"))
        return lhs is not None and rhs is not None and _same_equation(lhs - rhs, user)
    if action == "system":
        equations = args.get("equations") or []
        if not equations:
            return False
        for pair in equations:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                return False
            lhs, rhs = _parse(str(pair[0])), _parse(str(pair[1]))
            if lhs is None or rhs is None or not _same_equation(lhs - rhs, user):
                return False
        return True
    if action == "inequality":
        lhs, rhs = _parse(str(args.get("lhs") or "")), _parse(str(args.get("rhs") or "0"))
        comparator = str(args.get("comparator") or "")
        if lhs is None or rhs is None or comparator not in _COMPARATORS:
            return False
        return _same_inequality(lhs - rhs, comparator, user)
    if action in {"diff", "integrate", "simplify", "factor", "expand", "newton", "series", "limit"}:
        if not _expression_arg(args, "expr", user):
            return False
        if action == "diff":
            order = int(args.get("order") or 1)
            return order == 1 or any(word in user.lower for word in _ORDER_WORDS.get(order, ()))
        settings = {
            "integrate": ("lower", "upper"),
            "limit": ("point",),
            "series": ("start", "end"),
        }.get(action, ())
        return all(
            args.get(key) in (None, "") or _number_written(args.get(key), user) for key in settings
        )
    if action == "graph":
        if not _expression_arg(args, "expr", user):
            return False
        return not args.get("expr2") or _expression_arg(args, "expr2", user)
    if action in {"rectangle", "square", "circle"}:
        keys = [key for key in ("width", "height", "side", "radius") if args.get(key) is not None]
        return bool(keys) and all(_number_written(args[key], user) for key in keys)
    # dsolve, or the free-text fallback: the text must be the user's own words.
    text = str(args.get("text") or args.get("expr") or "")
    compact = re.sub(r"\s+", "", text.lower())
    return bool(compact) and compact in re.sub(r"\s+", "", user.lower)


_CALCULUS_ACTIONS = {"differentiate": "diff"}
# The kinds whose maths this check compares with what the user wrote.
READ_KINDS = frozenset(
    {"equation", "system", "inequality", "calculus", "limit", "graph", "complex"}
)


def intent_in_user_text(intent: Any, text: str) -> bool:
    """Whether a model-extracted ``MathIntent`` is mathematics the user wrote: its equation,
    system, inequality or expression, compared with SymPy, and its bounds or limit point
    written in ``text``. A reading the model derived (equations from a story, "x squared"
    for x²) is not the user's text, and SymPy's answer to it is no checked answer."""
    args: dict[str, Any]
    if intent.kind == "equation":
        args = {"action": "solve", "lhs": intent.lhs, "rhs": intent.rhs}
    elif intent.kind == "system":
        args = {"action": "system", "equations": intent.system_equations or []}
    elif intent.kind == "inequality":
        args = {"action": "inequality", "lhs": intent.lhs, "rhs": intent.rhs}
        args["comparator"] = intent.comparator
    elif intent.kind == "calculus":
        action = _CALCULUS_ACTIONS.get(intent.operation, intent.operation)
        args = {"action": action, "expr": intent.expr}
        args |= {"lower": intent.integral_lower, "upper": intent.integral_upper}
    elif intent.kind == "limit":
        args = {"action": "limit", "expr": intent.expr, "point": intent.limit_point}
    elif intent.kind in {"graph", "complex"}:
        args = {"action": "graph" if intent.kind == "graph" else "simplify", "expr": intent.expr}
    else:
        return False
    return tool_call_matches_user_text(args, [text])


def holds_no_formula(text: str) -> bool:
    """``text`` has no formula this check could match a call against."""
    return _UserMath(text).empty


def tool_call_matches_user_text(raw_args: str | dict[str, Any], user_texts: list[str]) -> bool:
    """True when the sympy call works on a problem from the user's own messages."""
    return matched_user_text(raw_args, user_texts) is not None


def matched_user_text(raw_args: str | dict[str, Any], user_texts: list[str]) -> str | None:
    """The user's message the sympy call works on, or None when it works on none.

    ``user_texts`` is newest first. The newest message that has any formula in
    it is the reference, so "now graph it" reads the question before it.
    """
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except (TypeError, ValueError):
        return None
    if not isinstance(args, dict):
        return None
    try:
        for text in user_texts:
            if not text or not text.strip():
                continue
            user = _UserMath(text)
            if user.empty:
                continue
            return text if _matches(args, user) else None
    except Exception:
        logger.info("tool-call match check failed", exc_info=True)
    return None
