"""The maths-notation rule both maths' pack and chat's every-turn maths-ink rule state.

Maths' pack (``modules/math/reply_policy``) quotes it, and so does the maths-ink rule every
turn gets (chat's ``prompt_constants/math``), so it sits below both.
"""

MATH_NOTATION_CLARIFICATION_HINT = (
    "If mathematical notation is unclear, unrecognized, or malformed, ask one brief "
    "clarification instead of guessing its meaning. Do not invent a named mathematical "
    "concept or silently change the expression. Standard, unambiguous notation aliases "
    "are fine. A bare log is base 10, as on a school calculator; write the natural log "
    "as ln."
)
