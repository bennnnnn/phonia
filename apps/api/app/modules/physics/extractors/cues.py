"""Whether a text carries a topic's cue words or cue patterns."""

from __future__ import annotations

import re


def _has_cue_either_case(
    cleaned: str,
    cues: tuple[str, ...],
    regexes: tuple[re.Pattern[str], ...] = (),
) -> bool:
    """`has_cue`, but the regexes see the text as written as well as lowered.

    A few cue regexes mean the SI symbols `V` and `A` and are case-sensitive on
    purpose - "12 V and 3 A" is a circuit, "12 v cards and 3 a piece" is not.
    Handing them only lowercased text silently disables them, which is exactly
    what the pre-filter did: `needs_symbolic` dropped questions the extractor
    would have answered, because the extractor saw the original casing and the
    pre-filter did not. The two have to see the same thing.

    A case-insensitive regex finds the same thing in both, so it reads once.
    """
    lower = cleaned.lower()
    if any(cue in lower for cue in cues):
        return True
    return any(
        rx.search(cleaned) or (not rx.flags & re.IGNORECASE and rx.search(lower)) for rx in regexes
    )


def has_cue(
    lower: str,
    cues: tuple[str, ...],
    regexes: tuple[re.Pattern[str], ...] = (),
) -> bool:
    """Cue match: plain substrings, plus regexes for cues that need a boundary.

    Most cues are safe as substrings ("net force"). A few are not: "find f"
    sits inside "find factors", and "KE" inside "take". Those are expressed as
    regexes instead of widening the tuple.
    """
    if any(cue in lower for cue in cues):
        return True
    return any(rx.search(lower) for rx in regexes)
