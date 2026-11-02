"""A subject's prompt copy, and where the prompt states it.

Each subject's adapter (``services/subjects/registry``) carries one; chat states it (its
``prompt_subjects`` and ``prompt_sections``) and holds two of its own for the presentation
subjects no module owns yet (statistics, biology).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectHints:
    """One subject's hints, and where the prompt states them."""

    # Short style or a compact turn -> the hints after the layout and photo hints.
    presentation: Callable[[bool], Sequence[str]]
    # The reply policy, after the shared copy and writing rules.
    closing: tuple[str, ...] = ()
    # The maths and physics packs carry their own maths-ink rules; the rest get chat's.
    shared_math_ink: bool = True
    # A turn that only continues the subject's last problem ("how?", "what about 2 moles?").
    followup: tuple[str, ...] = ()
    # Fixed copy the leak pass reads as rules beside chat's visuals rules: chemistry's
    # presentation and structure-fence hints, as its reply-policy module holds them.
    beside_visuals: tuple[str, ...] = ()
