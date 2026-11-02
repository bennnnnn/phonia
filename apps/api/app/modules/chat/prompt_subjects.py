"""Each subject's prompt hints, listed explicitly. The subject owns them; chat states them.

A subject's adapter (``services/subjects/registry``) carries its hints (``SubjectHints``).
Statistics and biology have no module yet: chat's ``continuation_subject`` names them,
so their one hint each stays in ``prompt_constants/format.py`` until a module owns it.
"""

from __future__ import annotations

from app.modules.chat.prompt_constants import (
    BIOLOGY_PRESENTATION_HINT,
    MATH_FENCE_SAFETY_HINT,
    STATISTICS_PRESENTATION_HINT,
    VERIFIED_SOLVE_SAFETY_HINT,
)
from app.services.subject_hints import SubjectHints
from app.services.subjects.registry import subject_adapter

# In this order: the leak pass joins the rules as listed (``prompt_rule_text``).
SUBJECT_HINTS: dict[str, SubjectHints] = {
    "physics": subject_adapter("physics").hints,
    "math": subject_adapter("math").hints,
    "chemistry": subject_adapter("chemistry").hints,
    "statistics": SubjectHints(lambda _short: (STATISTICS_PRESENTATION_HINT,)),
    "biology": SubjectHints(lambda _short: (BIOLOGY_PRESENTATION_HINT,)),
}


def subject_presentation_hints(subject: str | None, *, short: bool) -> list[str]:
    """A subject's hints after the shared verified-solve rule; no subject gets maths ink."""
    hints = SUBJECT_HINTS.get(subject or "")
    if hints is None:
        return [MATH_FENCE_SAFETY_HINT]
    ink = [MATH_FENCE_SAFETY_HINT] if hints.shared_math_ink else []
    return [VERIFIED_SOLVE_SAFETY_HINT, *hints.presentation(short), *ink]


def subject_closing_hints(subject: str | None) -> tuple[str, ...]:
    """A subject's reply policy. It comes late, so the detail it allows wins."""
    hints = SUBJECT_HINTS.get(subject or "")
    return hints.closing if hints else ()
