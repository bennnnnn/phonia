"""Unicode maths glyphs from OCR and homework as ASCII: operators, vulgar fractions,
superscript and subscript digits, and root signs."""

from __future__ import annotations

from app.services.glyphs import (
    OPERATOR_GLYPHS,
    SUBSCRIPT_DIGIT_GLYPHS,
    SUBSCRIPT_DIGITS,
    SUPERSCRIPT_DIGIT_GLYPHS,
    SUPERSCRIPT_DIGITS,
)

# OCR / homework unicode operators → ASCII before the allowlist runs.
# Do NOT widen `_SAFE_EXPR_CHARS`; map glyphs here instead.
# Escapes (not literals) keep RUF001 from flagging lookalike punctuation.
# The operators are the shared table (services/glyphs.py); π and ∞ are the solver's own.
# π is bracketed so a letter beside it stays a factor: "sin(πx)" was the one name "pix".
_UNICODE_OP_SUBS: tuple[tuple[str, str], ...] = (
    *OPERATOR_GLYPHS.items(),
    ("\u03c0", "(pi)"),  # π
    ("\u221e", "oo"),  # ∞
)

_UNICODE_VULGAR: tuple[tuple[str, str], ...] = (
    ("\u00bd", "(1)/(2)"),
    ("\u2153", "(1)/(3)"),
    ("\u2154", "(2)/(3)"),
    ("\u00bc", "(1)/(4)"),
    ("\u00be", "(3)/(4)"),
    ("\u2155", "(1)/(5)"),
    ("\u2156", "(2)/(5)"),
    ("\u2157", "(3)/(5)"),
    ("\u2158", "(4)/(5)"),
    ("\u2159", "(1)/(6)"),
    ("\u215a", "(5)/(6)"),
    ("\u215b", "(1)/(8)"),
    ("\u215c", "(3)/(8)"),
    ("\u215d", "(5)/(8)"),
    ("\u215e", "(7)/(8)"),
)

_SUP_GLYPHS = SUPERSCRIPT_DIGIT_GLYPHS
_SUB_GLYPHS = SUBSCRIPT_DIGIT_GLYPHS
_SUP_TABLE = SUPERSCRIPT_DIGITS
_SUB_TABLE = SUBSCRIPT_DIGITS


def _rewrite_unicode_script_runs(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in _SUP_GLYPHS:
            j = i + 1
            while j < n and s[j] in _SUP_GLYPHS:
                j += 1
            digits = s[i:j].translate(_SUP_TABLE)
            out.append(f"**{digits}" if len(digits) == 1 else f"**({digits})")
            i = j
            continue
        if ch in _SUB_GLYPHS:
            j = i + 1
            while j < n and s[j] in _SUB_GLYPHS:
                j += 1
            digits = s[i:j].translate(_SUB_TABLE)
            out.append(f"_{digits}")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_UNICODE_HIGHER_ROOTS = {"\u221b": "3", "\u221c": "4"}  # cube and fourth root signs


def _rewrite_unicode_higher_roots(s: str) -> str:
    """``∛(x)`` / ``∛8`` → ``((x))**(1/3)``; a sign with nothing after it is left alone."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        index = _UNICODE_HIGHER_ROOTS.get(s[i])
        if index is None:
            out.append(s[i])
            i += 1
            continue
        j = i + 1
        while j < n and s[j] in " \t":
            j += 1
        if j < n and s[j] == "(":
            depth = 1
            k = j + 1
            while k < n and depth:
                depth += {"(": 1, ")": -1}.get(s[k], 0)
                k += 1
            if depth:
                out.append(s[i])
                i += 1
                continue
            body = s[j + 1 : k - 1]
        else:
            k = j
            while k < n and (s[k].isalnum() or s[k] == "."):
                k += 1
            body = s[j:k]
        if not body.strip():
            out.append(s[i])
            i += 1
            continue
        out.append(f"(({body})**(1/{index}))")
        i = k
    return "".join(out)


def _rewrite_unicode_sqrts(s: str) -> str:
    """``√9`` / ``√x`` / ``√(x+1)`` → ``sqrt(...)``. Linear scan, leftover ``√`` → ``sqrt``."""
    out: list[str] = []
    i = 0
    n = len(s)
    root = "\u221a"
    while i < n:
        if s[i] != root:
            out.append(s[i])
            i += 1
            continue
        i += 1
        while i < n and s[i] in " \t":
            i += 1
        if i >= n:
            out.append("sqrt")
            break
        if s[i] == "(":
            depth = 1
            j = i + 1
            while j < n and depth:
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                out.append("sqrt(")
                out.append(s[i + 1 : j - 1])
                out.append(")")
                i = j
                continue
            out.append("sqrt")
            continue
        if s[i].isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            if j < n and s[j] == "." and j + 1 < n and s[j + 1].isdigit():
                j += 1
                while j < n and s[j].isdigit():
                    j += 1
            out.append("sqrt(")
            out.append(s[i:j])
            out.append(")")
            i = j
            continue
        if s[i].isalpha():
            out.append("sqrt(")
            out.append(s[i])
            out.append(")")
            i += 1
            continue
        out.append("sqrt")
    return "".join(out)
