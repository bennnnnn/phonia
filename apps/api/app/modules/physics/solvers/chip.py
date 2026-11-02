"""How a solver's quantities read as the answer: plain text and LaTeX.

The plain spelling is for guards, logs and readers without math; the LaTeX one
is the answer card. Both come from the same quantities through
``physics.display``, so the two never disagree on a figure.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.modules.physics.display import latex_quantity, plain_numbers_in, plain_quantity

if TYPE_CHECKING:
    from app.modules.physics.solvers.results import QuantityResult

_LATEX_TEXT_SPECIALS = str.maketrans({"%": r"\%", "#": r"\#", "&": r"\&", "_": r"\_", "$": r"\$"})


def render_quantity(item: QuantityResult) -> str:
    """Plain text, as ``physics.display`` spells it: ``39.6 m/s (gauge)``."""
    base = plain_quantity(item.value, item.unit)
    if item.detail is None:
        return base
    detail = plain_numbers_in(item.detail)
    if item.detail_style == "suffix":
        return f"{base} {detail}"
    if item.detail_style == "at":
        return f"{base} at {detail}"
    return f"{base} ({detail})"


def render_quantity_latex(item: QuantityResult) -> str:
    r"""LaTeX with an upright unit: ``3.31 \times 10^{-19}\,\mathrm{J}\ (\text{2.07 eV})``."""
    base = latex_quantity(item.value, item.unit)
    if item.detail is None:
        return base
    detail = plain_numbers_in(item.detail).translate(_LATEX_TEXT_SPECIALS)
    if item.detail_style == "suffix":
        return rf"{base}\ \text{{{detail}}}"
    if item.detail_style == "at":
        return rf"{base}\ \text{{at {detail}}}"
    return rf"{base}\ (\text{{{detail}}})"


def _plain_symbol(symbol: str) -> str:
    return re.sub(r"\\mathrm\{([^}]*)\}", r"\1", symbol).replace("{", "").replace("}", "")


def render_chip(items: tuple[QuantityResult, ...], joiner: str = " and ") -> str:
    """The answer in plain text, for guards, logs and the readers without math."""
    if not items:
        raise ValueError("a physics result needs a quantity")
    if joiner == "paren-second" and len(items) > 1:
        head = render_quantity(items[0])
        rest = ", ".join(render_quantity(item) for item in items[1:])
        return f"{head} ({rest})"
    if joiner == "projectile":
        return "; ".join(
            f"{_plain_symbol(item.symbol)} = {render_quantity(item)}" for item in items
        )
    return (" and " if joiner == "paren-second" else joiner).join(
        render_quantity(item) for item in items
    )


def render_chip_latex(items: tuple[QuantityResult, ...], joiner: str = " and ") -> str:
    """The same answer for the answer card, typeset."""
    if not items:
        raise ValueError("a physics result needs a quantity")
    if joiner == "paren-second" and len(items) > 1:
        head = render_quantity_latex(items[0])
        rest = r",\ ".join(render_quantity_latex(item) for item in items[1:])
        return rf"{head}\ ({rest})"
    if joiner == "projectile":
        return r";\quad ".join(f"{item.symbol} = {render_quantity_latex(item)}" for item in items)
    word = "and" if joiner == "paren-second" else joiner.strip()
    return rf"\ \text{{{word}}}\ ".join(render_quantity_latex(item) for item in items)
