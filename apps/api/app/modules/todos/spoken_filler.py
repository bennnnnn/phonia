"""Filler a spoken reminder starts with, which is not part of its title.

"ok can you remind me to water the plants" saved "ok water the plants". Filler
goes when it is the only thing before "remind me", or when punctuation sets it
off ("oh, wait for the plumber"); "wait for the plumber" keeps "wait", since
there it is the task. "What is 2 + 2? Also remind me to buy milk" saved "also
buy milk": a joining word alone before "remind me" goes too.
"""

from __future__ import annotations

import re

FILLER_WORDS = r"(?:wait|ok|okay|actually|oh|no|nah|sorry|hmm)"
_JOINING_WORDS = r"(?:also|and|plus|then|so|btw)"
_ONLY_FILLER_RE = re.compile(
    rf"\s*(?:(?:{FILLER_WORDS}|{_JOINING_WORDS})\b[,!.]*\s*)+", re.IGNORECASE
)
_SET_OFF_FILLER_RE = re.compile(rf"^\s*(?:{FILLER_WORDS}[,!.]+\s*)+", re.IGNORECASE)


def without_lead_filler(text: str) -> str:
    """ "ok " before "can you remind me", "oh, " before the task; "wait for the bus" stays."""
    if _ONLY_FILLER_RE.fullmatch(text):
        return ""
    return _SET_OFF_FILLER_RE.sub("", text)
