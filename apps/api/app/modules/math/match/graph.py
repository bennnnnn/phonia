"""Coordinate / plot / graph-expression cues."""

from __future__ import annotations

import math
import re

from app.modules.math.match.letter_runs import (
    VIZ_COMMANDS,
    _alpha_run_end,
    has_viz_command,
    looks_like_math_expr,
    split_glued_viz_runs,
)
from app.modules.math.match.scan import _BARE_COORD, strip_inline_math_delims
from app.services.number_text import DECIMAL_LITERAL

_GRAPH_PLOT_PREFIXES = ("graph ", "plot ")
# Plot verbs that must not steal geometry (`draw a triangle`) or Vega
# (`chart of rainfall`). Accepted only when the remainder is function-like.
_GRAPH_PLOT_SOFT_PREFIXES = (
    "draw ",
    "sketch ",
    "visualize ",
    "visualise ",
    "chart ",
    "show ",
)
_LOOKS_LIKE_CUES = ("look like", "looks like", "shape of")


def _find_unprefixed_phrase(lower: str, phrase: str, start: int = 0) -> int:
    """Find an actual visual command, excluding words inside other words or negation."""
    while True:
        idx = lower.find(phrase, start)
        if idx == -1:
            return -1
        if idx == 0 or not lower[idx - 1].isalpha():
            before = lower[max(0, idx - 24) : idx]
            # Presentation constraints are not commands: "no graph",
            # "without a plot", and "do not graph it" must leave the math
            # request available to the equation/inequality extractors.
            if (
                re.search(
                    r"(?:^|\b)(?:no|not|without|do\s+not|don['\u2019]?t)"
                    r"(?:\s+(?:a|an|the))?\s*$",
                    before,
                )
                is None
            ):
                return idx
        start = idx + 1


def _has_unprefixed_graph_or_plot(lower: str) -> bool:
    return any(_find_unprefixed_phrase(lower, prefix) != -1 for prefix in _GRAPH_PLOT_PREFIXES)


def _last_unprefixed_prefix(lower: str, prefixes: tuple[str, ...]) -> tuple[int, str] | None:
    last: tuple[int, str] | None = None
    for prefix in prefixes:
        start = 0
        while True:
            idx = _find_unprefixed_phrase(lower, prefix, start)
            if idx == -1:
                break
            if last is None or idx >= last[0]:
                last = (idx, prefix)
            start = idx + 1
    return last


def _last_unprefixed_graph_or_plot(lower: str) -> tuple[int, str] | None:
    return _last_unprefixed_prefix(lower, _GRAPH_PLOT_PREFIXES)


def _core_before_and_then(expr: str) -> str:
    """Text before the first `` and `` / `` then `` clause (no regex)."""
    lower = expr.lower()
    cut: int | None = None
    for token in (" and ", " then "):
        idx = lower.find(token)
        if idx != -1 and (cut is None or idx < cut):
            cut = idx
    s = expr[:cut] if cut is not None else expr
    return s.rstrip(" .?!")


def _parse_bound(token: str) -> float | None:
    """Parse a graph-domain bound: a plain number, ``pi``, ``-pi``, or ``N*pi``
    (``2pi`` / ``2*pi`` / ``0.5pi``). Returns None for anything unparseable so
    the caller falls back to the default window rather than mis-sampling."""
    t = token.strip().lower().replace("π", "pi").replace(" ", "")
    if not t:
        return None
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    denominator = 1.0
    if "/" in t:
        numerator, raw_denominator = t.split("/", 1)
        try:
            denominator = float(raw_denominator)
        except ValueError:
            return None
        if denominator == 0:
            return None
        t = numerator
    if t == "pi":
        val = math.pi
    elif t.endswith("pi"):
        coeff = t[:-2].rstrip("*")
        if coeff == "":
            return None
        try:
            val = float(coeff) * math.pi
        except ValueError:
            return None
    else:
        try:
            val = float(t)
        except ValueError:
            return None
    val /= denominator
    return -val if neg else val


# "from <lo> to <hi>" / "between <lo> and <hi>" / "on [<lo>, <hi>]" — the
# domain the user wants plotted. Bounds may be plain numbers or pi multiples
# (``pi``, ``2pi``, ``-pi``). Each pattern captures the two bound tokens.
_GRAPH_BOUND = (
    r"-?(?:\d+(?:\.\d+)?|\.\d+)"
    r"|-?(?:\d+(?:\.\d+)?\s*\*?\s*)?(?:pi|π)(?:\s*/\s*\d+(?:\.\d+)?)?"
)
_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\bfrom\s+({_GRAPH_BOUND})\s+to\s+({_GRAPH_BOUND})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bbetween\s+({_GRAPH_BOUND})\s+and\s+({_GRAPH_BOUND})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bon\s*\[\s*({_GRAPH_BOUND})\s*,\s*({_GRAPH_BOUND})\s*\]",
        re.IGNORECASE,
    ),
)


def graph_domain(expr: str) -> tuple[float, float, str] | None:
    """Extract a user-named plotting domain from a graph expression.

    Returns ``(lo, hi, expr_without_domain)`` when a domain clause is found,
    else None. The domain clause is stripped from the returned expression so
    SymPy never sees ``"from 0 to 100"`` as part of the formula. The LAST
    match wins (a leading "from … to …" describing something else is rare,
    but the trailing domain is what the user intends as the window).
    """
    last: tuple[int, int, str, str] | None = None  # (start, end, lo_tok, hi_tok)
    for pat in _DOMAIN_PATTERNS:
        for m in pat.finditer(expr):
            if last is None or m.start() >= last[0]:
                last = (m.start(), m.end(), m.group(1), m.group(2))
    if last is None:
        return None
    lo = _parse_bound(last[2])
    hi = _parse_bound(last[3])
    if lo is None or hi is None or lo >= hi:
        return None
    cleaned = (expr[: last[0]] + expr[last[1] :]).strip()
    return lo, hi, cleaned


def _parse_xy_pair(token: str) -> tuple[float, float] | None:
    """Parse ``x,y`` or mobile-slip ``x.y`` (comma key next to period)."""
    compact = token.replace(" ", "")
    if compact.startswith("(") and compact.endswith(")"):
        compact = compact[1:-1]
    if "," in compact:
        parts = compact.split(",", 1)
    elif compact.count(".") == 1:
        # "2.3" keyboard slip for "2,3"
        parts = compact.split(".", 1)
    else:
        return None
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def bare_coord(text: str) -> tuple[float, float] | None:
    compact = text.replace(" ", "")
    m = _BARE_COORD.match(compact)
    if m:
        return float(m.group("x")), float(m.group("y"))
    # "(2.3)" slip
    if compact.startswith("(") and compact.endswith(")"):
        return _parse_xy_pair(compact)
    return None


def plot_point(text: str) -> tuple[float, float] | None:
    lower = text.lower()
    if "point" not in lower:
        return None
    cues = ("plot ", "mark ", "graph ", "show ", "mark point")
    if not any(_find_unprefixed_phrase(lower, v) != -1 for v in cues):
        return None
    idx = lower.find("point")
    rest = text[idx + len("point") :].strip()
    if rest.startswith("("):
        close_p = rest.find(")")
        if close_p != -1:
            return _parse_xy_pair(rest[: close_p + 1])
    # "mark point 2, 3"
    return _parse_xy_pair(rest.split(")")[0])


_BARE_YF_SKIP_CUES = (
    "solve",
    "roots of",
    "zeros of",
    "find x",
    "for x when",
    "when x",
)


def _strip_wrapping_math_delims(text: str) -> str:
    s = text.strip()
    if len(s) >= 2 and s.startswith("$") and s.endswith("$"):
        return s[1:-1].strip()
    return s


def _bare_y_equals_rhs(text: str) -> str | None:
    """A message that's just ``y = f(x)`` (optionally wrapped in ``$...$``).

    The model is prompted to emit a ```graph fence for y=f(x). Without a
    verified sample, that invented JSON usually has no points and the
    post-stream rewriter turns it into "Could not render that diagram."
    """
    lower = text.lower()
    if any(cue in lower for cue in _BARE_YF_SKIP_CUES):
        return None
    stripped = _strip_wrapping_math_delims(text).rstrip(".!?")
    if stripped.count("=") != 1:
        return None
    lower_s = stripped.lower()
    if lower_s.startswith("y="):
        rhs = stripped[2:].lstrip()
    elif lower_s.startswith("y ="):
        rhs = stripped[3:].lstrip()
    else:
        return None
    if not rhs or len(rhs) > 120:
        return None
    compact = rhs.replace(" ", "").lower()
    if "x" in compact:
        return rhs
    try:
        float(compact)
    except ValueError:
        return None
    return rhs


_GRAPH_Y_PREFIXES = (
    "graph ",
    "plot ",
    "draw ",
    "sketch ",
    "visualize ",
    "visualise ",
    "chart ",
    "y=",
    "y =",
)


def _peel_repeated_graph_y_prefix(expr: str) -> str:
    """Unstack duplicated ``Graph y =`` / ``plot y =`` prefixes.

    The composer math keyboard (or a leftover ``Graph y =`` plus a second
    typed prompt) produces ``Graph y =Graph y = x²``. One-shot strip left
    ``Graph y = x^2``, which SymPy read as G·r·a·p·h·y = x² — no plot, and
    the model dumped a point table plus ASCII sketch instead.
    """
    s = expr.strip()
    prev = None
    while s and s != prev:
        prev = s
        low = s.lower()
        matched = False
        for prefix in _GRAPH_Y_PREFIXES:
            if low.startswith(prefix):
                s = s[len(prefix) :].lstrip()
                matched = True
                break
        if not matched:
            break
    return _collapse_keyboard_graph_rhs(s)


def _is_keyboard_leftover_lhs(lhs: str) -> bool:
    """True for ``x`` / ``x^`` / ``x^= x^`` junk, not ``2x+3`` or ``2x``."""
    compact = "".join(c for c in lhs.lower() if c not in " =")
    if not compact:
        return True
    return "x" in compact and all(c in "x^" for c in compact)


def _collapse_keyboard_graph_rhs(expr: str) -> str:
    """After peeling ``Graph y =``, leftover ``x^= x^2`` / ``x= x^2`` from ``$``.

    The keypad wrap ``y$= x^$$= x^2`` becomes ``x^= x^2``; taking the last
    f(x)-shaped RHS recovers the parabola. Keep ``x=2y`` / ``x=4`` /
    ``2x+3=x^2`` intact.
    """
    s = expr.strip()
    if "=" not in s:
        return s
    lhs, _, rhs = s.rpartition("=")
    lhs, rhs = lhs.strip(), rhs.strip()
    if not rhs:
        return s
    rhs_c = rhs.replace(" ", "").lower()
    # ``x=2y`` / ``x=4`` — real equations for the graph solver.
    if "y" in rhs_c and "x" not in rhs_c:
        return s
    if not _is_keyboard_leftover_lhs(lhs):
        return s
    if "x" not in rhs_c:
        return s
    return rhs


# Pronouns of two letters read as implicit multiplication — "me" is m*e, "it"
# is i*t, "us" is u*s — so looks_like_math_expr accepts them and "show me"
# asked to plot a function called me. Longer ones ("this", "him") already fail
# has_unknown_english_run. Real two-letter products like "ab" must keep
# working, so this is an explicit table rather than a length rule, matching
# this module's existing preference for phrase tables over fuzzy heuristics.
_PRONOUN_PLOT_CORES = frozenset(
    (
        "me",
        "it",
        "us",
        "them",
        "him",
        "her",
        "this",
        "that",
        "these",
        "those",
        "mine",
        "yours",
        "ours",
        "theirs",
        "myself",
        "itself",
        "one",
    )
)


def _function_like_plot_core(expr: str) -> bool:
    """True for ``x^2`` / ``y=x^2`` / ``sin(x)``, not ``a triangle`` / ``of rainfall``."""
    core = _core_before_and_then(_peel_repeated_graph_y_prefix(expr)).rstrip(" .?!")
    words = core.lower().split()
    if words and all(word in _PRONOUN_PLOT_CORES for word in words):
        return False
    if looks_like_math_expr(core):
        return True
    compact = core.replace(" ", "").lower()
    if compact.startswith("y=") or compact.startswith("x="):
        return looks_like_math_expr(core.split("=", 1)[-1])
    return False


def _expr_after_prefix(text: str, idx: int, prefix: str) -> str:
    return _peel_repeated_graph_y_prefix(text[idx + len(prefix) :].strip())


def _soft_plot_prefix_expr(text: str) -> str | None:
    """``draw y=x^2`` / ``chart y=x^2`` — only when the remainder is f(x)."""
    lower = text.lower()
    first: tuple[int, str] | None = None
    for prefix in _GRAPH_PLOT_SOFT_PREFIXES:
        idx = _find_unprefixed_phrase(lower, prefix)
        if idx != -1:
            first = (idx, prefix)
            break
    if first is None:
        return None
    idx, prefix = first
    expr = _expr_after_prefix(text, idx, prefix)
    if _function_like_plot_core(expr):
        return expr or None
    last = _last_unprefixed_prefix(lower, _GRAPH_PLOT_SOFT_PREFIXES)
    if last is not None and last[0] != idx:
        expr = _expr_after_prefix(text, last[0], last[1])
        if _function_like_plot_core(expr):
            return expr or None
    return None


def _expr_from_looks_like_ask(text: str) -> str | None:
    """``what does y=x^2 look like`` / ``show the shape of y=x^2``."""
    lower = text.lower()
    if not any(cue in lower for cue in _LOOKS_LIKE_CUES):
        return None
    marker = "y="
    idx = lower.find(marker)
    if idx == -1:
        marker = "y ="
        idx = lower.find(marker)
    if idx == -1:
        return None
    rest = text[idx + len(marker) :]
    rest_low = rest.lower()
    cut: int | None = None
    for cue in _LOOKS_LIKE_CUES:
        padded = f" {cue}"
        at = rest_low.find(padded)
        if at != -1 and (cut is None or at < cut):
            cut = at
        at = rest_low.find(cue)
        if at == 0:
            cut = 0
    if cut is not None:
        rest = rest[:cut]
    rest = rest.strip().rstrip(" .?!")
    if not rest or not _function_like_plot_core(rest):
        return None
    return _peel_repeated_graph_y_prefix(rest) or None


def graph_expr(text: str) -> str | None:
    lower = text.lower()
    first: tuple[int, str] | None = None
    for prefix in _GRAPH_PLOT_PREFIXES:
        idx = _find_unprefixed_phrase(lower, prefix)
        if idx != -1:
            first = (idx, prefix)
            break
    if first is None:
        soft = _soft_plot_prefix_expr(text)
        if soft is not None:
            return soft
        look = _expr_from_looks_like_ask(text)
        if look is not None:
            return look
        return _bare_y_equals_rhs(text)

    idx, prefix = first
    expr = _expr_after_prefix(text, idx, prefix)
    # Duplicated "Graph y = Graph y = x^2" is peeled from the first capture.
    # "graph this: graph y=x^2" still has a later command and a non-math core
    # — take the last unprefixed graph/plot instead. "graph y=x^2 then plot
    # a table" keeps the first capture: the core before " then " is math.
    if _has_unprefixed_graph_or_plot(expr.lower()) and not looks_like_math_expr(
        _core_before_and_then(expr)
    ):
        last = _last_unprefixed_graph_or_plot(lower)
        if last is not None and last[0] != idx:
            idx, prefix = last
            expr = _expr_after_prefix(text, idx, prefix)
    # "graph me" / "plot us" reach here rather than the soft-prefix path, so
    # they need the same pronoun guard — an explicit "graph" is a strong cue
    # but still does not make a pronoun plottable.
    words = expr.lower().rstrip(" .?!").split()
    if words and all(word in _PRONOUN_PLOT_CORES for word in words):
        return None
    return expr or None


_GRAPH_PAIR_PREFIXES = ("graph ", "plot ", "compare ")
_GRAPH_PAIR_TRAILING_FILLER = (
    " on the same graph",
    " on the same plot",
    " on the same axes",
    " on one graph",
    " together",
)
_EXPR_CANDIDATE_CHARS = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZπ+-*/().^= ."
)
# "plot sin(x) and explain it" must NOT be read as a second function named
# "explain it" — an explicit denylist (matching this module's existing
# preference for phrase tables over fuzzy heuristics) catches ordinary
# trailing prose that first_dim_pair-style character scanning can't.
_PROSE_WORDS = frozenset(
    (
        "explain",
        "it",
        "please",
        "why",
        "how",
        "what",
        "tell",
        "describe",
        "me",
        "this",
        "that",
        "show",
        "draw",
        "the",
        "a",
        "an",
        "is",
        "are",
        "these",
        "functions",
        "function",
        "curve",
        "curves",
        "then",
    )
)


def _strip_leading_y_equals(expr: str) -> str:
    lower = expr.lower()
    if lower.startswith("y="):
        return expr[2:].lstrip()
    if lower.startswith("y ="):
        return expr[3:].lstrip()
    return expr


def _looks_like_expr_candidate(s: str) -> bool:
    stripped = s.strip()
    if not stripped or len(stripped) > 120:
        return False
    if not all(c in _EXPR_CANDIDATE_CHARS for c in stripped):
        return False
    return not any(w in _PROSE_WORDS for w in stripped.lower().split())


def graph_expr_pair(text: str) -> tuple[str, str] | None:
    """ "graph EXPR1 and EXPR2 [on the same graph]" -> (EXPR1, EXPR2). Only
    matches when exactly one " and " splits the post-trigger text into two
    non-empty, expression-shaped candidates — checked BEFORE the single-
    expression graph_expr so a two-function ask doesn't get garbled into one
    unparseable expr, but a plain "plot sin(x) and explain it" still falls
    through to the single-expression path instead of treating "explain it"
    as a second function."""
    lower = text.lower()
    for prefix in _GRAPH_PAIR_PREFIXES:
        idx = _find_unprefixed_phrase(lower, prefix)
        if idx == -1:
            continue
        rest = text[idx + len(prefix) :].strip()
        and_idx = rest.lower().find(" and ")
        if and_idx == -1:
            continue
        first = _strip_leading_y_equals(rest[:and_idx].strip())
        # Sentence punctuation belongs to the request, not the second
        # expression or a presentation suffix ("on the same graph."). Keep
        # ``!`` because it may be a factorial that must not be dropped.
        second = rest[and_idx + len(" and ") :].strip().rstrip(".?")
        second_lower = second.lower()
        for suffix in _GRAPH_PAIR_TRAILING_FILLER:
            if second_lower.endswith(suffix):
                second = second[: -len(suffix)].strip()
                break
        second = _strip_leading_y_equals(second)
        if _looks_like_expr_candidate(first) and _looks_like_expr_candidate(second):
            return first, second
    return None


def vertical_line_x(text: str) -> float | None:
    """``x = 4`` after a graph cue — not ``3x=9`` and not when ``y=`` is present.

    Glued ``X=6graph`` / ``graphx=4`` / ``X=$6$graph`` still count: viz
    commands are tokens, not multiplied letters.
    """
    if not has_viz_command(text):
        return None
    lower = split_glued_viz_runs(strip_inline_math_delims(text).lower())
    if _standalone_equals(lower, "y") is not None:
        return None
    idx = 0
    while True:
        hit = _standalone_equals(lower, "x", start=idx)
        if hit is None:
            return None
        eq_at, after_eq = hit
        m = DECIMAL_LITERAL.match(lower, after_eq)
        if m is None:
            idx = eq_at + 1
            continue
        end = m.end()
        rest = lower[end:].lstrip()
        if rest:
            if rest[0] in "*/^(":
                idx = end
                continue
            if rest[0].isalnum():
                token_end = _alpha_run_end(rest, 0)
                token = rest[:token_end]
                if token not in VIZ_COMMANDS:
                    idx = end
                    continue
                leftover = rest[token_end:].lstrip(".,!? ")
                if leftover and (leftover[0].isalnum() or leftover[0] in "*/^("):
                    idx = end
                    continue
        return float(m.group(0))


def _standalone_equals(lower: str, letter: str, start: int = 0) -> tuple[int, int] | None:
    """Index of ``letter =`` not preceded by a digit/letter; scan from ``start``.

    Returns ``(equals_index, index_after_optional_spaces)`` for the number scan.
    """
    n = len(lower)
    i = start
    while i < n:
        if lower[i] == letter and (i == 0 or not lower[i - 1].isalnum()):
            j = i + 1
            while j < n and lower[j] in " \t":
                j += 1
            if j < n and lower[j] == "=":
                k = j + 1
                while k < n and lower[k] in " \t":
                    k += 1
                return j, k
        i += 1
    return None
