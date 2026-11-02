# ruff: noqa: RUF001, RUF002 -- the point of this module is the symbols OCR spells in LaTeX.
"""Read a photographed physics problem back as the text a student would type.

The student confirms the reading in the scanner, then the chat solves that
text like a typed question: verified, with the five-part reply. A vision
model often answers in LaTeX (``2 \\times 10^{-6}\\,\\mathrm{C}``,
``30^{\\circ}``), which the student should not have to read or edit, so the
reading is turned into plain text first (``2 × 10^-6 C``, ``30°``).
"""

from __future__ import annotations

import re

from app.core.config import Settings
from app.services.scan_text import read_problem_text

PHYSICS_READ_PROMPT = (
    "Read the physics problem written in this image. "
    "Return only that problem as plain text, with every number and its unit exactly as "
    "written, and powers of ten as 2 × 10^-6. "
    "If a diagram labels a value the problem uses, add it as it is labelled. "
    "Do not solve it. Do not describe the diagram. "
    "If there is no written problem, return nothing."
)

_MOCK_READING = "A ball is dropped from 20 m. How long does it take to hit the ground?"

# Math delimiters around an expression: \( \), \[ \], $$ and $.
_DELIMITERS = re.compile(r"\\[()\[\]]|\$\$?")
# \mathrm{m/s}, \text{ kg}: the text inside, as written.
_TEXT_RUN = re.compile(r"\\(?:mathrm|text|textrm|operatorname|mathit|mathbf)\s*\{([^{}]*)\}")
_DEGREE = re.compile(r"\^\s*(?:\{\s*\\circ\s*\}|\\circ)|\\circ|\\degree")
_FRACTION = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_EXPONENT = re.compile(r"\^\s*\{\s*([-+−]?\s*[\w.]+)\s*\}")
_SUBSCRIPT = re.compile(r"_\s*\{\s*(\w+)\s*\}")
# µ is the micro prefix before a unit; anywhere else it is a coefficient.
# ΔT is one symbol: LaTeX writes it with a space that a student does not.
_DELTA = re.compile(r"\\Delta\s*")
_MICRO = re.compile(r"\\mu\s*(?=(?:[CFmsATHgVWJ]|Hz|Pa|mol)\b)")
_SPACING = re.compile(r"\\[,;:!> ]|~")
_LEFT_RIGHT = re.compile(r"\\(?:left|right)\s*(?=[()\[\]|.])")
_BRACES = re.compile(r"\{([^{}\\]*)\}")
_SPACES = re.compile(r"[ \t]+")

_SYMBOLS = {
    r"\times": "×",
    r"\cdot": "·",
    r"\%": "%",
    r"\Omega": "Ω",
    r"\omega": "ω",
    r"\mu": "μ",
    r"\lambda": "λ",
    r"\theta": "θ",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\varepsilon": "ε",
    r"\epsilon": "ε",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\varphi": "φ",
    r"\phi": "φ",
    r"\eta": "η",
    r"\approx": "≈",
    r"\leq": "≤",
    r"\geq": "≥",
}
# Longest first, so \varepsilon is not read as \var + epsilon.
_SYMBOL = re.compile(
    "|".join(re.escape(name) for name in sorted(_SYMBOLS, key=len, reverse=True)) + r"(?![A-Za-z])"
)


def readable_physics(text: str) -> str:
    """OCR LaTeX as plain problem text. Lines are kept; nothing is solved."""
    text = _DELIMITERS.sub("", text)
    # Inner groups first, so a text run (\mathrm{m/s^{2}}) holds no braces.
    text = _DEGREE.sub("°", text)
    text = _EXPONENT.sub(lambda match: "^" + re.sub(r"\s+", "", match.group(1)), text)
    text = _SUBSCRIPT.sub(r"_\1", text)
    text = _TEXT_RUN.sub(r"\1", text)
    text = _FRACTION.sub(r"\1/\2", text)
    text = _DELTA.sub("Δ", text)
    text = _MICRO.sub("µ", text)
    text = _SPACING.sub(" ", text)
    text = _LEFT_RIGHT.sub("", text)
    text = _SYMBOL.sub(lambda match: _SYMBOLS[match.group(0)], text)
    # Braces left around plain text ({m}) are grouping only. Two passes
    # cover the nesting a problem statement uses.
    for _ in range(2):
        text = _BRACES.sub(r"\1", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


async def read_physics_problem(
    settings: Settings,
    *,
    content_type: str,
    data: bytes,
    timeout_seconds: float | None = None,
) -> str:
    """The written problem as plain text, or empty when the page cannot be read."""
    reading = await read_problem_text(
        settings,
        prompt=PHYSICS_READ_PROMPT,
        content_type=content_type,
        data=data,
        mock_reading=_MOCK_READING,
        timeout_seconds=timeout_seconds,
    )
    return readable_physics(reading)
