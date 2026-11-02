"""Pre-stream symbolic math augmentation for chat prompts."""

from __future__ import annotations

from app.modules.math import solve as math_solve
from app.modules.math.tools.block import (
    VerifiedMathBlock,
    _answer_canonical,
    _build_verified_block,
    _format_equation_answer,
    _format_system_answer,
)
from app.modules.math.tools.direct import (
    maybe_direct_math_reply,
    wants_math_explanation,
)
from app.modules.math.tools.extract import extract_math_intent
from app.modules.math.tools.prompt import (
    _build_verified_block_async,
    build_math_augmentation,
    needs_symbolic_math,
)

__all__ = [
    "VerifiedMathBlock",
    "_answer_canonical",
    "_build_verified_block",
    "_build_verified_block_async",
    "_format_equation_answer",
    "_format_system_answer",
    "build_math_augmentation",
    "extract_math_intent",
    "math_solve",
    "maybe_direct_math_reply",
    "needs_symbolic_math",
    "wants_math_explanation",
]
