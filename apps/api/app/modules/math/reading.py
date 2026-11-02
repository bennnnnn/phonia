"""What the scanner read, in the notation a student writes.

The read-back is the student's check that the camera saw the problem. It is
the full transcription (Mathpix text, or the vision model's ``source_text``),
not an equation rebuilt from a parse: a rebuilt equation silently drops what
the parse did not keep, such as a printed ``x ∈ ℤ``. Tapping Solve sends this
text through the ordinary chat pipeline, which reads every symbol below.
"""

from __future__ import annotations

import re

_DELIMITERS = re.compile(r"\\[()\[\]]|\$+")
# "1." numbers a question; the "1." of 1.5 is a decimal, not a label.
_LABEL = re.compile(
    r"^\s*(?:(?:Q|question\s*)?\d+\s*(?:[):]|\.(?!\d))\s*)?(?:\(?[a-hivx]{1,3}\)\s*)?", re.I
)
_BRACED = r"\{([^{}]*)\}"
_FRAC = re.compile(r"\\[dt]?frac\s*" + _BRACED + r"\s*" + _BRACED)
_SQRT_INDEX = re.compile(r"\\sqrt\s*\[\s*([^\]]+?)\s*\]\s*" + _BRACED)
_SQRT = re.compile(r"\\sqrt\s*" + _BRACED)
_TEXT = re.compile(r"\\(?:text|mathrm|mathbf|mathit|operatorname)\s*" + _BRACED)
_BLACKBOARD = {"R": "ℝ", "Z": "ℤ", "N": "ℕ", "Q": "ℚ", "C": "ℂ"}
_MATHBB = re.compile(r"\\mathbb\s*\{([RZNQC])\}")
_SCRIPT = re.compile(r"([\^_])\s*" + _BRACED)
_SYMBOLS = (
    ("\\leq", "≤"),
    ("\\geq", "≥"),
    ("\\neq", "≠"),
    ("\\le", "≤"),
    ("\\ge", "≥"),
    ("\\ne", "≠"),
    ("\\cdot", "·"),
    ("\\times", "×"),
    ("\\div", "÷"),
    ("\\pm", "±"),
    ("\\mp", "∓"),
    ("\\infty", "∞"),
    ("\\notin", "∉"),
    ("\\in", "∈"),
    ("\\pi", "π"),
    ("\\theta", "θ"),
    ("\\alpha", "α"),
    ("\\beta", "β"),
    ("\\lambda", "λ"),
    ("\\degree", "°"),
    ("\\rightarrow", "→"),
    ("\\to", "→"),
    ("^\\circ", "°"),
    ("^{\\circ}", "°"),
    ("\\circ", "∘"),
    ("\\%", "%"),
    ("\\sum", "∑"),
    ("\\prod", "∏"),
    ("\\angle", "∠"),
    ("\\triangle", "△"),
    ("\\perp", "⊥"),
    ("\\parallel", "∥"),
    ("\\approx", "≈"),
    ("\\cdots", "…"),
    ("\\ldots", "…"),
    ("\\dots", "…"),
    ("\\cup", "∪"),
    ("\\cap", "∩"),
    ("\\Delta", "Δ"),
    ("\\delta", "δ"),
    ("\\gamma", "γ"),
    ("\\mu", "μ"),
    ("\\rho", "ρ"),
    ("\\sigma", "σ"),
    ("\\phi", "φ"),
    ("\\omega", "ω"),
)
# 0.\overline{3}: the bar over each repeating digit.
_OVERLINE = re.compile(r"\\overline\s*" + _BRACED)
# Any command still left is shown as its name, never as LaTeX.
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_SPACES = re.compile(r"\\(?:quad|qquad|[,;:! ])")
_SIZING = re.compile(r"\\(?:left|right)\s*[.]|\\(?:left|right|big|Big|bigg|Bigg)(?![A-Za-z])\s*")
_NAMED = re.compile(r"\\(arcsin|arccos|arctan|sin|cos|tan|sec|csc|cot|log|ln|exp|lim)(?![A-Za-z])")
_INTEGRAL = re.compile(r"\\int(?![A-Za-z])")
# Mathpix spaces a script from its function (``\log _{2}``); "log _2(x+1)" lost the log.
_SPACED_SCRIPT = re.compile(r"(?<=[A-Za-z0-9)])\s+(?=[\^_][\w(])")
# ``lim_(x → 0)`` is written ``lim x→0``, the way the limit reader reads it.
_LIMIT = re.compile(r"\blim_\(([^()]*)\)")
_ARRAY = re.compile(
    r"\\(?:begin|end)\s*\{(?:array|cases|aligned|align\*?|gathered)\}(?:\{[^{}]*\})?"
)
_IMPLICIT_TIMES = re.compile(r"(\d)\s*\*\s*(?=[A-Za-z(])")
_ABS_CALL = re.compile(r"\bAbs\(([^()]*)\)")
_SQRT_CALL = re.compile(r"\bsqrt\(")
_SIMPLE = re.compile(r"[A-Za-z0-9.]+")
# One fraction part that needs no brackets: ``3``, ``x``, ``x^2``, ``x_1``.
_SIMPLE_PART = re.compile(r"[A-Za-z0-9.]+(?:[\^_][A-Za-z0-9.]+)?")
# A whole number printed just before a numeric fraction: the 2 of 2½, not an exponent.
_WHOLE_BEFORE = re.compile(r"(?<![\w.^_])\d+\s*$")
_DIGITS = re.compile(r"\d+")


def _fraction(match: re.Match[str]) -> str:
    """``\\frac{1}{2}x`` is ``(1/2)x``; a fraction standing alone needs no brackets."""
    top, bottom = match.group(1).strip(), match.group(2).strip()
    head = match.string[: match.start()]
    if _DIGITS.fullmatch(top) and _DIGITS.fullmatch(bottom) and _WHOLE_BEFORE.search(head):
        # ``2 \frac{1}{2}`` is the mixed number 2 1/2, as a student types it.
        return f"{'' if head[-1:].isspace() else ' '}{top}/{bottom}"
    top = top if _SIMPLE_PART.fullmatch(top) else f"({top})"
    bottom = bottom if _SIMPLE_PART.fullmatch(bottom) else f"({bottom})"
    before = match.string[: match.start()].rstrip()[-1:]
    after = match.string[match.end() :].lstrip()[:1]
    # A power binds tighter than the bar: \frac{2}{3}^{2} is (2/3)^2.
    glued = (before and (before.isalnum() or before in ")^_")) or (
        after and (after.isalnum() or after in "(\\^")
    )
    return f"({top}/{bottom})" if glued else f"{top}/{bottom}"


def _root(match: re.Match[str]) -> str:
    index, body = match.group(1), match.group(2).strip()
    glyph = {"3": "∛", "4": "∜"}.get(index)
    return f"{glyph}({body})" if glyph else f"({body})^(1/{index})"


def _script(match: re.Match[str]) -> str:
    mark, body = match.group(1), match.group(2).strip()
    return f"{mark}{body}" if _SIMPLE.fullmatch(body) else f"{mark}({body})"


def student_reading(source: str) -> str:
    """``\\frac{1}{2}x+3=7`` → ``(1/2)x+3=7``; ``Abs(2x-1)`` → ``|2x-1|``."""
    text = _DELIMITERS.sub(" ", source)
    text = _ARRAY.sub("", text)
    text = text.replace("\\\\", "\n").replace("&", "")
    text = _SIZING.sub("", text)
    text = _TEXT.sub(r"\1", text)
    text = _MATHBB.sub(lambda m: _BLACKBOARD[m.group(1)], text)
    text = _OVERLINE.sub(lambda m: "".join(f"{c}\u0305" for c in m.group(1).strip()), text)
    # Symbols first: a degree sign is written as a superscript (``^{\circ}``).
    for latex, glyph in _SYMBOLS:
        text = re.sub(re.escape(latex) + r"(?![A-Za-z])", glyph, text)
    # Innermost groups first: the power in ``\frac{x^{2}-1}{x-1}`` is read before
    # the fraction around it can be.
    for _ in range(4):
        before = text
        text = _SCRIPT.sub(_script, text)
        text = _FRAC.sub(_fraction, text)
        text = _SQRT_INDEX.sub(_root, text)
        text = _SQRT.sub(lambda m: f"√({m.group(1).strip()})", text)
        if text == before:
            break
    text = _SPACES.sub(" ", text)
    text = _NAMED.sub(r"\1", text)
    text = _INTEGRAL.sub("∫", text)
    text = _SCRIPT.sub(_script, text)
    text = _SPACED_SCRIPT.sub("", text)
    text = _LIMIT.sub(lambda m: "lim " + re.sub(r"\s+", "", m.group(1)) + " ", text)
    text = text.replace("\\{", "").replace("\\}", "").replace("{", "").replace("}", "")
    # Mathpix spaces a unit with ~ (``\mathrm{~cm}``) and a percent sign from its number.
    text = re.sub(r"(?<=\d)\s+%", "%", text.replace("~", " "))
    text = _COMMAND.sub(r"\1", text)
    text = text.replace("**", "^")
    text = _IMPLICIT_TIMES.sub(r"\1", text)
    text = _ABS_CALL.sub(r"|\1|", text)
    text = _SQRT_CALL.sub("√(", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if lines:
        lines[0] = _LABEL.sub("", lines[0], count=1).strip()
    return "\n".join(line for line in lines if line)
