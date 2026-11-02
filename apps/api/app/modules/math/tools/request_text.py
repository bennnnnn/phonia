"""The words around a maths expression: filler, lead-ins and the clause that follows it."""

from __future__ import annotations

from app.modules.math.match.scan import CALC_OP_SPELLINGS, ddx_cue_at, ddx_expr_after
from app.services.text_normalize import collapse_ws

# Cap before any poly-time regex. CodeQL only treats a const length compare as a
# ReDoS sanitizer — collapsing whitespace alone is not enough.
_MAX_MATH_INPUT = 1000


def _strip_series_prefix(expr: str) -> str:
    s = collapse_ws(expr)
    if len(s) > _MAX_MATH_INPUT:
        return s[:_MAX_MATH_INPUT]
    prev = None
    while prev != s:
        prev = s
        lower = s.lower()
        for prefix in (
            "does the series ",
            "does the sum ",
            "the series ",
            "the sum ",
            "series ",
            "sum ",
            "of ",
        ):
            if lower.startswith(prefix):
                s = s[len(prefix) :].strip()
                break
        else:
            break
    return s


_TRAILING_FILLER_SUFFIXES = (
    " please",
    " please.",
    " now",
    " now.",
    " thank",
    " thanks",
    " thanks.",
    " thank you",
    " thank you.",
    " for me",
    " for me.",
    " to me",
    " to me.",
    " real quick",
    " real quick.",
    " quickly",
    " quickly.",
    " briefly",
    " briefly.",
)


def _split_and_then(s: str) -> str:
    """Keep text before the first `` and `` / `` then `` clause (no regex)."""
    lower = s.lower()
    cut: int | None = None
    for token in (" and ", " then "):
        idx = lower.find(token)
        if idx != -1 and (cut is None or idx < cut):
            cut = idx
    return s[:cut] if cut is not None else s


_RESPONSE_SENTENCE_STARTS = (
    "show ",
    "use ",
    "explain ",
    "state ",
    "name ",
    "list ",
    "check ",
    "verify ",
    "include ",
    "keep ",
    "reject ",
    "preserve ",
    "identify ",
    "enumerate ",
)


def _split_response_instruction_sentence(s: str) -> str:
    """Peel a trailing presentation instruction from a captured expression.

    Requests such as ``... = 7. Show every step`` used to feed the second
    sentence into SymPy, disabling verification and allowing an unrelated
    algebra fallback. Only an explicit response/presentation verb is peeled;
    decimal points and a second mathematical question remain untouched.
    """
    lower = s.lower()
    for index, char in enumerate(s):
        if char not in ".?!":
            continue
        tail = lower[index + 1 :].lstrip()
        if any(tail.startswith(prefix) for prefix in _RESPONSE_SENTENCE_STARTS):
            return s[:index]
    return s


def strip_trailing_filler(expr: str) -> str:
    """`_GRAPH_EXPR`/the calculus expr-match are greedy captures of everything
    after the trigger word, so natural phrasing like "graph x^2 please" or
    "differentiate x^2 for me" sweeps the trailing words into the
    "expression" — which then fails to parse and silently disables the
    verified-math augmentation for phrasing a real user would actually type."""
    s = collapse_ws(expr)
    # Const length compare must sit in this function for CodeQL's ReDoS barrier.
    if len(s) > _MAX_MATH_INPUT:
        return s[:_MAX_MATH_INPUT]
    s = _split_response_instruction_sentence(s)
    # A conjunction essentially never appears inside a math expression
    # itself — anything from " and "/" then " onward is a new clause of
    # natural language (e.g. "sin(x) and explain it"), not part of the expr.
    s = _split_and_then(s)
    prev = None
    while prev != s:
        prev = s
        lower = s.lower()
        for suffix in _TRAILING_FILLER_SUFFIXES:
            if lower.endswith(suffix):
                s = s[: -len(suffix)].rstrip()
                break
    while s and s[-1] in ".?!":
        s = s[:-1].rstrip()
    return s


_EXPR_LEADINS = (
    "the polynomial ",
    "the expression ",
    "the function ",
    "the equation ",
    "polynomial ",
    "expression ",
    "function ",
    "equation ",
    "of ",
    "the ",
)


def _strip_expr_leadins(expr: str) -> str:
    """Drop scaffolding words so ``factor the polynomial x^3 - 1`` keeps ``x^3 - 1``."""
    s = collapse_ws(expr)
    if len(s) > _MAX_MATH_INPUT:
        return s[:_MAX_MATH_INPUT]
    prev = None
    while prev != s:
        prev = s
        lower = s.lower()
        for prefix in _EXPR_LEADINS:
            if lower.startswith(prefix):
                s = s[len(prefix) :].strip()
                break
        else:
            break
    for cue in (" with respect to ", " wrt "):
        wrt = s.lower().find(cue)
        if wrt != -1:
            s = s[:wrt].rstrip()
    return s


_CALC_VERBS = (
    "simplify",
    "differentiate",
    "derivative",
    "integrate",
    "integral",
    "factor",
    "expand",
    # The spellings ``calc_op`` reads as one of the verbs above.
    *CALC_OP_SPELLINGS,
)


def _calc_expr_tail(cleaned: str) -> str | None:
    """Text after the first calculus verb (index scan — avoids poly regex)."""
    lower = cleaned.lower()
    best_at: int | None = None
    best_end = 0
    for verb in _CALC_VERBS:
        needle = f"{verb} "
        idx = lower.find(needle)
        if idx != -1 and (best_at is None or idx < best_at):
            best_at = idx
            best_end = idx + len(needle)
    ddx_tail = ddx_expr_after(cleaned)
    if ddx_tail is not None:
        ddx = ddx_cue_at(cleaned)
        if ddx is not None and (best_at is None or ddx < best_at):
            return ddx_tail
    # ``∫ (3x^2 + 2x) dx``: the integral sign is the verb, never part of the integrand.
    sign_at = cleaned.find("∫")
    if sign_at != -1 and (best_at is None or sign_at < best_at):
        return cleaned[sign_at + 1 :].lstrip()
    if best_at is None:
        of_at = lower.find(" of ")
        if of_at != -1 and "'" in cleaned[:of_at]:
            return cleaned[of_at + 4 :]
        return None
    return cleaned[best_end:]
