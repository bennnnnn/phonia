"""A photographed problem's vision extract, mapped onto the intent the solvers already know.

Split from ``tools.prompt``. The extract is Pydantic-validated; it is never re-read
through the text regex, which mangles the unicode operators and absolute-value bars a
photographed problem can contain.
"""

from __future__ import annotations

from typing import Literal, cast

from app.modules.math.schemas import MathImageExtract, MathIntent


def intent_from_image_extract(extract: MathImageExtract) -> MathIntent | None:
    """Map a vision extract onto an existing MathIntent kind (no second parser)."""
    variable = extract.variables[0]
    if extract.kind == "system" and extract.equations:
        if len(extract.equations) > 4:
            return None
        return MathIntent(
            kind="system",
            system_equations=extract.equations,
            system_variables=extract.variables,
            operation="solve",
        )
    if extract.kind == "inequality" and extract.comparator:
        return MathIntent(
            kind="inequality",
            lhs=extract.lhs,
            rhs=extract.rhs,
            comparator=extract.comparator,
            operation="solve",
            variable=variable,
        )
    if extract.kind == "calculus" and extract.expr and extract.operation:
        return MathIntent(
            kind="calculus",
            expr=extract.expr,
            operation=cast(
                Literal["simplify", "differentiate", "integrate", "factor", "expand"],
                extract.operation,
            ),
            variable=variable,
            integral_lower=extract.integral_lower,
            integral_upper=extract.integral_upper,
        )
    if extract.kind == "limit" and extract.expr and extract.limit_point:
        return MathIntent(
            kind="limit",
            expr=extract.expr,
            limit_point=extract.limit_point,
            operation="limit",
            variable=variable,
        )
    if extract.kind == "graph" and extract.expr:
        return MathIntent(
            kind="graph",
            expr=extract.expr,
            operation="graph",
            variable=variable,
        )
    if extract.kind == "rectangle" and extract.width is not None and extract.height is not None:
        return MathIntent(
            kind="rectangle",
            width=extract.width,
            height=extract.height,
            unit=extract.unit or "cm",
            wants_area=True,
            wants_perimeter=True,
        )
    if extract.kind == "circle" and extract.radius is not None:
        return MathIntent(
            kind="circle",
            radius=extract.radius,
            unit=extract.unit or "cm",
            wants_area=True,
            wants_circumference=True,
        )
    if (
        extract.kind == "triangle_sides"
        and extract.tri_a is not None
        and extract.tri_b is not None
        and extract.tri_c is not None
    ):
        return MathIntent(
            kind="triangle_sides",
            tri_a=extract.tri_a,
            tri_b=extract.tri_b,
            tri_c=extract.tri_c,
            unit=extract.unit or "cm",
            operation="solve",
        )
    if extract.kind == "statistics" and extract.stats_numbers and extract.stats_op:
        return MathIntent(
            kind="statistics",
            stats_op=cast(
                Literal["mean", "median", "mode", "variance", "stdev"],
                extract.stats_op,
            ),
            stats_numbers=extract.stats_numbers,
            operation="solve",
        )
    return MathIntent(
        kind="equation",
        lhs=extract.lhs,
        rhs=extract.rhs,
        operation="solve",
        variable=variable,
    )
