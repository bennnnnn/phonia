"""Pure text-scanning primitives with no subject semantics.

Neither of these knows what a "kind" is or what a solver does — they answer
"is this phrase glued inside a longer word" and "does this look like an
equals-sign equation," nothing more. Math's extractor layer and physics's
extractor layer both lean on them heavily, so they live here rather than in
`app.modules.math`, which used to make physics import through math just to
reach a string scanner. See docs/SUBJECT_SEPARATION_TICKETS.md (S4).
"""

from __future__ import annotations


def word_index(lower: str, phrase: str) -> int:
    """First index of ``phrase`` not glued inside a longer letter-run."""
    start = 0
    n = len(phrase)
    while True:
        idx = lower.find(phrase, start)
        if idx == -1:
            return -1
        before_ok = idx == 0 or not lower[idx - 1].isalpha()
        after = idx + n
        after_ok = after >= len(lower) or not lower[after].isalpha()
        if before_ok and after_ok:
            return idx
        start = idx + 1


def has_any_word(lower: str, words: tuple[str, ...]) -> bool:
    """True when any of ``words`` appears as a whole word (``word_index``)."""
    return any(word_index(lower, word) != -1 for word in words)


def parens_balanced(text: str) -> bool:
    """Every ``)`` closes an earlier ``(`` and none is left open."""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def has_equation(text: str) -> bool:
    eq = text.find("=")
    if eq <= 0 or eq >= len(text) - 1:
        return False
    if text[eq + 1 : eq + 2] == "=":
        return False
    lhs, rhs = text[:eq].strip(), text[eq + 1 :].strip()
    return bool(lhs and rhs and any(c.isalnum() for c in lhs) and any(c.isalnum() for c in rhs))
