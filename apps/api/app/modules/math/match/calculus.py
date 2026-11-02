"""Limit / series / integral / calculus-op cues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.modules.math.function_names import MATH_FUNCTION_NAMES
from app.modules.math.match.dimensions import _parse_unsigned_number
from app.modules.math.match.letter_runs import looks_like_math_expr
from app.modules.math.match.scan import _CALC_OP, CALC_OP_SPELLINGS, ddx_cue_at


def _skip_optional_paren_var(text: str, start: int) -> int:
    """Advance past an optional ``(x)`` / ``(t)`` after Lagrange primes."""
    n = len(text)
    k = start
    if k >= n or text[k] != "(":
        return start
    k += 1
    while k < n and text[k].isspace():
        k += 1
    if k >= n or not text[k].isalpha():
        return start
    k += 1
    while k < n and text[k].isspace():
        k += 1
    if k >= n or text[k] != ")":
        return start
    return k + 1


# Multi-letter names that can carry Lagrange primes (``sin'``, ``ln'``).
# One-letter variables (``y'``, ``f''``) are accepted separately. Long English
# words (``teachers' lounge``) must not look like a derivative.
_MATH_PRIME_NAMES = MATH_FUNCTION_NAMES
_MAX_PRIME_BASE = 8


def _math_prime_base(text: str, prime_at: int) -> bool:
    """True when the token before ``'`` is a variable or function, not English."""
    prev = text[prime_at - 1]
    if prev == ")":
        return True
    if not prev.isalpha():
        return False
    start = prime_at - 1
    while start > 0 and text[start - 1].isalpha():
        start -= 1
        if prime_at - start > _MAX_PRIME_BASE:
            return False
    base = text[start:prime_at]
    if len(base) == 1:
        return True
    return base.lower() in _MATH_PRIME_NAMES


def _lagrange_prime_run(text: str, prime_at: int) -> tuple[int, int] | None:
    """Return ``(after_primes, order)`` when ``'`` at ``prime_at`` is a math prime.

    Rejects contractions (``y'all``), plural possessives (``teachers'``), and
    primes not attached to a letter or ``)``.
    """
    if prime_at <= 0:
        return None
    if not _math_prime_base(text, prime_at):
        return None
    n = len(text)
    j = prime_at
    while j < n and text[j] == "'":
        j += 1
    if j < n and text[j].isalpha():
        return None
    return j, min(j - prime_at, 3)


def lagrange_prime_order(text: str) -> int:
    """Highest Lagrange prime count (``''`` → 2, ``'''`` → 3). 0 if none."""
    best = 0
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "'":
            i += 1
            continue
        run = _lagrange_prime_run(text, i)
        if run is None:
            i += 1
            continue
        after, order = run
        if order > best:
            best = order
        i = after
    return best


def _lagrange_derivative_cue(text: str) -> bool:
    """True for ``y'`` / ``f''(x)`` that are not an ODE assignment (not followed by ``=``)."""
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "'":
            i += 1
            continue
        run = _lagrange_prime_run(text, i)
        if run is None:
            i += 1
            continue
        after, _order = run
        k = _skip_optional_paren_var(text, after)
        while k < n and text[k].isspace():
            k += 1
        if k < n and text[k] == "=":
            i = after
            continue
        return True
    return False


def y_prime_math_cue(text: str) -> bool:
    """``y'`` / ``y''`` as calculus or ODE, not the contraction ``y'all``."""
    start = 0
    while True:
        idx = text.find("y'", start)
        if idx == -1:
            return False
        run = _lagrange_prime_run(text, idx + 1)
        if run is not None:
            return True
        start = idx + 2


def calc_op(text: str) -> str | None:
    m = _CALC_OP.search(text)
    if m:
        word = m.group(1).lower()
        return CALC_OP_SPELLINGS.get(word, word)
    if "∫" in text:
        return "integrate"
    if ddx_cue_at(text) is not None:
        return "differentiate"
    if _lagrange_derivative_cue(text):
        return "derivative"
    return None


# Notation only maths writes: an operator, a power, a root or integral sign, a
# number glued to a letter (``2x``), a function name, ``d/dx``.
_STRONG_MATH = re.compile(
    r"[+*/^=\u221a\u222b\u00b2\u00b3\u03c0\\]|(?<![A-Za-z])-|-(?![A-Za-z])"
    r"|\d\s*[a-z]\b|\d\s*[:%]|\b(?:sin|cos|tan|sec|csc|cot|sinh|cosh|tanh|arcsin|arccos|"
    r"arctan|ln|log|exp|sqrt|squared|cubed)\b|\bd\s*/\s*d[a-z]\b",
    re.IGNORECASE,
)
_CALC_OBJECT_TOKEN = re.compile(r"[A-Za-z]+|\d+(?:\.\d+)?")
# Words a request around a bare letter or number may use: "integrate x from
# 0 to 3", "differentiate y with respect to x", "factor 360".
_CALC_OBJECT_WORDS = frozenset(
    {
        "of",
        "the",
        "this",
        "following",
        "expression",
        "function",
        "polynomial",
        "number",
        "fraction",
        "ratio",
        "completely",
        "fully",
        "out",
        "for",
        "me",
        "please",
        "now",
        "again",
        "from",
        "to",
        "with",
        "respect",
        "wrt",
        "dx",
        "dy",
        "dt",
        "dz",
        "du",
        "and",
        "between",
        "at",
        "over",
        "as",
        "approaches",
        "infinity",
        "pi",
        "by",
        "parts",
        "substitution",
        "using",
        "in",
        "terms",
    }
)


def calc_object(text: str) -> bool:
    """A calculus verb has something to act on, not "differentiate between weather and climate".

    Maths notation anywhere is enough. Without it the words after the verb
    must name a letter or a number ("integrate x from 0 to 3", "factor 360")
    and nothing that is not maths: "it", "this paragraph", "Slack with
    Notion" and "on that" are not objects.
    """
    if _STRONG_MATH.search(text):
        return True
    match = _CALC_OP.search(text)
    if match is None:
        # The integral sign and d/dx matched above; a bare Lagrange prime is notation.
        return True
    tokens = _CALC_OBJECT_TOKEN.findall(text[match.end() :])
    operands = [
        piece for piece in tokens if piece[0].isdigit() or (len(piece) == 1 and piece not in "aAiI")
    ]
    words = [piece.lower() for piece in tokens if piece[0].isalpha() and len(piece) > 1]
    return bool(operands) and all(
        word in _CALC_OBJECT_WORDS or word in MATH_FUNCTION_NAMES for word in words
    )


def _match_limit_point(s: str) -> tuple[str, int] | None:
    """Match infinity / oo / number at start of ``s``; return (token, end)."""
    low = s.lower()
    for tok in ("-infinity", "infinity", "-inf", "inf", "-oo", "oo"):
        if low.startswith(tok):
            return s[: len(tok)], len(tok)
    # The infinity sign itself, as the solver's ``oo``.
    for glyph, point in (("-∞", "-oo"), ("+∞", "oo"), ("∞", "oo")):
        if s.startswith(glyph):
            return point, len(glyph)
    start = 1 if s.startswith("-") else 0
    hit = _parse_unsigned_number(s, start)
    if hit is None or (start == 1 and hit[1] == 1):
        return None
    return s[: hit[1]], hit[1]


def _parse_signed_int_token(s: str) -> tuple[str, int] | None:
    start = 1 if s.startswith("-") else 0
    if start >= len(s) or not s[start].isdigit():
        return None
    i = start
    while i < len(s) and s[i].isdigit():
        i += 1
    return s[:i], i


@dataclass(frozen=True)
class LimitHit:
    expr: str
    var: str
    point: str
    direction: Literal["+", "-", "+-"] = "+-"


def _limit_direction(rest: str) -> tuple[Literal["+", "-", "+-"], str]:
    """Consume a direction without dropping an unrecognized expression tail."""
    attached = bool(rest) and not rest[0].isspace()
    rest = rest.lstrip()
    for token, direction in (
        ("from the left", "-"),
        ("from the right", "+"),
        ("from below", "-"),
        ("from above", "+"),
        ("^{-}", "-"),
        ("^{+}", "+"),
        ("^-", "-"),
        ("^+", "+"),
        ("-", "-"),
        ("+", "+"),
    ):
        if token in {"-", "+"} and not attached:
            continue
        if rest.lower().startswith(token):
            tail = rest[len(token) :]
            if not tail or tail[0].isspace() or tail[0] in "}?.":
                return ("-" if direction == "-" else "+"), tail.lstrip()
    return "+-", rest


def _read_operator_subscript(text: str, cmd: str) -> tuple[str, str] | None:
    """The variable that opens ``cmd``'s subscript (``\\lim_{x``), and the text after it."""
    idx = text.find(cmd)
    if idx == -1:
        return None
    rest = text[idx + len(cmd) :]
    while rest.startswith("_") or rest.startswith(" "):
        rest = rest[1:]
    if rest.startswith("{"):
        rest = rest[1:]
    rest = rest.lstrip(" ")
    if not rest or not rest[0].isalpha():
        return None
    return rest[0], rest[1:].lstrip(" ")


def _parse_latex_limit(text: str) -> LimitHit | None:
    """Parse ``\\lim_{x \\to 0} expr`` without optional-space regex pumps."""
    subscript = _read_operator_subscript(text, "\\lim")
    if subscript is None:
        return None
    var, rest = subscript
    arrow = None
    for candidate in ("\\to", "->", "→"):
        if rest.startswith(candidate):
            arrow = candidate
            break
    if arrow is None:
        return None
    rest = rest[len(arrow) :].lstrip(" ")
    point_hit = _match_limit_point(rest)
    if point_hit is not None:
        point, plen = point_hit
    elif rest.lower().startswith("-\\infty"):
        point, plen = "-\\infty", 7
    elif rest.lower().startswith("\\infty"):
        point, plen = "\\infty", 6
    else:
        return None
    direction, rest = _limit_direction(rest[plen:])
    if rest.startswith("}"):
        rest = rest[1:].lstrip(" ")
    expr = rest.strip()
    if not expr:
        return None
    return LimitHit(expr=expr, var=var, point=point, direction=direction)


def _parse_compact_limit(text: str, lower: str) -> LimitHit | None:
    """``lim x->0 expr`` / ``lim x→∞ expr``: the variable and arrow right after ``lim``."""
    idx = lower.find("lim ")
    rest = text[idx + 4 :].strip()
    if not rest:
        return None
    var = rest[0]
    if not var.isalpha():
        return None
    rest_l = rest[1:].lstrip()
    for arrow in ("->", "→"):
        if rest_l.startswith(arrow):
            rest_l = rest_l[len(arrow) :].lstrip()
            break
    else:
        return None
    point_hit = _match_limit_point(rest_l)
    if not point_hit:
        return None
    point, pend = point_hit
    direction, expr = _limit_direction(rest_l[pend:])
    if expr.lower().startswith("of "):
        expr = expr[3:].strip()
    if expr:
        return LimitHit(expr=expr, var=var, point=point, direction=direction)
    return None


# Words before " as x approaches …" that leave only the limit's expression.
_LIMIT_LEADS = (
    "find ",
    "evaluate ",
    "compute ",
    "what is ",
    "determine ",
    "the ",
    "limit of ",
    "limit ",
    "lim of ",
    "lim ",
)


def _parse_prose_limit(text: str, lower: str) -> LimitHit | None:
    """``expr as x approaches 0``, or ``limit as x approaches 2 of expr``."""
    as_idx = lower.find(" as ")
    before = text[:as_idx].strip()
    for lead in _LIMIT_LEADS:
        if before.lower().startswith(lead):
            before = before[len(lead) :].strip()
    after = text[as_idx + 4 :].strip()
    if not after or not after[0].isalpha():
        return None
    var = after[0]
    # The point is read lowercased; a trailing expression keeps its case.
    rest_cased = after[1:].lstrip()
    rest = rest_cased.lower()
    if len(rest) != len(rest_cased):
        rest_cased = rest
    for cue in ("approaches ", "goes to ", "tends to ", "->", "→", "to "):
        if rest.startswith(cue):
            rest = rest[len(cue) :].lstrip()
            rest_cased = rest_cased[len(cue) :].lstrip()
            break
    else:
        return None
    # prose uses "infinity" / "inf" / number (allow longer "infinity" spelling)
    point_hit = _match_limit_point(rest)
    if point_hit is None:
        for tok in ("-infinity", "infinity"):
            if rest.startswith(tok):
                point_hit = (tok, len(tok))
                break
    if not point_hit or not before:
        return None
    direction, tail = _limit_direction(rest_cased[point_hit[1] :])
    if before.lower() in {"limit", "lim"}:
        # "limit as x approaches 2 of (x^2-4)/(x-2)": the expression comes last.
        if not tail.lower().startswith("of "):
            return None
        expr = tail[3:].strip().rstrip(".?!").strip()
        if not looks_like_math_expr(expr):
            return None
        return LimitHit(expr=expr, var=var, point=point_hit[0], direction=direction)
    if tail.strip(" .?!"):
        return None
    return LimitHit(expr=before, var=var, point=point_hit[0], direction=direction)


def parse_limit(text: str) -> LimitHit | None:
    lower = text.lower()
    # Compact: lim x->0 expr. "lim (1+1/n)^n as n->infinity" falls to the prose form.
    if lower.startswith("lim ") or " lim " in f" {lower} ":
        compact = _parse_compact_limit(text, lower)
        if compact is not None:
            return compact
    # Prose: ... as x approaches 0
    if " as " in lower and ("limit" in lower or "lim" in lower):
        return _parse_prose_limit(text, lower)
    return _parse_latex_limit(text)


@dataclass(frozen=True)
class SeriesHit:
    expr: str
    var: str
    start: str
    end: str


def _parse_latex_series(text: str) -> SeriesHit | None:
    """Parse ``\\sum_{n=1}^{\\infty} expr`` without optional-space regex pumps."""
    subscript = _read_operator_subscript(text, "\\sum")
    if subscript is None:
        return None
    var, rest = subscript
    if not rest.startswith("="):
        return None
    rest = rest[1:].lstrip(" ")
    start_hit = _parse_signed_int_token(rest)
    if start_hit is None:
        return None
    start, send = start_hit
    rest = rest[send:].lstrip(" ")
    if rest.startswith("}"):
        rest = rest[1:].lstrip(" ")
    if not rest.startswith("^"):
        return None
    rest = rest[1:].lstrip(" ")
    if rest.startswith("{"):
        rest = rest[1:]
    rest = rest.lstrip(" ")
    end_tok: str | None = None
    low = rest.lower()
    for tok in ("\\infty", "infinity"):
        if low.startswith(tok):
            end_tok = rest[: len(tok)]
            rest = rest[len(tok) :]
            break
    if end_tok is None:
        end_hit = _parse_signed_int_token(rest)
        if end_hit is None:
            return None
        end_tok, eend = end_hit
        rest = rest[eend:]
    rest = rest.lstrip(" ")
    if rest.startswith("}"):
        rest = rest[1:].lstrip(" ")
    expr = rest.strip()
    if not expr:
        return None
    return SeriesHit(expr=expr, var=var, start=start, end=end_tok)


def parse_series(text: str) -> SeriesHit | None:
    lower = text.lower()
    if not any(k in lower for k in ("sum ", "series", "converge", "diverge")):
        # also bare "sum of"
        if "sum" not in lower:
            return None
    # Bounds-first prose: ``sum from n=0 to infinity of (-1)^n``.
    # This must run before equation extraction sees the lower bound as ``n=0``.
    bounds_head = "sum from "
    bounds_at = lower.find(bounds_head)
    if bounds_at != -1:
        rest = text[bounds_at + len(bounds_head) :].strip()
        to_at = rest.lower().find(" to ")
        if to_at != -1:
            lower_bound = rest[:to_at].replace(" ", "")
            after_to = rest[to_at + 4 :].strip()
            of_at = after_to.lower().find(" of ")
            if of_at != -1 and "=" in lower_bound:
                var, start = lower_bound.split("=", 1)
                end = after_to[:of_at].strip()
                expr = after_to[of_at + 4 :].strip().rstrip(".?!")
                low_expr = expr.lower()
                for suffix in (
                    " converges or diverges",
                    " converge or diverge",
                    " is convergent or divergent",
                ):
                    if low_expr.endswith(suffix):
                        expr = expr[: -len(suffix)].rstrip()
                        break
                start_hit = _parse_signed_int_token(start)
                end_low = end.lower()
                valid_end = end_low in {"infinity", "inf", "oo"} or (
                    _parse_signed_int_token(end) or (None, 0)
                )[1] == len(end)
                if (
                    len(var) == 1
                    and var.isalpha()
                    and start_hit is not None
                    and start_hit[1] == len(start)
                    and valid_end
                    and expr
                ):
                    return SeriesHit(expr=expr, var=var, start=start, end=end)

    # sum|series [of] EXPR from VAR=START to END
    for head in ("sum of ", "series of ", "sum ", "series "):
        idx = lower.find(head)
        if idx == -1:
            continue
        rest = text[idx + len(head) :]
        # "sum k^2 from k=1 to 10" or "sum k^2 for k=1 to 10".
        joint = " from " if " from " in rest.lower() else " for "
        from_idx = rest.lower().find(joint)
        if from_idx == -1:
            continue
        expr = rest[:from_idx].strip()
        if joint == " for " and not looks_like_math_expr(expr):
            # "sum my expenses for k=1 to 10" names no term.
            continue
        tail = rest[from_idx + len(joint) :].strip()
        parts = tail.replace(" ", "")
        # var=START to END — linear scan on compacted digits
        if not parts or not parts[0].isalpha():
            continue
        var = parts[0]
        if len(parts) < 2 or parts[1] != "=":
            continue
        after_eq = parts[2:]
        start_hit = _parse_signed_int_token(after_eq)
        if start_hit is None:
            continue
        start, send = start_hit
        after_start = after_eq[send:]
        if not after_start.lower().startswith("to"):
            continue
        after_to = after_start[2:]
        end_tok: str | None = None
        low_end = after_to.lower()
        for tok in ("infinity", "inf", "oo"):
            if low_end.startswith(tok):
                end_tok = after_to[: len(tok)]
                break
        if end_tok is None:
            end_hit = _parse_signed_int_token(after_to)
            if end_hit is None:
                continue
            end_tok = end_hit[0]
        if expr:
            return SeriesHit(expr=expr, var=var, start=start, end=end_tok)
    return _parse_latex_series(text)


def integral_bounds(expr: str) -> tuple[str, str, str] | None:
    """Return (expr_without_bounds, lo, hi) for trailing ``from LO to HI``."""
    lower = expr.lower()
    idx = lower.rfind(" from ")
    if idx == -1:
        return None
    head = expr[:idx].strip()
    tail = expr[idx + 6 :].strip()
    to_idx = tail.lower().find(" to ")
    if to_idx == -1:
        return None
    lo = tail[:to_idx].strip()
    hi = tail[to_idx + 4 :].strip()
    if head and lo and hi and " " not in hi:
        return head, lo, hi
    return None
