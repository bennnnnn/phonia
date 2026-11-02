"""Definitions in a request: ``y = …`` peeled to its expression, ``let x = 5`` substituted."""

from __future__ import annotations

import re

from app.modules.math.match.letter_runs import looks_like_math_expr
from app.modules.math.tools.request_text import _MAX_MATH_INPUT, _strip_expr_leadins
from app.services.text_normalize import collapse_ws


def _is_named_function_lhs(left: str) -> bool:
    """``y`` or ``f(x)`` — a definition lhs, not ``2x+3``."""
    compact = left.replace(" ", "")
    if len(compact) == 1 and compact.isalpha():
        return True
    return (
        len(compact) == 4
        and compact[0].isalpha()
        and compact[1] == "("
        and compact[2].isalpha()
        and compact[3] == ")"
    )


_EVAL_AFTER_GIVEN_CUES = (
    "what is",
    "what's",
    "whats",
    "compute ",
    "evaluate ",
    "calculate ",
)

_ASSIGNMENT_START_RE = re.compile(r"\b[a-zA-Z]\s*=")
_EVALUATION_REQUEST_RE = re.compile(
    r"\b(?:evaluate|compute|calculate|what\s+is|what's|whats)\b", re.IGNORECASE
)


def has_assignment_evaluation_request(text: str) -> bool:
    """Recognize a requested evaluation even if its expression cannot parse.

    Inspect raw text: removing math delimiters can join ``Evaluate$x`` into
    ``Evaluatex`` and hide the cue. A binding is context for the later ask,
    not a standalone equation whose solution completes that ask.
    """
    if len(text) > _MAX_MATH_INPUT:
        return False
    assignment = _ASSIGNMENT_START_RE.search(text)
    return bool(assignment and _EVALUATION_REQUEST_RE.search(text, assignment.end()))


def substituted_eval_expr(cleaned: str) -> str | None:
    """``Let x = 5. What is x + 2?`` → ``5+2``. Bare ``let x = 5`` stays None."""
    if len(cleaned) > _MAX_MATH_INPUT:
        return None
    from app.modules.math import solve as math_solve

    eq_pairs = math_solve.try_extract_equations_from_text(cleaned)
    if len(eq_pairs) != 1:
        return None
    lhs, rhs = eq_pairs[0]
    left = lhs.replace(" ", "")
    if len(left) != 1 or not left.isalpha():
        return None
    compact_rhs = rhs.replace(" ", "")
    sign = ""
    if compact_rhs.startswith("-"):
        sign = "-"
        compact_rhs = compact_rhs[1:]
    if not compact_rhs or compact_rhs.count(".") > 1:
        return None
    if not all(ch.isdigit() or ch == "." for ch in compact_rhs):
        return None
    eq_at = cleaned.find("=")
    if eq_at == -1:
        return None
    rest = cleaned[eq_at + 1 :]
    rest_l = rest.lower()
    cue_at = -1
    cue_len = 0
    for cue in _EVAL_AFTER_GIVEN_CUES:
        found = rest_l.find(cue)
        if found != -1 and (cue_at == -1 or found < cue_at):
            cue_at = found
            cue_len = len(cue)
    if cue_at == -1:
        return None
    expr = rest[cue_at + cue_len :].strip()
    while expr and expr[-1] in "?.!":
        expr = expr[:-1].rstrip()
    if not expr:
        return None
    # A substituted negative base must keep its grouping under powers.
    replacement = f"({sign}{compact_rhs})" if sign else compact_rhs
    var = left.lower()
    out: list[str] = []
    i = 0
    saw_var = False
    while i < len(expr):
        ch = expr[i]
        isolated = (i == 0 or not expr[i - 1].isalpha()) and (
            i + 1 >= len(expr) or not expr[i + 1].isalpha()
        )
        if ch.lower() == var and isolated:
            adjacent_factor = (i > 0 and (expr[i - 1].isdigit() or expr[i - 1] == ")")) or (
                i + 1 < len(expr) and (expr[i + 1].isdigit() or expr[i + 1] == "(")
            )
            out.append(f"({replacement})" if adjacent_factor else replacement)
            saw_var = True
            i += 1
            continue
        out.append(ch)
        i += 1
    if not saw_var:
        return None
    result = "".join(out).replace(" ", "")
    if any(ch.isalpha() for ch in result) or not any(ch.isdigit() for ch in result):
        return None
    return result


def peel_function_definition(expr: str) -> str:
    """``y = x^3 - 3x`` / ``of y = …`` / ``if y = …`` → the rhs expression."""
    s = _strip_expr_leadins(collapse_ws(expr))
    if len(s) > _MAX_MATH_INPUT:
        s = s[:_MAX_MATH_INPUT]
    low = s.lower()
    if low.startswith("if "):
        s = s[3:].lstrip()
        s = _strip_expr_leadins(s)
    eq = s.find("=")
    if eq == -1:
        return s
    left = s[:eq].strip()
    right = s[eq + 1 :].strip()
    if _is_named_function_lhs(left) and looks_like_math_expr(right):
        return right
    return s
