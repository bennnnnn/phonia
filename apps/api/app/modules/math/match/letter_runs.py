"""Letter runs in a maths message: which are English, which are maths names or viz commands.

A run of three or more letters that is not a maths name (``sin``, ``pi``, ``gcd``) is English
or a command, never a product of one-letter variables: ``6graph`` must not guess g, r, a, p, h.
Linear scans, no regex (CodeQL-safe).
"""

from __future__ import annotations

from app.modules.math.function_names import MATH_FUNCTION_NAMES

# Multi-letter tokens SymPy already treats as one name. Any other 3+ letter
# run is English or a command — never g*r*a*p*h, and never ``squared``/``plus``
# slipping into letter-products.
MATH_MULTI_LETTER = MATH_FUNCTION_NAMES | frozenset(
    {
        "min",
        "max",
        "pi",
        "oo",
        "inf",
        "infinity",
        "nan",
        "det",
        "gcd",
        "lcm",
        "mod",
        "theta",
    }
)
VIZ_COMMANDS = frozenset(
    {
        "graph",
        "plot",
        "draw",
        "show",
        "sketch",
        "visualize",
        "visualise",
        "vertical",
    }
)
# Only these may glue onto a following 1-letter variable (``graphx=4``).
# ``show``/``draw`` are too common as English prefixes (``shown``, ``drawn``).
_GLUEABLE_VIZ = frozenset({"graph", "plot"})


def _alpha_run_end(s: str, start: int) -> int:
    j = start
    n = len(s)
    while j < n and s[j].isalpha():
        j += 1
    return j


def _looks_like_math_core(s: str) -> bool:
    if not s:
        return False
    if any(ch.isdigit() for ch in s):
        return True
    if any(ch in "+-*/^()" for ch in s):
        return True
    letters = [ch for ch in s if ch.isalpha()]
    return len(letters) == 1


def peel_edge_english(side: str) -> str:
    """Trim unknown 3+ letter runs glued to an equation side.

    ``X=6graph`` → RHS ``6``. ``velocity=12`` stays (the whole side is the
    name). ``E=mc^2`` is untouched (2-letter ``mc`` is implicit product).
    """
    s = side.strip()
    i = len(s)
    while i > 0 and s[i - 1].isalpha():
        i -= 1
    run = s[i:]
    rest = s[:i].rstrip()
    if len(run) >= 3 and run.lower() not in MATH_MULTI_LETTER and _looks_like_math_core(rest):
        s = rest
    j = 0
    while j < len(s) and s[j].isalpha():
        j += 1
    run = s[:j]
    rest = s[j:].lstrip()
    if len(run) >= 3 and run.lower() not in MATH_MULTI_LETTER and _looks_like_math_core(rest):
        s = rest
    return s


def _alpha_run_is_viz(run: str, *, commands: frozenset[str], glueable: frozenset[str]) -> bool:
    low = run.lower()
    if low in commands:
        return True
    for cmd in glueable:
        if len(low) > len(cmd) and low.startswith(cmd) and _looks_like_math_core(low[len(cmd) :]):
            return True
    return False


def _text_has_command(
    text: str,
    commands: frozenset[str],
    glueable: frozenset[str] | None = None,
) -> bool:
    glue = glueable or frozenset()
    lower = text.lower()
    start = 0
    n = len(lower)
    while start < n:
        if lower[start].isalpha():
            end = _alpha_run_end(lower, start)
            if _alpha_run_is_viz(lower[start:end], commands=commands, glueable=glue):
                return True
            start = end
        else:
            start += 1
    return False


def has_viz_command(text: str) -> bool:
    """True when the user asked to graph/plot/draw — whole word or glued.

    Substring ``graph`` must not match ``paragraph``. Glued ``X=6graph``
    still counts: ``graph`` is its own letter-run, not five variables.
    ``graphx=4`` counts because ``graph`` is a prefix of the run and ``x``
    is a 1-letter variable.
    """
    lower = text.lower()
    if "visuali" in lower:
        return True
    return _text_has_command(text, VIZ_COMMANDS, _GLUEABLE_VIZ)


def mask_unknown_letter_runs(text: str) -> str:
    """Replace unknown 3+ letter runs with spaces so they are not split into
    per-letter variables (``6graph`` must not guess g,r,a,p,h)."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isalpha():
            j = _alpha_run_end(text, i)
            run = text[i:j]
            if len(run) >= 3 and run.lower() not in MATH_MULTI_LETTER:
                out.append(" ")
            else:
                out.append(run)
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def has_unknown_english_run(text: str) -> bool:
    """True when an alpha-run of length >= 3 is not a known math token."""
    i = 0
    n = len(text)
    while i < n:
        if text[i].isalpha():
            j = _alpha_run_end(text, i)
            if (j - i) >= 3 and text[i:j].lower() not in MATH_MULTI_LETTER:
                return True
            i = j
        else:
            i += 1
    return False


def looks_like_math_expr(text: str) -> bool:
    """Candidate is an expression, not leftover English with a digit in it."""
    stripped = text.strip()
    if not stripped:
        return False
    if has_unknown_english_run(stripped):
        return False
    return any(ch.isalnum() or ch in "+-*/^=()." for ch in stripped)


def split_glued_viz_runs(text: str) -> str:
    """``graphx=4`` → ``graph x=4`` so ``x`` is a standalone variable."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i].isalpha():
            end = _alpha_run_end(text, i)
            run = text[i:end]
            low = run.lower()
            split_at: int | None = None
            for cmd in _GLUEABLE_VIZ:
                if (
                    len(low) > len(cmd)
                    and low.startswith(cmd)
                    and _looks_like_math_core(low[len(cmd) :])
                ):
                    split_at = len(cmd)
                    break
            if split_at is not None:
                out.append(run[:split_at])
                out.append(" ")
                out.append(run[split_at:])
            else:
                out.append(run)
            i = end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)
