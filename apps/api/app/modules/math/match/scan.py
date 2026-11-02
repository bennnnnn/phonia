"""Maths text scans: the prepare pass, number folding, command words and equation gates.

CodeQL-safe, mostly linear. Letter runs are read in ``letter_runs.py`` and geometry
dimensions in ``dimensions.py``.
"""

from __future__ import annotations

import re

from app.modules.math.match.letter_runs import (
    _GLUEABLE_VIZ,
    _text_has_command,
    has_unknown_english_run,
    looks_like_math_expr,
)
from app.services.number_text import fold_scientific
from app.services.symbolic_text import (
    normalize_symbolic_request,
    strip_inline_math_delimiters,
)
from app.services.text_match import has_equation, word_index

_MAX = 1000
# Math keyboard / Unicode units: m/s² and m/s^{2} must match m/s^2.
_BARE_COORD = re.compile(r"^\((?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?)\)$")
_CALC_OP = re.compile(
    r"\b(simplify|differentiate|derivative|integrate|integral|factor|expand|dsolve|"
    r"factori[sz]e|deriv[ai]t[ai]ve|derivatve|diriv[ai]tive|intergrate|intergral)\b",
    re.IGNORECASE,
)
# British spellings and the misspellings students type, as the verb they mean.
CALC_OP_SPELLINGS = {
    "factorise": "factor",
    "factorize": "factor",
    "derivitive": "derivative",
    "derivitave": "derivative",
    "derivatave": "derivative",
    "derivatve": "derivative",
    "dirivative": "derivative",
    "dirivitive": "derivative",
    "intergrate": "integrate",
    "intergral": "integral",
}


def _leibniz_op_end(text: str, start: int) -> int | None:
    """Exclusive end of ``d/dx`` or ``dy/dx`` starting at ``start``."""
    n = len(text)
    if start >= n or text[start] not in "dD":
        return None
    i = start + 1
    if i < n and text[i] == "/":
        if i + 1 < n and text[i + 1] in "dD":
            i += 2
            if i < n and text[i].isalpha() and (i + 1 == n or not text[i + 1].isalpha()):
                return i + 1
        return None
    if i < n and text[i].isalpha() and (i + 1 == n or not text[i + 1].isalpha()):
        i += 1
        if i + 1 < n and text[i] == "/" and text[i + 1] in "dD":
            i += 2
            if i < n and text[i].isalpha() and (i + 1 == n or not text[i + 1].isalpha()):
                return i + 1
    return None


def ddx_cue_at(text: str) -> int | None:
    """Index of a ``d/dx`` / ``dy/dx`` derivative cue (not ``and/or``)."""
    lower = text.lower()
    n = len(lower)
    start = 0
    while start < n:
        idx = lower.find("d", start)
        if idx == -1:
            return None
        prev_ok = idx == 0 or not lower[idx - 1].isalpha()
        if prev_ok and _leibniz_op_end(lower, idx) is not None:
            return idx
        start = idx + 1
    return None


def ddx_expr_after(text: str) -> str | None:
    idx = ddx_cue_at(text)
    if idx is None:
        return None
    end = _leibniz_op_end(text, idx)
    if end is None:
        return None
    return text[end:]


def strip_inline_math_delims(text: str) -> str:
    """Composer/math keyboard wraps numbers in ``$...$`` / ``\\(...\\)``.

    ``X=$6$graph`` must be seen as ``X=6graph`` — a ``$`` after ``x=`` used
    to hide the 6 from the vertical-line matcher, so we solved the equation
    in words and never attached the plot.
    """
    return strip_inline_math_delimiters(text)


def prepare(text: str) -> str | None:
    # ``1.8 x 10^-5`` is the product it means, never an unknown x, and folding
    # it before superscripts become carets reads ``1.8·10⁻⁵`` too.
    cleaned = normalize_symbolic_request(fold_scientific(text, style="product"))
    if cleaned is None:
        return None
    return fold_digit_groups(fix_leading_solve_typo(cleaned))


# The verbs a closed request may open with: "find the area of …", "what's the mean of …".
_COMMAND_LEADS = ("find ", "calculate ", "compute ", "determine ", "what is ", "what's ")


def strip_command_lead(request: str) -> str:
    """``find the area of …`` → ``area of …``: one command verb, then one ``the``."""
    for prefix in _COMMAND_LEADS:
        if request.startswith(prefix):
            request = request[len(prefix) :]
            break
    if request.startswith("the "):
        request = request[4:]
    return request


# A polite opener before the command: "please find …", "can you compute …".
_POLITE_LEADS = ("please ", "can you ", "could you ")


def closed_request_text(text: str) -> str | None:
    """A one-line closed request lowercased, its polite opener and command verb off.

    None past 1,000 characters: no closed request is that long.
    """
    if len(text) > 1000:
        return None
    request = " ".join(text.lower().split()).rstrip(".?")
    for prefix in _POLITE_LEADS:
        if request.startswith(prefix):
            request = request[len(prefix) :]
            break
    return strip_command_lead(request)


# "slove 4x - 8 = 12": the command a student meant, as the first word only.
_SOLVE_TYPO = re.compile(r"^(?:slove|sovle|solv|slov)(?=\s)", re.IGNORECASE)


def fix_leading_solve_typo(text: str) -> str:
    """A misspelled leading "solve" reads as the verb, not as prose before the equation."""
    return _SOLVE_TYPO.sub("solve", text)


# Clauses of a typed system: "x+y=5, x-y=1", "3x+2y=12 and x-y=1".
_SYSTEM_CLAUSE_SPLIT = re.compile(r"(?:[,;]|\band\b)\s*", re.IGNORECASE)
# An equation with a term in it, not only "x = 1".
_EQUATION_TERM = re.compile(r"[+\-*/^]|\d\s*[a-zA-Z]")
_MAX_BARE_SYSTEM = 4


def bare_equation_system(text: str) -> bool:
    """The whole message is two to four equations: ``x+y+z=6, 2x-y+z=3, x+2y-z=2``.

    Each clause is one equation of maths on both sides, and at least one has
    a term, so a list of assignments (``a=1, b=2``) is not a system.
    """
    if len(text) > _MAX or "=" not in text:
        return False
    clauses = [part for part in _SYSTEM_CLAUSE_SPLIT.split(text.strip().rstrip(".?!")) if part]
    if not 2 <= len(clauses) <= _MAX_BARE_SYSTEM:
        return False
    with_term = False
    for clause in clauses:
        if clause.count("=") != 1:
            return False
        lhs, rhs = clause.split("=")
        if not (looks_like_math_expr(lhs) and looks_like_math_expr(rhs)):
            return False
        with_term = with_term or _EQUATION_TERM.search(clause) is not None
    return with_term and _STANDALONE_VAR_RE.search(text) is not None


# ``1,200`` and ``1,234,567.5``: one number written in groups of three.
_DIGIT_GROUPS = re.compile(r"(?<![\w.,])(\d{1,3})((?:,\d{3})+)(?![\d]|,\d)")
_BRACKET_BEFORE = re.compile(r"[(\[<{]\s*$")
_BRACKET_AFTER = re.compile(r"^\s*[)\]>}]")
_BARE_COMMA = re.compile(r"\d,\d")


def fold_digit_groups(text: str) -> str:
    """``7.5% of 1,200`` is 7.5% of 1200, not of 1 with ``,200`` left over.

    A list typed without spaces (``2,4,4,5``) keeps its commas, and so does
    any number in that message. A run that reads both ways (``100,200,300``)
    is left alone, and so are pairs and matrices in brackets (``(1,200)``),
    so an extractor that cannot read it declines.
    """
    if "," not in text:
        return text
    found = list(_DIGIT_GROUPS.finditer(text))
    if not found:
        return text
    rest = _DIGIT_GROUPS.sub(" ", text)
    if _BARE_COMMA.search(rest):
        return text

    def fold(match: re.Match[str]) -> str:
        lead, groups = match.group(1), match.group(2)
        if len(lead) == 3 and groups.count(",") >= 2:
            return match.group(0)
        before, after = text[: match.start()], text[match.end() :]
        if _BRACKET_BEFORE.search(before) or _BRACKET_AFTER.match(after):
            return match.group(0)
        return lead + groups.replace(",", "")

    return _DIGIT_GROUPS.sub(fold, text)


# Whole words only. ``solve`` inside ``resolved`` and ``factor`` inside
# ``factorial`` are not commands. Inflections are listed themselves so
# ``solved`` still matches and a longer word does not.
_MATH_COMMAND_WORDS = (
    "solve",
    "solved",
    "simplify",
    "simplified",
    "factor",
    "factored",
    "factoring",
    "expand",
    "expanded",
    "expanding",
    "differentiate",
    "differentiated",
    "derivative",
    "derivatives",
    "integrate",
    "integrated",
    "integral",
    "integrals",
    "equation",
    "equations",
    "algebra",
    "quadratic",
    "quadratics",
    "polynomial",
    "polynomials",
    "diagonal",
    "diagonals",
    "rectangle",
    "rectangles",
    "triangle",
    "triangles",
    "circle",
    "circles",
    "geometry",
    "radius",
    "diameter",
    "diameters",
    "circumference",
    "circumferences",
    "function",
    "functions",
    "sqrt",
)
_MATH_COMMAND_PHRASES = ("find the angle", "square root")


def _word_starts(lower: str, stem: str) -> bool:
    """True when ``stem`` begins a word, so ``pythagorean`` still matches."""
    start = 0
    while True:
        idx = lower.find(stem, start)
        if idx == -1:
            return False
        if idx == 0 or not lower[idx - 1].isalpha():
            return True
        start = idx + 1


def has_math_keyword(lower: str) -> bool:
    compact = lower.replace(" ", "")
    # Bare ``y=x^2`` is a math ask. ``tell me about y=x^2`` is prose that
    # happens to mention a formula — do not pull it into SymPy as a solve.
    if "y=" in compact and not has_unknown_english_run(lower):
        return True
    # ``graph``/``plot`` are whole tokens (or glued onto a variable), not
    # substrings — ``paragraph`` must not look like a graph ask. ``show`` /
    # ``draw`` stay out of this gate so "show me the weather" is not math.
    if _text_has_command(lower, _GLUEABLE_VIZ, _GLUEABLE_VIZ):
        return True
    if any(word_index(lower, word) != -1 for word in _MATH_COMMAND_WORDS):
        return True
    if any(phrase in lower for phrase in _MATH_COMMAND_PHRASES):
        return True
    return _word_starts(lower, "pythagor")


# A standalone single-letter variable (not part of a longer word) is a strong
# algebraic signal. "2x+3=7" → 'x' qualifies; "the meeting = 3pm" has no such
# letter (every letter sits inside a multi-letter word), so prose with an '='
# is not pulled into SymPy.
_STANDALONE_VAR_RE = re.compile(r"(?<![a-zA-Z])[a-zA-Z](?![a-zA-Z])")
_ATTACHMENT_MARKER_HEADS = ("[File:", "[Image:", "[File attached:", "[File (")


def _without_attachment_markers(text: str) -> str:
    """Drop ``[File: …]`` / ``[Image: …]`` labels. Linear scan, no regex."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if any(text.startswith(head, i) for head in _ATTACHMENT_MARKER_HEADS):
            end = text.find("]", i)
            if end != -1:
                i = end + 1
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def has_algebraic_equation(text: str) -> bool:
    """An equation that contains a standalone single-letter variable.

    Used to trigger SymPy for bare ``2x+3=7`` (no "solve"/"find" keyword)
    without dragging in prose that happens to contain an ``=``.

    A ``[File:]`` / ``[Image:]`` label is removed first. The equation itself
    has to start a clause, so ``x^2 = 0`` followed by "Show your work" still
    qualifies and ``the answer key says x=5`` does not.
    """
    if not has_equation(text):
        return False
    if not _STANDALONE_VAR_RE.search(text):
        return False
    from app.modules.math.solve.extract_eq import free_standing_equation

    body = _without_attachment_markers(text)
    found = free_standing_equation(body)
    if found is None:
        return False
    _prefix, _problem, suffix = found
    # A file label may be followed by "Show your work". Anywhere else, a
    # trailing clause (``where x is positive``) is not a bare equation.
    if body != text:
        return True
    return not suffix.strip(" .!?")


def inequality_signal(cleaned: str) -> bool:
    """A clear algebraic inequality: a symbolic comparator (``<``, ``>``, ``≤``,
    ``≥``, ``<=``, ``>=``) with both a variable letter and a number nearby —
    ``"x > 4"``, ``"2x < 10"``, ``"1 < x < 5"``.

    Rejects prose (``"less than 5 minutes"`` — word, no symbol) and trivial
    comparisons (``"5 < 10"`` — no variable letter). The window is small (12
    chars each side) so a stray ``>`` in unrelated prose without a nearby digit
    + letter doesn't trip.
    """
    for m in re.finditer(r"<=|>=|≤|≥|<|>", cleaned):
        start = max(0, m.start() - 12)
        end = min(len(cleaned), m.end() + 12)
        window = cleaned[start:end]
        if any(c.isalpha() for c in window) and any(c.isdigit() for c in window):
            return True
    return False
