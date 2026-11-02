"""Whole-message numeric arithmetic, kept out of the dimension scan.

A cue such as "what is" or "how would you calculate" is stripped, then the
remainder has to be a number expression. Dates and phone numbers stay out.
"""

from __future__ import annotations

import re

from app.services.glyphs import OPERATOR_GLYPHS
from app.services.text_match import parens_balanced, word_index
from app.services.text_normalize import collapse_ws

_MAX = 1000

# Whole-message arithmetic cues. Longer phrases first so "what is" does not
# leave "the value of" behind.
_ARITH_CUES: tuple[str, ...] = (
    "how would you calculate",
    "how would you compute",
    "how would you evaluate",
    "how do you calculate",
    "how do you compute",
    "how can you calculate",
    "can you calculate",
    "could you calculate",
    "the result of",
    "the sum of",
    "the value of",
    # A follow-up suggestion: "What if it were 3 - 2?", "What if 2½ + 1½ instead?" and
    # "what about 7 * 8?" ask for that sum.
    "what if it were",
    "what if it was",
    "what if it is",
    "what if",
    "what about",
    "how about",
    "instead",
    "what is",
    "what's",
    "whats",
    # Chat spelling of the same cue ("wat is 15 - 4 x 3").
    "wat is",
    "wat's",
    "wats",
    "calculate",
    "compute",
    "evaluate",
    "please",
)
# OCR / keyboard glyphs → ASCII before SymPy. Keep ÷ unambiguous *before* this
# map so a lone ASCII `/` can still look like a date.
_ARITH_OP_ASCII: tuple[tuple[str, str], ...] = tuple(OPERATOR_GLYPHS.items())
_UNAMBIGUOUS_ARITH = frozenset("*^" + "".join(src for src, dst in _ARITH_OP_ASCII if dst in "*/"))
_ARITH_ALLOWED = frozenset("0123456789.+-*/^()! " + "".join(src for src, _ in _ARITH_OP_ASCII))
# Functions whose value at a number is one number in any unit system.
# Hyperbolic and inverse trig take a number, not an angle, so they are not
# ambiguous the way sin(30) is. Longest names first: ``asinh(`` holds ``sinh(``.
_NUMERIC_FUNCTIONS = (
    "asinh", "acosh", "atanh", "asin", "acos", "atan", "acot", "asec", "acsc",
    "sinh", "cosh", "tanh", "coth", "sech", "csch",
    "ceiling", "floor", "sqrt", "Abs", "log", "ln", "exp",
)  # fmt: skip
# ``\\arcsin(…)`` normalizes to ``asin (…)``: a call with a space.
_SPACED_CALL = re.compile(rf"(?<![A-Za-z])({'|'.join(_NUMERIC_FUNCTIONS)})\s+\(")
_LATEX_ARITH_OPS = ("\\div", "\\times", "\\cdot")
# Constants the keypad types: e, π, and the upright i (read as ``I``). A word
# such as ``pie`` or ``I am`` is not one; ``5e3`` keeps its number.
_NUMERIC_CONSTANT = re.compile(r"(?<![A-Za-z])(?:pi|e|I)(?![A-Za-z0-9])|π")
# The factorial input cap the combinatorics solver keeps.
_LARGEST_FACTORIAL = 170
# ``2 1/2`` is two and a half, never ``2 * 1/2``.
_MIXED_NUMBER = re.compile(r"(?:\b(?<!\.)|\B(?<!\d))(\d+)\s+(\d+)\s*/\s*(\d+)(?![\d.])")
# Two numbers with only a space between them (``1 000``) are not one expression.
_SPACED_NUMBERS = re.compile(r"\d\s+[\d.]")
# ``456 x 23``: a letter x spaced between two numbers is "times". ``2x + 3``
# keeps its unknown, and a glued ``8x5`` stays a dimension (like ``8 by 5``).
_TIMES_LETTER = re.compile(r"\b(?<!\.)(\d+(?:\.\d+)?)\s+[xX]\s+(?=\d)")
# Spoken operators between numbers, read by the same whole-message grammar.
_SPOKEN_OPERATORS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bmultiplied\s+by\b"), "*"),
    (re.compile(r"\bdivided\s+by\b"), "/"),
    (re.compile(r"\btimes\b"), "*"),
    (re.compile(r"\bplus\b"), "+"),
    (re.compile(r"\bminus\b"), "-"),
)
# ``log base 2 of 64`` is ``log_2(64)``: a number base, a number or a bracket.
_SPOKEN_LOG_BASE = re.compile(
    r"\blog\s+(?:to\s+(?:the\s+)?)?base\s+(\d+(?:\.\d+)?)\s+of\s+(\d+(?:\.\d+)?|\([^()]*\))"
)


def times_between_numbers(text: str) -> str:
    """``456 x 23`` → ``456 * 23``; ``2x + 3``, ``8x5`` and ``0x10`` stay as typed."""
    return _TIMES_LETTER.sub(r"\1 * ", text)


def spoken_arithmetic(lower: str) -> str:
    """Spoken operators and ``log base b of n`` in the notation the grammar reads."""
    text = _SPOKEN_LOG_BASE.sub(r"log_\1(\2)", lower)
    for pattern, operator in _SPOKEN_OPERATORS:
        text = pattern.sub(f" {operator} ", text)
    return collapse_ws(times_between_numbers(text))


def _factorials_ok(compact: str) -> bool:
    """Every ``!`` closes a whole number of at most 170: ``6!/4!``, not ``5!!`` or ``(2+3)!``."""
    for index, ch in enumerate(compact):
        if ch != "!":
            continue
        start = index
        while start > 0 and compact[start - 1].isdigit():
            start -= 1
        if start == index or (start > 0 and compact[start - 1] == "."):
            return False
        if int(compact[start:index]) > _LARGEST_FACTORIAL:
            return False
        if index + 1 < len(compact) and compact[index + 1] in "!.":
            return False
    return True


def _strip_arith_cues(lower: str) -> tuple[str, bool]:
    """Remove whole-word compute cues. Linear ``word_index``, no regex."""
    had = False
    s = lower
    changed = True
    while changed:
        changed = False
        for cue in _ARITH_CUES:
            idx = word_index(s, cue)
            if idx == -1:
                continue
            s = s[:idx] + " " + s[idx + len(cue) :]
            had = True
            changed = True
            break
    s = s.strip()
    while s and s[-1] in "?.!":
        if s[-1] == "!" and "!" in s[:-1]:
            # ``6!/4!``: once factorials are written, a closing ``!`` is one too.
            break
        s = s[:-1].rstrip()
    return collapse_ws(s), had


def _to_ascii_arith(expr: str) -> str:
    out = expr
    for src, dst in _ARITH_OP_ASCII:
        out = out.replace(src, dst)
    return out


def _binary_ops_only_minus_or_slash(compact: str) -> bool:
    """True when every binary operator is ``-`` or ``/`` (dates, phone numbers)."""
    for ch in compact.removeprefix("+"):
        if ch in "+*^":
            return False
    return True


def _looks_like_date_or_phone(compact: str) -> bool:
    """Structural dates (``9/7/2026``) and phones (``1-800-273-8255``).

    Linear scan — not a blanket reject of every ``-``/``/`` chain, so
    ``10-3-2`` and ``100/5/2`` stay calculator arithmetic.
    """
    compact = compact.removeprefix("+")
    if not compact or compact[0] == "-":
        return False
    if re.fullmatch(r"(?:\+?1-?)?\(\d{3}\)\d{3}-\d{4}", compact):
        return True
    groups: list[int] = []
    seps: list[str] = []
    i = 0
    n = len(compact)
    while i < n:
        ch = compact[i]
        if ch.isdigit():
            j = i + 1
            while j < n and compact[j].isdigit():
                j += 1
            groups.append(j - i)
            i = j
            continue
        if ch in "-/":
            seps.append(ch)
            i += 1
            continue
        return False
    if not seps or len(groups) != len(seps) + 1:
        return False
    all_slash = all(sep == "/" for sep in seps)
    all_minus = all(sep == "-" for sep in seps)
    if not (all_slash or all_minus):
        return False
    if len(groups) == 2:
        # Seven-digit phone and year-month date. A bare short subtraction
        # such as 2-6 is arithmetic; prose ranges never pass the allowlist.
        a, b = groups
        return all_minus and ((a == 3 and b == 4) or (a == 4 and b == 2))
    if len(groups) == 3:
        a, b, c = groups
        if a <= 2 and b <= 2 and c in (2, 4):
            return True
        if a == 4 and b <= 2 and c <= 2:
            return True
        return all_minus and a == 3 and b == 3 and c == 4
    return all_minus and len(groups) >= 4 and sum(groups) >= 7


def _unambiguous_single_slash(compact: str) -> bool:
    """True for a two-number division that cannot reasonably be a date.

    A bare ``9/9`` remains ambiguous, as do year/month forms such as
    ``2026/09``.  Values such as ``456/56`` are not calendar-shaped and should
    reach the arithmetic solver instead of leaving a model to improvise long
    division in plain text.
    """
    if compact.count("/") != 1 or any(ch in compact for ch in "+-*^()"):
        return False
    left, right = compact.split("/", 1)
    if not left or not right:
        return False
    if "." in left or "." in right:
        return all(part.replace(".", "", 1).isdigit() for part in (left, right))
    if not left.isdigit() or not right.isdigit():
        return False
    first, second = int(left), int(right)
    if len(left) == 4 and 1 <= second <= 12:
        return False
    could_be_month_day = (1 <= first <= 12 and 1 <= second <= 31) or (
        1 <= second <= 12 and 1 <= first <= 31
    )
    return not could_be_month_day


def _count_binary_arith_ops(compact: str) -> int:
    """Binary ``+ - * / ^`` in an ASCII expression. Leading/unary ``-`` is not an op."""
    ops = 0
    prev_was_op = True
    for ch in compact:
        if ch in "+*/^":
            ops += 1
            prev_was_op = True
            continue
        if ch == "-":
            if not prev_was_op:
                ops += 1
            prev_was_op = True
            continue
        if ch == "(":
            prev_was_op = True
            continue
        if ch == ")":
            prev_was_op = False
            continue
        prev_was_op = False
    return ops


def bare_arithmetic_expr(text: str) -> str | None:
    """Whole-message numeric arithmetic, or None.

    Shared by the SymPy gate and the arithmetic extractor so ``8-8*2`` cannot
    be gated as a dimension pair (``8*2``) and then fail extract.

    Bare subtraction is arithmetic; a single ``/`` needs a cue unless its
    values cannot reasonably be a date (for example ``456/56``).
    Auto-accept with a single subtraction, ``*``, ``^``, a factorial (``6!/4!``),
    times/divide glyphs, two or more operators, or a cue word (``what is``,
    ``calculate``, ...).
    Uncued ``-``/``/`` chains that look like a date or phone are rejected;
    chained arithmetic such as ``10-3-2`` is not.
    """
    if not text or len(text) > _MAX:
        return None
    stripped, had_cue = _strip_arith_cues(text.lower())
    # A keypad constant is a number too: ``ln(e)`` has no digit and is 1.
    if not stripped or not (
        any(ch.isdigit() for ch in stripped) or _NUMERIC_CONSTANT.search(stripped)
    ):
        return None
    stripped = spoken_arithmetic(stripped)
    from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy

    normalized = normalize_latex_to_sympy(_MIXED_NUMBER.sub(r"(\1+\2/\3)", stripped))
    normalized = _SPACED_CALL.sub(r"\1(", normalized)
    if _SPACED_NUMBERS.search(normalized):
        return None
    # Numeric radicals and keyboard braced powers use the same normalization
    # as the solver. Functions with one numeric value are admitted (|-7|,
    # log(1000)); trig is not, since sin(30) could mean degrees or radians.
    numeric = normalized
    for name in _NUMERIC_FUNCTIONS:
        numeric = numeric.replace(f"{name}(", "(")
    numeric = _NUMERIC_CONSTANT.sub("1", numeric)
    if any(ch not in _ARITH_ALLOWED for ch in numeric):
        return None
    compact = _to_ascii_arith(numeric).replace(" ", "")
    if not compact or not parens_balanced(compact) or not _factorials_ok(compact):
        return None
    if compact[-1] not in "0123456789)!":
        return None
    if compact[0] not in "0123456789.(+-":
        return None
    ops = _count_binary_arith_ops(compact)
    has_root = any(f"{name}(" in normalized for name in _NUMERIC_FUNCTIONS)
    if ops < 1 and not has_root:
        return None
    unambiguous = has_root or any(ch in stripped for ch in _UNAMBIGUOUS_ARITH)
    unambiguous = unambiguous or "**" in normalized or "!" in compact
    # The keypad's divide and times keys type \div and \times: never a date.
    unambiguous = unambiguous or any(cmd in stripped for cmd in _LATEX_ARITH_OPS)
    unambiguous = unambiguous or _unambiguous_single_slash(compact)
    subtraction = ops == 1 and "-" in compact and not any(ch in "+*/^" for ch in compact)
    # ``-3+5`` is one signed start and one operation, not a date.
    signed_start = compact[0] in "+-" and ops >= 1
    if not (unambiguous or subtraction or ops >= 2 or had_cue or signed_start):
        return None
    # Dates / phones: structural ``9/7/2026`` / ``1-800-273-8255``, not
    # every minus-or-slash chain (``10-3-2``). Keep ``8-8*2`` and cued ``9/9``.
    if (
        not had_cue
        and not unambiguous
        and _binary_ops_only_minus_or_slash(compact)
        and _looks_like_date_or_phone(compact)
    ):
        return None
    return collapse_ws(_to_ascii_arith(normalized))
