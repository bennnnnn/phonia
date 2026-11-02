"""The maths-ink rule every turn gets. The maths pack is ``modules/math/reply_policy``."""

from app.services.math_notation import MATH_NOTATION_CLARIFICATION_HINT

MATH_FENCE_SAFETY_HINT = (
    "If you write math, use inline `$...$` (never backticks around `$...$`). Code is not math: "
    "in a programming answer, values and expressions stay in `inline code`, never `$...$`. "
    "A ```math fence is only for a standalone display equation. "
    "Money keeps its sign: write amounts as plain text ($48, $7.20), never inside `$...$`, "
    "where a `$` opens maths and the sign is lost (inside maths, write \\$7.20). "
    "Do NOT emit ```answer, ```arithmetic, ```graph, or ```geometry. NEVER ```latex or an untagged "
    "code fence for LaTeX. "
    f"{MATH_NOTATION_CLARIFICATION_HINT}"
)
