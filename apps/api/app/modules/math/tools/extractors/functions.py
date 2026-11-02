"""Intent extraction for deterministic single-variable function analysis."""

from __future__ import annotations

import re

from app.modules.math.schemas import MathIntent
from app.modules.math.tools.expr_rewrite import _normalize_latex_expr, math_expr_or_none
from app.modules.math.tools.function_def import peel_function_definition
from app.modules.math.tools.request_text import strip_trailing_filler

_FUNC_DEF_START = re.compile(r"\b([A-Za-z])\s*\(\s*([A-Za-z])\s*\)\s*=", re.IGNORECASE)
_TRAILING_JOINER = re.compile(r"(?:\sand|[,;])\s*$", re.IGNORECASE)
_FUNCTION_ANALYSIS_CUE_RE = re.compile(
    r"\b(?:domain|range|inverse(?:\s+function)?)\b",
    re.IGNORECASE,
)
_FUNCTION_RESTRICTION_RE = re.compile(
    r"\b(?:on|for|where|when)\b[^,;]*?(?:<=|>=|<|>|≤|≥|\bin\b|\bbetween\b|\[|\()",
    re.IGNORECASE,
)


def function_analysis_constraint_would_be_dropped(text: str) -> bool:
    """True when a supported function ask includes a domain restriction.

    Domain/range/inverse helpers currently operate on the maximal real domain.
    A restriction such as ``on x >= 0`` must never be peeled away and replaced
    by a confidently verified unrestricted answer.
    """
    return bool(_FUNCTION_ANALYSIS_CUE_RE.search(text) and _FUNCTION_RESTRICTION_RE.search(text))


def _function_definitions(text: str) -> list[tuple[str, str, str]]:
    """Return explicit ``(name, variable, expression)`` definitions in order."""
    matches = list(_FUNC_DEF_START.finditer(text))
    out: list[tuple[str, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        body = _TRAILING_JOINER.sub("", body).strip()
        # Common postfix request: ``..., find f(g(x))``.
        lower = body.lower()
        cut: int | None = None
        for marker in (", find ", "; find ", ", compute ", "; compute "):
            at = lower.find(marker)
            if at != -1 and (cut is None or at < cut):
                cut = at
        if cut is not None:
            body = body[:cut].strip()
        guarded = math_expr_or_none(_normalize_latex_expr(strip_trailing_filler(body)))
        if guarded is None:
            return []
        out.append((match.group(1), match.group(2), guarded))
    return out


def _composition_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    compact = re.sub(r"\s+", "", lower)
    if "compose" not in lower and not re.search(r"[a-z]\([a-z]\([a-z]\)\)", compact):
        return None
    defs = _function_definitions(cleaned)
    if len(defs) != 2:
        return None
    first_name, first_var, first_expr = defs[0]
    second_name, second_var, second_expr = defs[1]
    if first_var.lower() != second_var.lower():
        return None
    var = first_var
    first_call = f"{first_name.lower()}({second_name.lower()}({var.lower()}))"
    second_call = f"{second_name.lower()}({first_name.lower()}({var.lower()}))"
    if second_call in compact:
        outer, inner = second_expr, first_expr
    elif first_call in compact or "compose" in lower:
        # ``compose f and g`` convention here is f∘g; explicit nested notation
        # above always wins when the user names the order.
        outer, inner = first_expr, second_expr
    else:
        return None
    return MathIntent(
        kind="calculus",
        operation="simplify",
        school_op="function_compose",
        expr=outer,
        expr2=inner,
        variable=var,
    )


# "even or odd" is unambiguous; "symmetric" alone is not (a symmetric matrix,
# a symmetric layout), so it only counts beside "about the y-axis"/"the origin".
_EVEN_ODD_RE = re.compile(
    r"\b(?:even\s+or\s+odd|odd\s+or\s+even)\b"
    r"|\bsymmetric\b[^.?!]{0,30}?\b(?:y[- ]axis|origin)\b",
    re.IGNORECASE,
)
_EVEN_ODD_FUNCTION_RE = re.compile(
    r"(?:f\s*\(\s*x\s*\)|y)\s*=\s*"
    r"(\S(?:[^\n]*?\S)??(?:[^\S\n]+(?=[?.!]*$))?|[^\S\n](?=\n*\S|\n?\Z))"
    r"(?=\s*(?:[,;]\s*)?(?:is\s+it\b|is\s+this\b|even\b|odd\b|symmetric\b)|[?.!]*$)",
    re.IGNORECASE,
)


def _single_function_intent(cleaned: str) -> MathIntent | None:
    lower = cleaned.lower()
    if "[[" in cleaned or "matrix" in lower:
        return None
    # Number theory owns modular inverses. Without this guard, the generic
    # ``inverse of`` cue can steal ``modular inverse of 3 mod 11`` before the
    # number-theory extractor gets a chance to verify it.
    if "modular inverse" in lower or " mod " in lower or " modulo " in lower:
        return None
    if function_analysis_constraint_would_be_dropped(cleaned):
        return None

    # "is f(x)=x^3 even or odd" puts its cue *after* the function, so it is
    # read before the leading-cue table below rather than through it.
    if _EVEN_ODD_RE.search(cleaned):
        match = _EVEN_ODD_FUNCTION_RE.search(cleaned)
        if match is None:
            return None
        expr = math_expr_or_none(_normalize_latex_expr(strip_trailing_filler(match.group(1))))
        if not expr:
            return None
        return MathIntent(
            kind="calculus",
            operation="simplify",
            school_op="function_symmetry",
            expr=expr,
            variable="x",
        )

    op: str | None = None
    cue: str | None = None
    for phrase, name in (
        ("domain of", "function_domain"),
        ("range of", "function_range"),
        ("inverse function of", "function_inverse"),
        ("inverse of", "function_inverse"),
    ):
        at = lower.find(phrase)
        if at != -1:
            op, cue = name, phrase
            break
    if op is None:
        for prefix, name in (
            ("domain ", "function_domain"),
            ("range ", "function_range"),
            ("inverse function ", "function_inverse"),
        ):
            if lower.startswith(prefix):
                op, cue = name, prefix.strip()
                break
    if op is None or cue is None:
        return None

    defs = _function_definitions(cleaned)
    if len(defs) == 1:
        _name, var, expr = defs[0]
    elif defs:
        return None
    else:
        at = lower.find(cue)
        raw = cleaned[at + len(cue) :].strip() if at != -1 else ""
        raw = peel_function_definition(strip_trailing_filler(raw))
        # ``range of 1,2,3`` is descriptive statistics, not function range.
        # A comma also means this single-variable function extractor cannot
        # safely claim the whole request.
        if op == "function_range" and "," in raw:
            return None
        expr = math_expr_or_none(_normalize_latex_expr(raw)) or ""
        var = "x"
    if not expr:
        return None
    return MathIntent(
        kind="calculus",
        operation="simplify",
        school_op=op,
        expr=expr,
        variable=var,
    )


def _extract_function_analysis_intent(cleaned: str) -> MathIntent | None:
    composed = _composition_intent(cleaned)
    if composed is not None:
        return composed
    return _single_function_intent(cleaned)


FUNCTION_EXTRACTORS = (_extract_function_analysis_intent,)
