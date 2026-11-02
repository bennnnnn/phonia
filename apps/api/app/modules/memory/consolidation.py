"""When a memory section needs rewriting, and whether a rewrite is acceptable.

Policy only — the LLM call and the DB write live in
consolidation_workflow.py. Kept apart from the caching and locking
machinery so the rules can be read and tested on their own.
"""

import logging
import re
from collections.abc import Iterable
from typing import Any

from app.modules.memory.fact_quality import FactView, texts_to_drop
from app.modules.memory.ops import normalize_memory_text
from app.modules.memory.text import merge_diet_facts

logger = logging.getLogger(__name__)

_CONSOLIDATION_ANCHOR_STOP = frozenset(
    {
        "user",
        "the",
        "and",
        "for",
        "with",
        "who",
        "that",
        "this",
        "their",
        "they",
        "prefers",
        "likes",
        "works",
        "name",
        "is",
        "are",
        "was",
        "has",
        "have",
    }
)


_NEAR_DUP_JACCARD = 0.8


def _fact_tokens(text: str) -> frozenset[str]:
    return frozenset(part for part in normalize_memory_text(text).lower().split() if part)


def fact_text_jaccard(left: str, right: str) -> float:
    a = _fact_tokens(left)
    b = _fact_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def facts_need_consolidation(memories: Iterable[Any]) -> bool:
    """True when two active facts are duplicates, or one should be dropped."""
    active_views = [
        FactView(text=normalize_memory_text(getattr(memory, "text", "")))
        for memory in memories
        if str(getattr(memory, "status", None) or "active") == "active"
        and normalize_memory_text(getattr(memory, "text", ""))
    ]
    if texts_to_drop(active_views):
        return True
    active: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for memory in memories:
        status = str(getattr(memory, "status", None) or "active")
        if status != "active":
            continue
        text = normalize_memory_text(getattr(memory, "text", ""))
        if not text:
            continue
        key = (str(getattr(memory, "type", "")), text.lower())
        if key in seen:
            return True
        seen.add(key)
        active.append(key)
    for index, (left_type, left_text) in enumerate(active):
        left_tokens = _fact_tokens(left_text)
        if not left_tokens:
            continue
        for right_type, right_text in active[index + 1 :]:
            if left_type != right_type:
                continue
            if fact_text_jaccard(left_text, right_text) >= _NEAR_DUP_JACCARD:
                return True
    return False


def extract_consolidation_anchors(text: str) -> frozenset[str]:
    """Salient tokens from prior memory text that a rewrite should preserve."""
    anchors: set[str] = set()
    for match in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.-]+", text):
        anchors.add(match.group(0).lower())
    for match in re.finditer(r"\b\d{2,}\b", text):
        anchors.add(match.group(0))
    for match in re.finditer(r'"([^"]{2,80})"', text):
        quoted = match.group(1).strip().lower()
        if quoted:
            anchors.add(quoted)
    for match in re.finditer(r"\b[A-Z][a-zA-Z0-9-]{2,}\b", text):
        token = match.group(0).lower()
        if token not in _CONSOLIDATION_ANCHOR_STOP:
            anchors.add(token)
    return frozenset(anchors)


def consolidation_rewrite_preserves_facts(
    prior: str,
    summary: str,
    *,
    min_preserved_ratio: float = 0.8,
) -> bool:
    """True when enough prior anchors appear in the rewritten summary.

    The gate rejects a merge that drops 20% of the anchors or more (the default
    ``min_preserved_ratio=0.8``): keeping exactly 80% is a rejection too, hence the
    strict ``>``.
    """
    anchors = extract_consolidation_anchors(prior)
    if len(anchors) < 2:
        return True
    haystack = summary.lower()
    preserved = sum(1 for anchor in anchors if anchor in haystack)
    return preserved / len(anchors) > min_preserved_ratio


def accept_memory_section_rewrite(
    *,
    section_type: str,
    prior: str,
    summary: str,
    confidence: float,
    min_confidence: float,
    enforce_length_floor: bool = True,
    allow_clear: bool = False,
) -> str | None:
    """Validate a whole-section rewrite before upsert (extraction + consolidation).

    Rejects low confidence, empty text, catastrophic shortening, and rewrites
    that drop too many prior fact anchors — so a flaky LLM pass cannot silently
    erase stable facts (name, employer, allergy, …). Explicit forget commands
    pass ``allow_clear`` only so an empty summary can wipe that section; nonempty
    rewrites still go through the shortening and anchor checks.
    """
    if confidence < min_confidence:
        return None
    clean = normalize_memory_text(summary)
    if not clean:
        return "" if allow_clear else None
    # Exact-sentence dedupe can shrink well below 50%; only LLM merges use the floor.
    if enforce_length_floor and prior and len(clean) < len(prior) * 0.5:
        logger.warning(
            "Skipping memory rewrite for %s: new text much shorter than existing",
            section_type,
        )
        return None
    if prior and not consolidation_rewrite_preserves_facts(prior, clean):
        logger.warning(
            "Skipping memory rewrite for %s: rewrite dropped prior fact anchors",
            section_type,
        )
        return None
    # Identical text is still "accepted" so extraction can re-embed stale rows;
    # callers that only want real changes should compare against prior.
    if prior and not allow_clear:
        clean = merge_diet_facts(prior, clean)
    return clean
