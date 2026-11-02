"""Whether a message asks for a comparison, a callout, a how-to or a quote."""

from __future__ import annotations

import re

from app.modules.turn_reading.chart import is_chart_question
from app.modules.turn_reading.diagrams import is_mermaid_question

_COMPARISON_TURN = re.compile(
    r"(?:"
    r"\bvs\.?\b|"
    r"\bversus\b|"
    r"\bcompar(?:e|ed|ing|ison)\b|"
    r"\bdifference(?:s)?\s+between\b|"
    r"\bside[\s-]?by[\s-]?side\b|"
    r"\bwhich\s+is\s+better\b"
    r")",
    re.IGNORECASE,
)


def is_comparison_question(text: str) -> bool:
    """True when the user is asking for an X vs Y / feature comparison."""
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(_COMPARISON_TURN.search(cleaned))


_TECHNICAL_COMPARE_WORDS = (
    "python",
    "java",
    "javascript",
    "typescript",
    "rust",
    "kotlin",
    "swift",
    "react",
    "vue",
    "angular",
    "django",
    "flask",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "linux",
    "windows",
    "android",
    "typing",
    "syntax",
    "compiler",
)


def _has_whole_word(haystack: str, word: str) -> bool:
    """Linear whole-word scan — avoid regex over the user turn."""
    lower = haystack.lower()
    start = 0
    n = len(word)
    while True:
        idx = lower.find(word, start)
        if idx < 0:
            return False
        before = lower[idx - 1] if idx > 0 else " "
        after = lower[idx + n] if idx + n < len(lower) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = idx + n


def is_structured_comparison_question(text: str) -> bool:
    """Table + code-card compare: languages/tools/features, not tea vs coffee."""
    if not is_comparison_question(text):
        return False
    lower = text.strip().lower()
    if any(
        cue in lower
        for cue in (
            "feature",
            "price",
            "cost",
            "performance",
            "battery",
            "camera",
            "specification",
            "specs",
            "use case",
            "pros and cons",
        )
    ):
        return True
    return any(_has_whole_word(lower, word) for word in _TECHNICAL_COMPARE_WORDS)


_CALLOUT_TURN = re.compile(
    r"(?:"
    r"\binclude\s+(?:a\s+)?(?:tip|note|warning)\b|"
    r"\b(?:important\s+|safety\s+)?warning\s+about\b|"
    r"\bcallout\b"
    r")",
    re.IGNORECASE,
)


def is_callout_question(text: str) -> bool:
    """True when the user asked for tips/notes/warnings as callouts, not a how-to table."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if (
        is_comparison_question(cleaned)
        or is_chart_question(cleaned)
        or is_mermaid_question(cleaned)
    ):
        return False
    return bool(_CALLOUT_TURN.search(cleaned))


# A plan over weeks or phases. "From scratch" stays here: "learn Python from
# scratch" is a roadmap, and the hint says one task is still one list of steps.
_HOWTO_TURN = re.compile(
    r"(?:"
    r"\b\d+[\s-]?week(?:s)?\s+plan\b|"
    r"\bweek[\s-]?by[\s-]?week\b|"
    r"\broadmap(?:\s+to\s+learn)?\b|"
    r"\b(?:learning|study)\s+plan\b|"
    r"\bplan\s+to\s+learn\b|"
    r"\bfrom scratch\b|"
    r"\bplan\s+de\s+\d+[\s-]?(?:semana|semanas|semaine|semaines)\b|"
    r"\b\d+[\s-]?wochen[\s-]?plan\b"
    r")",
    re.IGNORECASE,
)


def _owned_by_another_layout(cleaned: str) -> bool:
    """A compare, chart, flowchart or callout ask keeps that layout over a how-to's."""
    return (
        is_comparison_question(cleaned)
        or is_chart_question(cleaned)
        or is_mermaid_question(cleaned)
        or is_callout_question(cleaned)
    )


def is_howto_question(text: str) -> bool:
    """True for learning plans / roadmaps that must stay lists, not schedule tables."""
    cleaned = text.strip()
    if not cleaned or _owned_by_another_layout(cleaned):
        return False
    return bool(_HOWTO_TURN.search(cleaned))


# "How do I make tea", "how to tie a tie", "what are the steps to renew a
# passport": a task the user will do. Feelings and judgment ("how do I know if",
# "how do I deal with") are not steps.
_TASK_HOWTO = re.compile(
    r"^(?:(?:so|ok(?:ay)?|hey|hi|please|quick\s+question)[,!:]?\s+)?"
    r"(?:how\s+(?:do|can|should|would)\s+(?:i|you|we|one)|how\s+to"
    r"|what\s+(?:are|is)\s+the\s+steps?\s+(?:to|for)|(?:give\s+me\s+)?(?:the\s+)?steps\s+to)\s+"
    r"(?!(?:know|tell|feel|deal|cope|forgive|trust|decide|understand|stop\s+(?:feeling|thinking)"
    r"|get\s+over|be\s+(?:happy|confident|happier)|love|say|pronounce|spell)\b)[^\W\d_]",
    re.IGNORECASE,
)


# Asked for as steps anywhere in the message: "walk me through changing a tire",
# "install Python step by step", "receta de pan paso a paso".
_STEPWISE_TURN = re.compile(
    r"(?:"
    r"\bhow (?:do i|to) (?:set up|setup|install|configure|build)\b|"
    r"\bwalk\s+me\s+through\b|"
    r"\bstep[\s-]?by[\s-]?step\b|"
    r"\bpaso\s+a\s+paso\b|"
    r"\b(?:etape|étape)\s+par\s+(?:etape|étape)\b|"
    r"\bschritt[\s-]?f[uü]r[\s-]?schritt\b"
    r")",
    re.IGNORECASE,
)


def is_task_howto(text: str) -> bool:
    """True for "how do I <do a task>": numbered steps, not a plan or an essay."""
    cleaned = text.strip()
    if not cleaned or len(cleaned) > 300:
        return False
    if _TASK_HOWTO.search(cleaned) is not None:
        return True
    return _STEPWISE_TURN.search(cleaned) is not None and not _owned_by_another_layout(cleaned)


_QUOTE_TURN = re.compile(
    r"(?:"
    r"\b(?:give|share|tell)(?:\s+me)?\s+(?:an?\s+|one\s+)?"
    r"(?:famous\s+|well[- ]known\s+|inspirational\s+|motivational\s+)?"
    r"quotes?\b|"
    r"\b(?:famous|inspirational|motivational)\s+quotes?\b|"
    r"\bquotes?\s+by\b|"
    r"\bquotes?\s+(?:about|on|from)\b|"
    r"\bquotation\s+(?:by|from|about)\b"
    r")",
    re.IGNORECASE,
)


_STOCK_QUOTE = re.compile(
    r"(?:stock\s+quotes?|ticker\s+symbol|\bnasdaq\b|\bnyse\b)",
    re.IGNORECASE,
)


def is_quote_question(text: str) -> bool:
    """True when the user asked for a famous / attributed quotation, not a stock quote."""
    cleaned = text.strip()
    if not cleaned:
        return False
    if _STOCK_QUOTE.search(cleaned):
        return False
    return bool(_QUOTE_TURN.search(cleaned))
