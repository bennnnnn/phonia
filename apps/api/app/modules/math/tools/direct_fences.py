"""The fences a verified math block shows, shared by the direct-reply guards."""

from __future__ import annotations

from app.services.solving import VerifiedMathBlock

# Longer answers are prose the model should frame, not a chip.
MAX_DIRECT_ANSWER_CHARS = 400


def solver_fences(verified: VerifiedMathBlock) -> list[dict[str, object]]:
    fences: list[dict[str, object]] = []
    if verified.canonical_fence is not None:
        fences.append(verified.canonical_fence)
    for fence in verified.canonical_fences:
        if fence is not None and fence not in fences:
            fences.append(fence)
    return fences
