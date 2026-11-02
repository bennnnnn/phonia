"""Where a LaTeX ``{…}`` group ends: one brace matcher for every reader of a reply's or a
keyboard's TeX (the times sign, physics notation, keyboard fractions)."""

from __future__ import annotations


def group_end(latex: str, brace: int) -> int:
    """Past the ``{…}`` group that opens at ``brace``; the text's end when it never closes."""
    return closed_group_end(latex, brace) or len(latex)


def closed_group_end(latex: str, brace: int) -> int | None:
    """Past the ``{…}`` group that opens at ``brace``; None when no group opens there or
    it never closes."""
    if brace >= len(latex) or latex[brace] != "{":
        return None
    depth = 0
    for index in range(brace, len(latex)):
        if latex[index] == "{":
            depth += 1
        elif latex[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None
