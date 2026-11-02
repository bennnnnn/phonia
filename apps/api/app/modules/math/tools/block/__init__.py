"""kind → verified system block. Registry: _BLOCK_BUILDERS."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.core.config import Settings
from app.modules.math import solve as math_solve
from app.modules.math.schemas import MathIntent
from app.modules.math.solve.restated import REWRITES, card_restates
from app.modules.math.tools.block.algebra import (
    _verified_block_equation,
    _verified_block_inequality,
    _verified_block_numerical_method,
    _verified_block_system,
)
from app.modules.math.tools.block.answer_text import (
    _format_equation_answer as _format_equation_answer,
)
from app.modules.math.tools.block.answer_text import (
    _format_system_answer as _format_system_answer,
)
from app.modules.math.tools.block.calculus import _verified_block_calculus
from app.modules.math.tools.block.canonical import (
    _answer_canonical as _answer_canonical,
)
from app.modules.math.tools.block.canonical import (
    _diagram_block as _diagram_block,
)
from app.modules.math.tools.block.canonical import (
    finish_with_answer as finish_with_answer,
)
from app.modules.math.tools.block.discrete import (
    _verified_block_combinatorics,
    _verified_block_number_theory,
)
from app.modules.math.tools.block.geometry import (
    _verified_block_circle,
    _verified_block_parallelogram,
    _verified_block_rectangle,
    _verified_block_right_triangle,
    _verified_block_sector,
    _verified_block_square,
    _verified_block_trapezoid,
    _verified_block_triangle,
    _verified_block_triangle_sides,
)
from app.modules.math.tools.block.graph import (
    _verified_block_graph,
    _verified_block_graph_pair,
    _verified_block_point,
    _verified_block_vertical,
)
from app.modules.math.tools.block.limits import _verified_block_limit
from app.modules.math.tools.block.matrix import _verified_block_matrix
from app.modules.math.tools.block.series import _verified_block_series
from app.modules.math.tools.block.solid import _verified_block_solid
from app.modules.math.tools.block.statistics import _verified_block_statistics
from app.modules.math.tools.block.word import _verified_block_word_problem
from app.modules.math.tools.block.work import _verified_block_work_check
from app.services.solving import (
    VerifiedMathBlock as VerifiedMathBlock,
)
from app.services.solving import wrap_verified_math

logger = logging.getLogger(__name__)

# ``Any`` is limited to this declarative registry boundary. Every concrete
# builder and the public dispatcher remain math-only and precisely typed.
_BlockBuilder = Callable[[Any, Settings, list[str]], VerifiedMathBlock | None]

_BLOCK_BUILDERS: dict[str, _BlockBuilder] = {
    "equation": _verified_block_equation,
    "inequality": _verified_block_inequality,
    "system": _verified_block_system,
    "numerical_method": _verified_block_numerical_method,
    "rectangle": _verified_block_rectangle,
    "square": _verified_block_square,
    "solid": _verified_block_solid,
    "circle": _verified_block_circle,
    "triangle": _verified_block_triangle,
    "right_triangle": _verified_block_right_triangle,
    "triangle_sides": _verified_block_triangle_sides,
    "trapezoid": _verified_block_trapezoid,
    "parallelogram": _verified_block_parallelogram,
    "sector": _verified_block_sector,
    "point": _verified_block_point,
    "vertical": _verified_block_vertical,
    "graph": _verified_block_graph,
    "graph_pair": _verified_block_graph_pair,
    "calculus": _verified_block_calculus,
    "limit": _verified_block_limit,
    "series": _verified_block_series,
    "statistics": _verified_block_statistics,
    "combinatorics": _verified_block_combinatorics,
    "number_theory": _verified_block_number_theory,
    "matrix": _verified_block_matrix,
    "work_check": _verified_block_work_check,
    "word_problem": _verified_block_word_problem,
}


# SymPy's complex infinity and NaN. ``5/0`` once shipped a green ``\tilde{\infty}``
# card; a value that is undefined says so in words (``\text{undefined}``).
_NON_FINITE = re.compile(r"\\tilde\{\\infty\}|\bNaN\b|\bnan\b|\bzoo\b")


def _shows_non_finite(block: VerifiedMathBlock) -> bool:
    shown = (block.canonical_answer, block.display_answer, block.direct_reply, block.worked_reply)
    return any(_NON_FINITE.search(text) for text in shown if text)


def _restates(intent: MathIntent, block: VerifiedMathBlock) -> bool:
    """A rewrite whose card is the expression it was given (``solve/restated.py``)."""
    return bool(
        intent.kind == "calculus"
        and intent.operation in REWRITES
        and block.canonical_answer
        and card_restates(block.canonical_answer, (intent.expr,))
    )


def _build_verified_block(intent: MathIntent, settings: Settings) -> VerifiedMathBlock | None:
    lines: list[str] = []

    try:
        builder: _BlockBuilder | None = _BLOCK_BUILDERS.get(intent.kind)
        if builder is None:
            from app.modules.math.tools.school import SCHOOL_BLOCK_BUILDERS

            builder = SCHOOL_BLOCK_BUILDERS.get(intent.kind)
        if builder is None:
            return None
        block = builder(intent, settings, lines)
        if block is None or _shows_non_finite(block):
            return None
        if _restates(intent, block):
            return None

        # A rendered reply and a literal plot are bound to the request they read.
        bound = block.direct_reply is not None or intent.plot_point is not None
        return replace(
            block,
            text=wrap_verified_math(block.text),
            geometry_request=intent.geometry_request,
            plot_point=intent.plot_point,
            direct_request_text=intent._request_text if bound else None,
            direct_requires_calculus_guard=bool(
                block.direct_reply is not None
                and intent.kind == "calculus"
                and intent.school_op is None
                and intent.operation in {"differentiate", "integrate"}
            ),
            direct_answer_binding=(
                block.canonical_answer if block.direct_reply is not None else None
            ),
        )
    except math_solve.SolveServiceError as exc:
        # The class only: a SolveServiceError's message quotes the user's expression.
        logger.info("math_tools skipped: %s", type(exc).__name__)
        return None
    except Exception:
        logger.exception("math_tools failed")
        return None


def verified_curves(
    exprs: tuple[str, ...], x_min: float | None, x_max: float | None, settings: Settings
) -> dict[str, object] | None:
    """The ```graph spec for one or two curves y = f(x), sampled as "graph …" samples them.

    For a formula that reached the reply some other way (a model's chart of ``sin(x)``):
    the same builder, so the curve is SymPy's and never the phone's. None when SymPy
    cannot read or sample it.
    """
    if not 1 <= len(exprs) <= 2:
        return None
    intent = MathIntent(
        kind="graph" if len(exprs) == 1 else "graph_pair",
        expr=exprs[0],
        expr2=exprs[1] if len(exprs) == 2 else None,
        operation="graph",
        graph_x_min=x_min,
        graph_x_max=x_max,
    )
    block = _build_verified_block(intent, settings)
    fence = block.canonical_fence if block is not None else None
    return fence if isinstance(fence, dict) and fence.get("points") else None
