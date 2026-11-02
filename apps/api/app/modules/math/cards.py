"""The fences maths writes for a verified block: its answer card and its pictures.

A question in parts keeps, of the reply's fences, the ones that are one of its parts' own
(``chat.finalize_subjects``); these are the maths part's, built the way the maths fence
check builds them (``math.fence``).
"""

from __future__ import annotations

import json

from app.modules.math.fence import (
    canonical_answer_body,
    collect_canonical_specs,
    spec_fence_kind,
)
from app.services.md_fence_scan import iter_fences
from app.services.part_fences import RESULT_FENCE_LANGS
from app.services.solving import VerifiedMathBlock

# A teaching spec is drawn in an ```arithmetic fence, as the check draws it.
_FENCE_OF_KIND = {
    "geometry": "geometry",
    "graph": "graph",
    "teach": "arithmetic",
    "arithmetic": "arithmetic",
}


def solver_cards(verified: VerifiedMathBlock) -> tuple[str, ...]:
    answer = canonical_answer_body(verified)
    cards = [f"```answer\n{answer}\n```"] if answer else []
    for spec in collect_canonical_specs(verified):
        language = _FENCE_OF_KIND.get(spec_fence_kind(spec) or "")
        if language is not None:
            cards.append(f"```{language}\n{json.dumps(spec, separators=(',', ':'))}\n```")
    # The solver's own reply writes its card its way: "\frac{dy}{dx} = -\frac{x}{y}".
    written = verified.direct_reply or ""
    cards.extend(
        written[fence.start : fence.end]
        for fence in iter_fences(written)
        if fence.closed and fence.lang in RESULT_FENCE_LANGS
    )
    return tuple(cards)
