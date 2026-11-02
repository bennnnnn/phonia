"""A question in parts: the reply's result fences held to every part's verified result.

Each part of "A ball is dropped from 20 m. What is its speed after 1 s? How long does it
take to reach the ground?" is verified on its own, and the reply carries each part's card
and scene. A subject's fence check holds a reply to one verified block, so it dropped every
card and scene but that block's, and both parts lost theirs (2026-11-01). Here a result
fence stays when it is one of the parts' own fences (``SubjectFence.cards``) and goes when it
is none of them: a card no part verified is never kept.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Sequence

from app.services.answer_fence import ANSWER_FENCE_LANGS, answer_fence_value
from app.services.card_value import final_answer_only
from app.services.md_fence_scan import Fence, iter_fences

# Fences that state a result or draw one; a part's cards may add their own (a molecule).
RESULT_FENCE_LANGS = frozenset({*ANSWER_FENCE_LANGS, "graph", "simulation", "geometry"})


def _key(lang: str, body: str) -> tuple[str, str]:
    """What a fence says, spelled one way: an answer by its value (the check line and
    notation header aside), a picture by its data (JSON key order and spacing aside)."""
    if lang in ANSWER_FENCE_LANGS:
        value = unicodedata.normalize("NFKC", final_answer_only(answer_fence_value(body)))
        return "answer", "".join(value.split())
    try:
        data = json.loads(body)
    except ValueError:
        return lang, body.strip()
    return lang, json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _closed(text: str) -> Iterable[Fence]:
    return (fence for fence in iter_fences(text) if fence.closed)


def _keys(cards: Sequence[str]) -> set[tuple[str, str]]:
    return {
        _key(fence.lang, card[fence.body_start : fence.body_end])
        for card in cards
        for fence in _closed(card)
    }


def keep_part_fences(text: str, cards: Sequence[str]) -> str:
    """``text`` with only the result fences that are one of ``cards`` (every part's own)."""
    own = _keys(cards)
    langs = RESULT_FENCE_LANGS | {lang for lang, _value in own}
    dropped = [
        fence
        for fence in iter_fences(text)
        if fence.lang in langs
        and (
            not fence.closed or _key(fence.lang, text[fence.body_start : fence.body_end]) not in own
        )
    ]
    for fence in reversed(dropped):
        text = text[: fence.start] + text[fence.end :]
    return re.sub(r"\n{3,}", "\n\n", text).strip() if dropped else text
