"""Whether a plain line is a chain to lay out, and how a laid-out line ends: its note and its
hard break (twin: calculationLayoutTail.ts)."""

from __future__ import annotations

import re


def finish_inline(parts: list[str], tail: str) -> str:
    """The laid-out rows of a line, then whatever followed the maths.

    "$h = …, k = …$ — Vertex of a parabola": the note names the first row, not a
    line of its own. The line's hard break ("…$  ") still ends it, or the next
    line runs on.
    """
    note = tail.strip()
    if parts and note.startswith("\u2014 ") and "\n" in parts[-1]:
        first, _, rest = parts[-1].partition("\n")
        parts[-1] = f"{first.rstrip()} {note}  \n{rest}"
    elif parts and _UNIT_TAIL.fullmatch(note):
        # "$d = 120 + 60 = 180$ km": the unit stays with the last row's value.
        parts[-1] = f"{parts[-1].rstrip()} {note}"
    elif note:
        parts.append(tail.lstrip() if parts else tail)
    return keep_hard_break(tail, "\n".join(parts))


def continues_sentence(after: str) -> bool:
    """Prose follows a maths span on its line: the span is part of a sentence.

    "has $\\Delta = 9 - 8 = 1$, giving …" or "$v = 100/20 = 5$ m/s, so it is slow" split
    into rows broke the sentence into fragments, a unit or a clause alone on a line. A
    chain that ends its line ("**Step 1:** $x = 2 + 3 = 5$"), or whose line ends in a unit
    ("$d = 120 + 60 = 180$ km") or a note ("$h = …$ — Vertex of a parabola"), is a worked
    step and still splits.
    """
    rest = after.lstrip(".,;:!?").strip()
    return bool(rest) and not rest.startswith("\u2014 ") and not _UNIT_TAIL.fullmatch(rest)


# A unit after a value ("km/h", "m/s²", "N.", "kg·m/s"): letter runs of three or fewer, so
# "here" or "only" read as words.
_UNIT_TAIL = re.compile(
    r"[A-Za-zµμΩ°]{1,3}(?:[/·^][A-Za-zµμΩ°0-9²³⁻¹]{1,3}|[0-9²³⁻¹]{1,2}){0,3}[.,;:!?]*"
)


def keep_hard_break(original: str, laid: str) -> str:
    """``laid`` ends with ``original``'s hard break, if it had one."""
    return f"{laid.rstrip()}  " if original.endswith("  ") else laid


# Subscript digits and charges are chemistry notation (C₃H₈, Fe²⁺): typeset as maths,
# its formulas and units went italic ("n(C₃H₈) = 0.227 mol").
_CHEMISTRY_MARKS = frozenset("₀₁₂₃₄₅₆₇₈₉⁺⁻")


def reads_as_prose(text: str) -> bool:
    """A plain line that stays text: a word of four letters or more, or chemistry notation."""
    run = 0
    for char in text:
        if char in _CHEMISTRY_MARKS:
            return True
        run = run + 1 if char.isalpha() else 0
        if run >= 4:
            return True
    return False


def converts_units(segments: list[str]) -> bool:
    """``v = 100 km/h * 1000/3600 = 27.8 m/s``: a symbol's value in two units, one row.

    Every value after the symbol carries its unit. A chain that works a value out
    (``a = (27.8 - 0)/8 = 3.47 m/s²``) has bare numbers until its end, and splits;
    so does one through another symbol (``F = ma = …``), or from a value rather than a
    symbol (``1 km = 1000 m = 100000 cm``).
    """
    return (
        len(segments) > 2
        and not segments[0].strip()[:1].isdigit()
        and all(_has_unit(part) for part in segments[1:])
    )


# How a value's unit is written: \mathrm{km/h}, \text{ m}, \Omega, 30^\circ.
_UNIT_MARKS = (r"\mathrm{", r"\text{", r"\Omega", r"^\circ", "°")


def _has_unit(segment: str) -> bool:
    return any(mark in segment for mark in _UNIT_MARKS)
