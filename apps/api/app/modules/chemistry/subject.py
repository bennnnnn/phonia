"""Chemistry as the subject registry asks it (``services/subjects/registry``).

The adapter calls what chemistry already has: the reading of a line through ``reading``, the
verified block through ``context`` (with its fence hint from ``reply_policy``) and the direct
reply through ``direct``, each imported when it runs; and its prompt copy from
``reply_policy`` and ``followup``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.modules.chemistry.followup import CHEMISTRY_FOLLOWUP_HINT, chemistry_followup_problem
from app.modules.chemistry.reply_policy import (
    CHEMISTRY_FENCE_HINT,
    CHEMISTRY_PRESENTATION_HINT,
    chemistry_prompt_hints,
)
from app.modules.chemistry.request import is_chemistry_question
from app.modules.chemistry.shape_followup import (
    could_ask_a_shape,
    is_show_line,
    last_question_line,
    shape_followup_problem,
)
from app.services.solving import SubjectAugmentation
from app.services.subject_hints import SubjectHints

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.solving import VerifiedSolveBlock
    from app.services.subjects.registry import SubjectRequest


_HINTS = SubjectHints(
    chemistry_prompt_hints,
    followup=(CHEMISTRY_FOLLOWUP_HINT,),
    beside_visuals=(CHEMISTRY_PRESENTATION_HINT, CHEMISTRY_FENCE_HINT),
)


@dataclass(frozen=True)
class ChemistryFollowups:
    def problem(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> str | None:
        return chemistry_followup_problem(query, recent)

    def continues(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> bool:
        return chemistry_followup_problem(query, recent) is not None

    def previous_result(self, reply: str) -> str | None:
        return None

    def continues_alone(self, line: str) -> bool:
        return False

    def borrows_earlier(self, line: str) -> bool:
        return False

    def asks_to_see(self, line: str, recent: Sequence[Any] | None = None) -> bool:
        # "can u show me both" right after a shape answer asks for its molecules.
        if not is_show_line(line):
            return False
        return recent is None or could_ask_a_shape(last_question_line(recent))

    def shown_problem(self, line: str, recent: Sequence[Any]) -> str | None:
        return shape_followup_problem(line, recent)


@dataclass(frozen=True)
class ChemistryFence:
    """Chemistry checks the replies it verified, and draws its molecules (chat's finalize)."""

    def needs_check(self, text: str, verified: VerifiedSolveBlock | None) -> bool:
        return True

    def check(
        self, text: str, verified: VerifiedSolveBlock | None, correct: bool, user_text: str
    ) -> str:
        from app.modules.chemistry.fence import validate_chemistry_fences

        return validate_chemistry_fences(text, verified=verified, correct=correct)

    def recover(self, text: str, verified: VerifiedSolveBlock | None) -> str:
        from app.modules.chemistry.fence import replace_unclosed_chemistry_fences_safe

        return replace_unclosed_chemistry_fences_safe(text, verified)

    def cards(self, verified: VerifiedSolveBlock) -> tuple[str, ...]:
        from app.modules.chemistry.fence import solver_cards

        return solver_cards(verified)

    def unverified_note(self, text: str) -> str:
        from app.modules.chemistry.context import append_unverified_chemistry_note

        return append_unverified_chemistry_note(text)

    def draws(self, text: str, settings: Settings) -> bool:
        lowered = text.lower()
        return settings.chemistry_enabled and ("```smiles" in lowered or "```chemistry" in lowered)

    def draw(self, text: str, settings: Settings) -> str:
        from app.modules.chemistry.fence import enrich_chemistry_fences_worker

        return enrich_chemistry_fences_worker(text)

    def tidy(self, text: str, user_text: str, verified: VerifiedSolveBlock | None) -> str:
        return text


@dataclass(frozen=True)
class ChemistrySubject:
    name: Literal["chemistry"] = "chemistry"
    hints: SubjectHints = _HINTS
    followups: ChemistryFollowups = ChemistryFollowups()
    fence: ChemistryFence = ChemistryFence()
    # No photo reader and no model tool of its own.
    photo: None = None
    tool: None = None

    def asks(self, text: str, *, has_image_attachment: bool = False) -> bool:
        return is_chemistry_question(text)

    def reads(self, text: str) -> bool:
        from app.modules.chemistry.extract import extract_chemistry_intent

        return extract_chemistry_intent(text) is not None

    def fast_lane(self, text: str, *, tools_on: bool) -> bool | None:
        # A chemistry answer's card is the server's: the fast model only presents it.
        return True

    def instant_reply(self, text: str, *, prior_reply: str | None) -> str | None:
        return None

    def warm(self) -> None:
        return None

    def solve_timeouts(self) -> AbstractContextManager[list[str]]:
        return nullcontext([])

    async def solve(self, request: SubjectRequest, settings: Settings) -> SubjectAugmentation:
        if not settings.chemistry_enabled:
            return SubjectAugmentation(None, None, None)
        from app.modules.chemistry.context import build_chemistry_augmentation
        from app.modules.chemistry.reading import chemistry_text_for_solve
        from app.modules.chemistry.reply_policy import attach_chemistry_fence_hint

        block, verified, declined = await build_chemistry_augmentation(
            chemistry_text_for_solve(request.text), settings, redis=request.redis
        )
        if block:
            block = attach_chemistry_fence_hint(block)
        return SubjectAugmentation(
            subject="chemistry" if block or verified else None,
            prompt_block=block,
            verified=verified,
            unverified=declined,
        )

    def direct_reply(
        self,
        verified: VerifiedSolveBlock,
        user_text: str,
        *,
        has_image_attachment: bool,
        verified_request_text: str | None,
    ) -> str | None:
        del verified_request_text
        from app.modules.chemistry.block import VerifiedChemistry
        from app.modules.chemistry.direct import maybe_direct_chemistry_reply

        if not isinstance(verified, VerifiedChemistry):
            return None
        return maybe_direct_chemistry_reply(
            verified,
            has_image_attachment=has_image_attachment,
            user_text=user_text,
        )


CHEMISTRY_SUBJECT = ChemistrySubject()
