"""LLM-structured MathIntent extraction — the fallback when regex finds nothing.

The regex extractors in ``extract.py`` are fast but narrow: novel wording that
the gate still recognizes as math ("Integrate x squared") used to fall straight
to the unverified honesty note. This module makes ONE hidden structured-output
call on a fast internal alias and maps the result onto the existing
``MathIntent`` — the same pattern the camera path uses for vision extracts.

Two invariants keep this honest:

- The model never sees fence JSON or ``canonical_*`` fields (lesson: showing
  the chat model fence examples taught it to invent them). The prompt below is
  a bare extraction schema.
- The extracted intent is never trusted. It is only a *candidate* for the
  existing SymPy verified-block builder; if SymPy cannot close it, the turn
  gets the same honesty note it would have gotten without this call.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.models.routing_lanes import ROUTING
from app.modules.math.schemas import MathIntent

logger = logging.getLogger(__name__)

# The gate already decided this text is math-flavored; the extraction prompt
# only needs the raw request. Cap it so a pasted essay cannot blow up tokens.
_MAX_INPUT_CHARS = 2000

_EXTRACT_PROMPT = """Convert the user's request into structured JSON for a symbolic math solver.

Return JSON only, exactly one of these shapes:
- {"found": false} — not a concrete solvable math problem, or data is missing.
- {"found": true, "kind": "equation", "lhs": "2*x+3", "rhs": "7", "variable": "x"}
- {"found": true, "kind": "system", "equations": [["x+y", "10"], ["x-y", "2"]],
  "variables": ["x", "y"]}
- {"found": true, "kind": "inequality", "lhs": "2*x+1", "rhs": "5",
  "comparator": "<", "variable": "x"}
- {"found": true, "kind": "calculus", "operation": "integrate", "expr": "x^2",
  "variable": "x"} — operation is one of simplify|differentiate|integrate|factor|expand;
  add "lower"/"upper" only for a definite integral.
- {"found": true, "kind": "limit", "expr": "sin(x)/x", "point": "0", "variable": "x"}
- {"found": true, "kind": "graph", "expr": "x^2 - 2*x", "variable": "x"}

Rules:
- Plain ASCII math only: * for multiplication, ^ for powers, sqrt(x) for roots,
  pi for π. No LaTeX, no $ delimiters.
- Logarithms as written: log(x) is base 10, ln(x) is the natural log, log_2(x)
  has base 2. Never turn ln into log.
- Copy the user's numbers and terms exactly. Never invent, drop, or "fix" a term.
- Spoken math is written out: "x squared" → x^2, "the integral of x" → integrate x.
- Word problems, proofs, "explain why", or anything the shapes above cannot fully
  capture → {"found": false}."""


class LLMMathExtract(BaseModel):
    """Narrow extraction schema — deliberately NOT the 60-field MathIntent."""

    found: bool = False
    kind: Literal["equation", "system", "inequality", "calculus", "limit", "graph"] | None = None
    lhs: str | None = Field(default=None, max_length=256)
    rhs: str | None = Field(default=None, max_length=256)
    expr: str | None = Field(default=None, max_length=256)
    variable: str = Field(default="x", max_length=4)
    comparator: Literal["<", ">", "<=", ">="] | None = None
    operation: Literal["simplify", "differentiate", "integrate", "factor", "expand"] | None = None
    lower: str | None = Field(default=None, max_length=64)
    upper: str | None = Field(default=None, max_length=64)
    point: str | None = Field(default=None, max_length=64)
    equations: list[tuple[str, str]] | None = None
    variables: list[str] | None = None


def to_math_intent(extract: LLMMathExtract) -> MathIntent | None:
    """Map a validated extract onto a MathIntent; None when fields are missing."""
    if not extract.found or extract.kind is None:
        return None
    if extract.kind == "equation" and extract.lhs and extract.rhs:
        return MathIntent(
            kind="equation",
            lhs=extract.lhs,
            rhs=extract.rhs,
            operation="solve",
            variable=extract.variable,
        )
    if extract.kind == "system" and extract.equations and extract.variables:
        if len(extract.equations) > 4:
            return None
        return MathIntent(
            kind="system",
            system_equations=extract.equations,
            system_variables=extract.variables[:4],
            operation="solve",
        )
    if extract.kind == "inequality" and extract.lhs and extract.rhs and extract.comparator:
        return MathIntent(
            kind="inequality",
            lhs=extract.lhs,
            rhs=extract.rhs,
            comparator=extract.comparator,
            operation="solve",
            variable=extract.variable,
        )
    if extract.kind == "calculus" and extract.expr and extract.operation:
        return MathIntent(
            kind="calculus",
            expr=extract.expr,
            operation=extract.operation,
            variable=extract.variable,
            integral_lower=extract.lower,
            integral_upper=extract.upper,
        )
    if extract.kind == "limit" and extract.expr and extract.point:
        return MathIntent(
            kind="limit",
            expr=extract.expr,
            limit_point=extract.point,
            operation="limit",
            variable=extract.variable,
        )
    if extract.kind == "graph" and extract.expr:
        return MathIntent(
            kind="graph",
            expr=extract.expr,
            operation="graph",
            variable=extract.variable,
        )
    return None


async def llm_extract_math_intent(
    text: str,
    settings: Settings,
    *,
    usage: dict[str, int] | None = None,
    timeout_seconds: float | None = None,
    alone: bool = False,
) -> MathIntent | None:
    """One bounded structured-extraction call. Never raises into the chat path.

    The model reader (``modules/model_reader``) counts its tokens (``usage``), gives it its
    own time (``timeout_seconds``) and asks it ``alone``: no fallback model, and a timeout
    logged quietly, since nothing waits on it."""
    if not settings.math_llm_extract_enabled:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    # Imported here, not at module top: SymPy pool workers import this package
    # to solve, and litellm alone added about 190 MB to each of them.
    from app.gateways import litellm_gateway

    try:
        parsed = await litellm_gateway.complete_structured(
            settings=settings,
            model_alias=ROUTING.math_extract,
            messages=[
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": cleaned[:_MAX_INPUT_CHARS]},
            ],
            schema=LLMMathExtract,
            max_tokens=256,
            timeout_seconds=timeout_seconds or settings.math_llm_extract_timeout_seconds,
            usage=usage,
            allow_fallback=not alone,
            fallback_on_invalid=not alone,
            quiet_timeout=alone,
        )
    except Exception:
        # complete_structured already swallows provider/parse failures; this is
        # the belt for anything else (route resolution, event-loop edges).
        logger.warning("llm math extract failed", exc_info=True)
        return None
    if parsed is None:
        return None
    return complex_reading(to_math_intent(parsed), cleaned)


def complex_reading(intent: MathIntent | None, text: str) -> MathIntent | None:
    """A simplification about complex numbers is complex arithmetic.

    The schema has no complex kind, so "Simplify and write in the form a + bi:
    i^320 - 5i^121 + 3i^45" came back a simplification in the letter i, and its card
    was ``i^45(i^275 - 5i^76 + 3)``; read with i the imaginary unit it is 1 - 2i."""
    from app.modules.math.tools.school.complex import imaginary_unit_meant

    if (
        intent is None
        or intent.kind != "calculus"
        or intent.operation not in {"simplify", "expand"}
        or not imaginary_unit_meant(text, intent.expr or "")
    ):
        return intent
    # "Expand (x + 3i)²" stays an expansion, in complex numbers.
    operation = "expand" if intent.operation == "expand" else "eval"
    return MathIntent(kind="complex", school_op=operation, expr=intent.expr, operation="solve")
