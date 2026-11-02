"""The word "search" and its typos ("seearch", "serach"), never "starch"."""

from __future__ import annotations

from app.services.text_normalize import fold_token

_SEARCH_WORD = "search"
# Real words one edit from "search"; never a misspelled command.
_NOT_SEARCH_TYPOS = frozenset({"starch"})
_SEARCH_FORMS = frozenset({"search", "searches", "searching", "serch", "seach"})


def _one_edit_apart(word: str, target: str) -> bool:
    """True for one insertion, deletion, substitution or adjacent swap."""
    if word == target:
        return True
    lw, lt = len(word), len(target)
    if abs(lw - lt) > 1:
        return False
    if lw == lt:
        diffs = [i for i in range(lw) if word[i] != target[i]]
        if len(diffs) == 1:
            return True
        return (
            len(diffs) == 2
            and diffs[1] == diffs[0] + 1
            and word[diffs[0]] == target[diffs[1]]
            and word[diffs[1]] == target[diffs[0]]
        )
    shorter, longer = (word, target) if lw < lt else (target, word)
    i = j = 0
    skipped = False
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
            continue
        if skipped:
            return False
        skipped = True
        j += 1
    return True


def is_search_word(word: str) -> bool:
    """ "search" and its typos ("seearch", "serach", "searh"), not "starch"."""
    folded = fold_token(word)
    if folded in _SEARCH_FORMS:
        return True
    if folded in _NOT_SEARCH_TYPOS or len(folded) < 5 or not folded.startswith("s"):
        return False
    return _one_edit_apart(folded, _SEARCH_WORD)
