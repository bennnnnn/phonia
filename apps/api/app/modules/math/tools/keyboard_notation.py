"""The phone's math keyboard types LaTeX the extractors were not written for.

``$\\int_{0}^{1}x^{2}\\,dx$``, ``$\\frac{d}{dx}x^{3}$``, ``$\\binom{5}{2}$`` and
``$\\sin(30^{\\circ})$`` went to the model unverified, while "integrate x^2 from
0 to 1", "d/dx x^3", "C(5,2)" and "sin(30°)" were solved. Each ``$…$`` span is
rewritten into that plain notation, and the extractors get one more try.
"""

from __future__ import annotations

import re

_SPAN_RE = re.compile(r"\$([^$]+)\$")

_INT_BOUNDS_RE = re.compile(
    r"\\int_\{([^{}]*)\}\^\{([^{}]*)\}\s*(\S(?:[^\n]*?\S)??|[^\S\n](?=\n*\S))"
    r"\s*(?:\\,\s*)?d\{?([a-z])\}?\s*$"
)
_INT_RE = re.compile(
    r"\\int\s*(\S(?:[^\n]*?\S)??|[^\S\n](?=\n*\S))\s*(?:\\,\s*)?d\{?([a-z])\}?\s*$"
)
_SECOND_DERIVATIVE_RE = re.compile(
    r"^\\frac\{d\^\{?2\}?\}\{d\{?([a-z])\}?\^\{?2\}?\}\s*(\S.*|[^\S\n](?=\n?\Z))$"
)
_DERIVATIVE_RE = re.compile(r"^\\frac\{d\}\{d\{?([a-z])\}?\}\s*(\S.*|[^\S\n](?=\n?\Z))$")
_BINOM_RE = re.compile(r"\\binom\{([^{}]+)\}\{([^{}]+)\}")
_DEGREE_RE = re.compile(r"\^\{\\circ\}")
_RADIAN_RE = re.compile(r"(?:\b|\B(?<!\s))\s*\\mathrm\{rad\}")
_DERIVATIVE_FRAC_RE = re.compile(r"\\frac\{(?:d|\\partial)")
_GREEK_COMMAND_RE = re.compile(r"\\(var)?([a-z]+)(?![A-Za-z])")
_MOD_RE = re.compile(r"\\bmod\b")
_FLOOR_RE = re.compile(r"\\lfloor\s*(\S(?:[^\n]*?\S)??|[^\S\n](?=\n*\S))\s*\\rfloor")
_CEIL_RE = re.compile(r"\\lceil\s*(\S(?:[^\n]*?\S)??|[^\S\n](?=\n*\S))\s*\\rceil")
_PARTIAL_RE = re.compile(r"^\\frac\{\\partial\}\{\\partial ?([a-z])\}\s*(\S.*|[^\S\n](?=\n?\Z))$")
_PRODUCT_RE = re.compile(r"^\\prod_\{([a-z])=(-?\d+)\}\^\{(-?\d+)\}\s*(\S.*|[^\S\n](?=\n?\Z))$")
_DOT_PRODUCT_RE = re.compile(r"^\(([^()][^(),]*,[^()]+)\)\s*\\cdot\s*\(([^()][^(),]*,[^()]+)\)$")
# A product written out factor by factor; longer ones stay with the model.
_MAX_PRODUCT_FACTORS = 20


def _group_end(tex: str, start: int) -> int | None:
    """Index after the ``{…}`` group opening at ``start``."""
    if start >= len(tex) or tex[start] != "{":
        return None
    depth = 0
    for index in range(start, len(tex)):
        if tex[index] == "{":
            depth += 1
        elif tex[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _times_beside_fractions(tex: str) -> str:
    """``44\\frac{2}{2}4`` is 44 * 2/2 * 4: a number beside a fraction multiplies.

    Unread, it went to the model, which guessed ``44 + 2 / 2 + 4`` and answered 50.
    """
    out: list[str] = []
    index = 0
    while index < len(tex):
        if not tex.startswith("\\frac", index):
            out.append(tex[index])
            index += 1
            continue
        numerator_end = _group_end(tex, index + len("\\frac"))
        end = _group_end(tex, numerator_end) if numerator_end is not None else None
        if end is None:
            out.append(tex[index])
            index += 1
            continue
        before = "".join(out).rstrip()
        if before and (before[-1].isdigit() or before[-1] == ")"):
            out.append("\\cdot ")
        out.append(tex[index:end])
        after = tex[end:].lstrip()
        if (
            after
            and (after[0].isdigit() or after[0] == "(")
            and not _DERIVATIVE_FRAC_RE.match(tex, index)
        ):
            out.append("\\cdot ")
        index = end
    return "".join(out)


def _greek_names(tex: str) -> str:
    """The keypad's ``\\theta`` is the unknown ``theta``; ``\\pi`` stays a constant."""
    from app.modules.math.function_names import GREEK_NAMES

    def name(match: re.Match[str]) -> str:
        word = match.group(2)
        return word if word in GREEK_NAMES else match.group(0)

    return _GREEK_COMMAND_RE.sub(name, tex)


def _product_factors(match: re.Match[str]) -> str | None:
    """``\\prod_{n=1}^{5}n`` as ``(1)*(2)*(3)*(4)*(5)``, which arithmetic checks."""
    var, low, high, body = match.groups()
    start, end = int(low), int(high)
    if not 0 <= end - start < _MAX_PRODUCT_FACTORS:
        return None
    term = re.compile(rf"(?<![A-Za-z\\]){re.escape(var)}(?![A-Za-z])")

    def factor(value: int) -> str:
        def put(found: re.Match[str]) -> str:
            before = body[: found.start()].rstrip()
            joint = "\\cdot " if before and (before[-1].isdigit() or before[-1] in ")}") else ""
            return f"{joint}({value})"

        return f"({term.sub(put, body)})"

    return "\\cdot ".join(factor(value) for value in range(start, end + 1))


def _template_to_words(tex: str) -> str:
    tex = _greek_names(_times_beside_fractions(tex.strip()))
    tex = _MOD_RE.sub(" mod ", tex)
    tex = _FLOOR_RE.sub(r"floor(\1)", tex)
    tex = _CEIL_RE.sub(r"ceiling(\1)", tex)
    match = _PRODUCT_RE.match(tex)
    if match:
        tex = _product_factors(match) or tex
    match = _DOT_PRODUCT_RE.match(tex)
    if match:
        return f"dot product of ({match.group(1)}) and ({match.group(2)})"
    match = _PARTIAL_RE.match(tex)
    if match:
        var, body = match.groups()
        return f"differentiate {body} with respect to {var}"
    tex = _DEGREE_RE.sub("°", tex)
    tex = _RADIAN_RE.sub(" rad", tex)
    tex = _BINOM_RE.sub(r"C(\1,\2)", tex)
    match = _INT_BOUNDS_RE.search(tex)
    if match:
        lower, upper, body, _var = match.groups()
        return f"{tex[: match.start()]}integrate {body} from {lower} to {upper}"
    match = _INT_RE.search(tex)
    if match:
        body, var = match.groups()
        return f"{tex[: match.start()]}integrate {body} d{var}"
    match = _SECOND_DERIVATIVE_RE.match(tex)
    if match:
        return f"second derivative of {match.group(2)}"
    match = _DERIVATIVE_RE.match(tex)
    if match:
        var, body = match.groups()
        return f"d/d{var} {body}"
    return tex


def keyboard_bounds_read_first(text: str) -> bool:
    """A ``\\prod_{n=1}^{5}`` bound would be read as the equation n = 1."""
    return "\\prod_{" in text


# LaTeX pasted or typed without ``$``: the whole message is one span when it
# opens with one of these commands (``\frac{d}{dx} x^5``, ``\int_{0}^{1} x\,dx``).
_BARE_LATEX_START = re.compile(r"^\s*\\(?:frac|dfrac|int|lim|sum|prod|binom|sqrt)(?![A-Za-z])")


def keyboard_math_to_plain(text: str) -> str:
    """Each ``$…$`` span in the plain notation the extractors read."""
    from app.modules.math.solve.latex_normalize import normalize_latex_to_sympy

    if "$" not in text and _BARE_LATEX_START.match(text):
        return normalize_latex_to_sympy(_template_to_words(text)).strip()
    if "$" not in text or ("\\" not in text and "{" not in text):
        return text

    def plain(match: re.Match[str]) -> str:
        words = _template_to_words(match.group(1))
        return normalize_latex_to_sympy(words).strip()

    return _SPAN_RE.sub(plain, text)
