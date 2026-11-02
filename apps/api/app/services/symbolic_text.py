"""Subject-neutral normalization for symbolic math and physics requests."""

from __future__ import annotations

from app.services.glyphs import SUPERSCRIPT_DIGIT_GLYPHS, SUPERSCRIPT_SIGNED
from app.services.text_normalize import collapse_ws

_MAX_SYMBOLIC_REQUEST = 1000
# A physics problem and its givens fit in a few hundred characters. Four
# thousand leaves room for a worksheet problem pasted whole, and keeps the
# extractor chain, which scans the text dozens of times, inside a turn's budget.
_MAX_PHYSICS_REQUEST = 4_000
# The longest message a subject gate reads at all. Past this it is a document,
# and only its head and tail are worth looking at.
_MAX_SUBJECT_TEXT = 20_000
_SUP_GLYPHS = SUPERSCRIPT_DIGIT_GLYPHS
_SUP_SIGNS = "⁻⁺"
_SUP_TABLE = SUPERSCRIPT_SIGNED


def strip_inline_math_delimiters(text: str) -> str:
    """Remove composer delimiters without changing the enclosed expression."""
    return (
        text.replace("$$", "")
        .replace("$", "")
        .replace("\\(", "")
        .replace("\\)", "")
        .replace("\\[", "")
        .replace("\\]", "")
    )


# Marks the math keypad types as LaTeX: ``20\\%`` is a percent, ``f^{\\prime}`` a prime.
# Longest first, so a double prime is not read as two singles with a brace left over.
_LATEX_MARKS = (
    ("^{\\prime\\prime}", "''"),
    ("^{\\prime}", "'"),
    ("^\\prime", "'"),
    ("\\prime", "'"),
    ("\\%", "%"),
)


def fold_latex_marks(text: str) -> str:
    """``20\\%`` → ``20%`` and ``f^{\\prime}(x)`` → ``f'(x)``, as a student would type them."""
    if "\\" not in text:
        return text
    for latex, plain in _LATEX_MARKS:
        text = text.replace(latex, plain)
    return text


def fold_numeric_superscripts(text: str) -> str:
    """Normalize Unicode and braced numeric powers to caret notation."""
    if "^{" not in text and not any(glyph in text for glyph in _SUP_GLYPHS):
        return text
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        # A sign opens the power it belongs to: "s⁻²" is "s^-2", not "s⁻^2".
        signed = char in _SUP_SIGNS and index + 1 < len(text) and text[index + 1] in _SUP_GLYPHS
        if char in _SUP_GLYPHS or signed:
            end = index + 1
            while end < len(text) and text[end] in _SUP_GLYPHS:
                end += 1
            out.append("^" + text[index:end].translate(_SUP_TABLE))
            index = end
            continue
        if char == "^" and index + 1 < len(text) and text[index + 1] == "{":
            close = text.find("}", index + 2)
            if close != -1:
                inner = text[index + 2 : close]
                if inner.isdigit() and (not out or out[-1] != "}"):
                    out.append("^" + inner)
                    index = close + 1
                    continue
        out.append(char)
        index += 1
    return "".join(out)


def collapse_repeated_si_unit_powers(text: str) -> str:
    """Collapse repeated keyboard inserts such as ``m/s^2^2.^2``."""
    if "m/s^" not in text:
        return text
    out: list[str] = []
    index = 0
    while index < len(text):
        if index + 4 <= len(text) and text[index : index + 4] == "m/s^":
            end = index + 4
            if end < len(text) and text[end].isdigit():
                digit_end = end + 1
                while digit_end < len(text) and text[digit_end].isdigit():
                    digit_end += 1
                out.append(text[index:digit_end])
                index = digit_end
                while index < len(text):
                    repeat = index + (1 if text[index : index + 1] == "." else 0)
                    if (
                        repeat + 1 < len(text)
                        and text[repeat] == "^"
                        and text[repeat + 1].isdigit()
                    ):
                        repeat += 2
                        while repeat < len(text) and text[repeat].isdigit():
                            repeat += 1
                        index = repeat
                        continue
                    break
                continue
        out.append(text[index])
        index += 1
    return "".join(out)


def normalize_symbolic_request(text: str, *, limit: int = _MAX_SYMBOLIC_REQUEST) -> str | None:
    """Normalize bounded user text without applying subject semantics.

    Math keeps the default 1,000-character cap. Physics passes a higher limit,
    and no limit can exceed ``_MAX_SUBJECT_TEXT``.
    """
    ceiling = min(max(limit, 1), _MAX_SUBJECT_TEXT)
    cleaned = collapse_ws(fold_latex_marks(strip_inline_math_delimiters(text)))
    if len(cleaned) > ceiling:
        return None
    return collapse_repeated_si_unit_powers(fold_numeric_superscripts(cleaned))
