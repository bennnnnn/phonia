"""LaTeX and school shorthand rewritten as SymPy text.

``normalize_latex_to_sympy`` runs every rewrite, the Unicode glyphs of ``unicode_normalize.py``
included, so pasted, OCR and math-keyboard homework can pass the safe-character gate in
``parse.py``.
"""

from __future__ import annotations

import re

from app.modules.math.function_names import (
    HYPERBOLIC,
    TRIG,
    function_name_alternation,
)
from app.modules.math.solve.unicode_normalize import (
    _UNICODE_OP_SUBS,
    _UNICODE_VULGAR,
    _rewrite_unicode_higher_roots,
    _rewrite_unicode_script_runs,
    _rewrite_unicode_sqrts,
)
from app.services.symbolic_text import strip_inline_math_delimiters

# Shallow LaTeX → SymPy-ish text. Nested \frac needs repeated passes (capped).
_LATEX_FRAC_RE = re.compile(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
# A whole number written against a numeric fraction that stands alone is a mixed
# number: 2½ and 2\frac{1}{2} are two and a half, never 2 * 1/2. A power's or a
# decimal's digits (x^2½, 0.2½) start none, and a fraction with a factor after it
# (the keyboard's 44\frac{2}{2}4, 2½x) stays a product. The whole part is at most
# nine digits, so a long run of digits costs one bounded try per position.
_MIXED_GLYPH_RE = re.compile(
    r"(?<![\w.^}])(\d{1,9})\s*([" + "".join(glyph for glyph, _ in _UNICODE_VULGAR) + r"])(?![\w(])"
)
_MIXED_LATEX_RE = re.compile(
    r"(?<![\w.^}])(\d{1,9})\s*\\[dt]?frac\s*\{\s*(\d+)\s*\}\s*\{\s*(\d+)\s*\}(?![\w(])"
)
_VULGAR_VALUE = dict(_UNICODE_VULGAR)
_LATEX_ABS_LEFT_RIGHT_RE = re.compile(
    # The bars may sit on different lines: [^\x00] crosses newlines, as "." did under DOTALL.
    r"\\(?:left|lvert)\s*\|\s*(?:(\S(?:[^\x00]*?\S)??)\s*)??\\(?:right|rvert)\s*\|"
)
_LATEX_ABS_VERT_RE = re.compile(r"\\(?:lvert|rvert)\b")
_LATEX_SYMBOL_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\mathrm\{i\}"), "I"),
    (re.compile(r"\\infty"), "oo"),
    (re.compile(r"\\pi\b"), "pi"),
    (re.compile(r"\\cdot"), "*"),
    (re.compile(r"\\times"), "*"),
    (re.compile(r"\\div"), "/"),
    # Before \\left/\\right: \\le must not steal the prefix of \\left.
    (re.compile(r"\\leq"), "<="),
    (re.compile(r"\\geq"), ">="),
    (re.compile(r"\\le(?![a-zA-Z])"), "<="),
    (re.compile(r"\\ge(?![a-zA-Z])"), ">="),
    (re.compile(r"\\left"), ""),
    (re.compile(r"\\right"), ""),
]
_LATEX_FUNCTION_RE = re.compile(
    r"\\(sinh|cosh|tanh|coth|sech|csch|sin|cos|tan|sec|csc|cot|log|ln|sqrt|exp|min|max|Abs|abs)\b",
    re.IGNORECASE,
)
_TRIG_NAMES = f"({function_name_alternation(TRIG + HYPERBOLIC)})"
# ``\cot^{-1}(x)``, ``sinh^(-1) x`` and ``tan⁻¹ x`` name the inverse function,
# as on a school calculator. Read as a power they became ``1/cot(x)``, and the
# derivative of cot⁻¹(x) was certified as 1/cos²(x).
_INVERSE_POWER_RE = re.compile(
    rf"(?:\\|(?<![A-Za-z])){_TRIG_NAMES}\s*"
    r"(?:\^\s*\{\s*-\s*1\s*\}|\^\s*\(\s*-\s*1\s*\)|\^\s*-\s*1(?!\d)|\u207b\u00b9|\*\*\s*\(\s*-\s*1\s*\))"
)
# ``\arcsin`` … ``\arccsch`` are SymPy's ``asin`` … ``acsch``.
_ARC_NAME_RE = re.compile(rf"(?:\\|(?<![A-Za-z]))arc{_TRIG_NAMES}(?![A-Za-z])")


def _rewrite_inverse_functions(s: str) -> str:
    """``\\cot^{-1}`` / ``\\arccot`` → ``acot``; ``\\sinh^{-1}`` → ``asinh``."""
    # The trailing space keeps a glued argument apart: ``\\sin^{-1}x`` → ``asin x``.
    s = _ARC_NAME_RE.sub(lambda m: f"a{m.group(1).lower()} ", s)
    return _INVERSE_POWER_RE.sub(lambda m: f"a{m.group(1).lower()} ", s)


def _rewrite_bare_abs_bars(expr: str) -> str:
    """Rewrite paired ``|inner|`` → ``Abs(inner)``.

    Bare pipes are rejected by the expression allowlist; converting first lets
    homework like ``|x-2|<5`` reach SymPy without loosening ``_SAFE_EXPR_CHARS``.
    Unbalanced ``|`` is left as-is (still rejected later).
    """
    out: list[str] = []
    i = 0
    n = len(expr)
    while i < n:
        if expr[i] != "|":
            out.append(expr[i])
            i += 1
            continue
        depth = 0
        j = i + 1
        found = -1
        while j < n:
            ch = expr[j]
            if ch == "|" and depth == 0:
                found = j
                break
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth = max(0, depth - 1)
            j += 1
        if found == -1:
            out.append("|")
            i += 1
            continue
        inner = expr[i + 1 : found]
        if not inner.strip():
            out.append("|")
            i += 1
            continue
        out.append(f"Abs({inner})")
        i = found + 1
    return "".join(out)


def _read_brace_group(s: str, i: int) -> tuple[str, int] | None:
    if i >= len(s) or s[i] != "{":
        return None
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return None


def _rewrite_latex_sqrts(s: str) -> str:
    """`\\sqrt{x}` → sqrt(x); `\\sqrt[n]{x}` → (x)**(1/(n)). Linear scan."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        root_start = i + 1 if s[i] == "\\" else i
        if (
            s.startswith("sqrt", root_start)
            and (i == 0 or not s[i - 1].isalpha())
            and (root_start + 4 >= n or not s[root_start + 4].isalpha())
            and (s[i] == "\\" or s[root_start + 4 : root_start + 5] in {"[", "{"})
        ):
            j = root_start + 4
            degree: str | None = None
            if j < n and s[j] == "[":
                close = s.find("]", j + 1)
                if close == -1:
                    out.append(s[i])
                    i += 1
                    continue
                degree = s[j + 1 : close]
                j = close + 1
            while j < n and s[j] == " ":
                j += 1
            grp = _read_brace_group(s, j)
            if grp is not None:
                body, j = grp
            else:
                k = j
                while k < n and (s[k].isalnum() or s[k] == "."):
                    k += 1
                if k == j:
                    out.append(s[i])
                    i += 1
                    continue
                body = s[j:k]
                j = k
            if degree is not None and degree.strip():
                out.append(f"({body})**(1/({degree}))")
            else:
                out.append(f"sqrt({body})")
            i = j
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _implicit_mul_before_sqrt(s: str) -> str:
    """`6sqrt(4)` → `6*sqrt(4)` so juxtaposition is multiplication, not a 6th root."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s.startswith("sqrt(", i):
            prev = ""
            for ch in reversed(out):
                if not ch.isspace():
                    prev = ch
                    break
            if prev and (prev.isdigit() or prev in ")."):
                out.append("*")
        out.append(s[i])
        i += 1
    return "".join(out)


def _rewrite_latex_braced_scripts_once(s: str) -> str:
    """One pass: ``x^{6}`` → ``x^6``; ``^{x}^{2}`` → ``x^{2}``."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if s.startswith("^{", i):
            grp = _read_brace_group(s, i + 1)
            if grp is None:
                out.append(s[i])
                i += 1
                continue
            body, j = grp
            if s.startswith("^{", j):
                nxt = _read_brace_group(s, j + 1)
                if nxt is not None:
                    # ^{a}^{b} → a^{b} (math-keyboard x² chain).
                    out.append(body)
                    out.append("^{")
                    out.append(nxt[0])
                    out.append("}")
                    i = nxt[1]
                    continue
            if body and all(ch.isalnum() or ch in ".-" for ch in body):
                out.append("^")
                out.append(body)
            else:
                out.append("^(")
                out.append(body)
                out.append(")")
            i = j
            continue
        if s.startswith("_{", i):
            grp = _read_brace_group(s, i + 1)
            if grp is None:
                out.append(s[i])
                i += 1
                continue
            body, j = grp
            if body and all(ch.isalnum() or ch in ".-" for ch in body):
                out.append("_")
                out.append(body)
            else:
                out.append("_(")
                out.append(body)
                out.append(")")
            i = j
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _rewrite_latex_braced_scripts(s: str) -> str:
    """``x^{6}`` → ``x^6``; ``^{x}^{2}`` → ``x^2``. Linear scan, no regex."""
    for _ in range(8):
        nxt = _rewrite_latex_braced_scripts_once(s)
        if nxt == s:
            return s
        s = nxt
    return s


def _rewrite_log_bases_once(s: str) -> str:
    """``log_2(x)`` -> ``ln(x)/ln(2)`` without dropping the logarithm.

    The equation scanner intentionally rejects underscores. Previously it
    resumed at the base digit, turning ``log_2(x-1)`` into ``2(x-1)`` and
    certifying an entirely different equation. Numeric bases cover ordinary
    school notation while keeping the safe-expression grammar narrow.
    """
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if not s.startswith("log_", i) or (i > 0 and s[i - 1].isalpha()):
            out.append(s[i])
            i += 1
            continue
        base_start = i + 4
        base_end = base_start
        while base_end < n and (s[base_end].isdigit() or s[base_end] == "."):
            base_end += 1
        if base_end == base_start:
            out.append(s[i])
            i += 1
            continue
        paren = base_end
        while paren < n and s[paren].isspace():
            paren += 1
        if paren >= n or s[paren] != "(":
            out.append(s[i])
            i += 1
            continue
        depth = 1
        close = paren + 1
        while close < n and depth:
            if s[close] == "(":
                depth += 1
            elif s[close] == ")":
                depth -= 1
            close += 1
        if depth:
            out.append(s[i])
            i += 1
            continue
        base = s[base_start:base_end]
        body = s[paren + 1 : close - 1]
        out.append(f"(ln({body})/ln({base}))")
        i = close
    return "".join(out)


# ``log2(x)`` and ``log10(x)`` are written bases. Without this the digits end a
# letter run and implicit multiplication reads ``l*o*g*2*x``.
_GLUED_LOG_BASE_RE = re.compile(r"(?<![A-Za-z_\\])log(\d+)(?=\s*\()")

# ``sinx`` / ``sin2x`` / ``lnx`` are sin(x), sin(2x), ln(x). The argument is
# digits and one letter; anything longer (``sinx^2``, ``sinxy``) is left alone so
# the written-letter guard declines it instead of guessing.
_GLUED_FUNCTION_ARG_RE = re.compile(
    r"(?<![A-Za-z_\\])(sin|cos|tan|sec|csc|cot|ln)(\d*[a-z])(?![A-Za-z(_^\d])"
)


def _rewrite_glued_function_args(s: str) -> str:
    # ``\log_2`` keeps its backslash: ``_`` is a word character, so the LaTeX
    # function pattern's ``\b`` never matched it.
    s = s.replace("\\log_", "log_")
    s = _GLUED_LOG_BASE_RE.sub(r"log_\1", s)
    return _GLUED_FUNCTION_ARG_RE.sub(r"\1(\2)", s)


def _rewrite_log_bases(s: str) -> str:
    s = _rewrite_glued_function_args(s)
    for _ in range(8):
        nxt = _rewrite_log_bases_once(s)
        if nxt == s:
            return s
        s = nxt
    return s


def normalize_latex_to_sympy(expr: str) -> str:
    """Expand common LaTeX so pasted/OCR homework can pass the safe-char gate."""
    s = strip_inline_math_delimiters(expr)
    s = _rewrite_inverse_functions(s)
    for glyph, repl in _UNICODE_OP_SUBS:
        s = s.replace(glyph, repl)
    s = _MIXED_GLYPH_RE.sub(lambda m: f"({m.group(1)}+{_VULGAR_VALUE[m.group(2)]})", s)
    s = _MIXED_LATEX_RE.sub(r"(\1+(\2)/(\3))", s)
    for glyph, repl in _UNICODE_VULGAR:
        s = s.replace(glyph, repl)
    s = _rewrite_unicode_higher_roots(s)
    s = _rewrite_unicode_sqrts(s)
    s = _rewrite_unicode_script_runs(s)
    for _ in range(8):
        nxt = _rewrite_latex_sqrts(s)
        if nxt == s:
            break
        s = nxt
    s = _implicit_mul_before_sqrt(s)
    s = _LATEX_ABS_LEFT_RIGHT_RE.sub(r"Abs(\1)", s)
    s = _LATEX_ABS_VERT_RE.sub("", s)
    for pattern, replacement in _LATEX_SYMBOL_SUBS:
        s = pattern.sub(replacement, s)

    def _func_repl(match: re.Match[str]) -> str:
        name = match.group(1).lower()
        return "Abs" if name == "abs" else name

    s = _LATEX_FUNCTION_RE.sub(_func_repl, s)
    for _ in range(8):
        nxt = _LATEX_FRAC_RE.sub(r"((\1)/(\2))", s)
        if nxt == s:
            break
        s = nxt
    s = _rewrite_bare_abs_bars(s)
    s = _rewrite_latex_braced_scripts(s)
    s = _rewrite_log_bases(s)
    return s
