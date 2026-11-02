"""Physics as the subject registry asks it (``services/subjects/registry``).

The adapter calls what physics already has: the verified block through ``prompt``, the
direct reply through ``direct``, and its prompt copy from ``reply_policy`` and ``followup``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.modules.physics.extract import needs_physics
from app.modules.physics.followup import PHYSICS_FOLLOWUP_HINT, physics_followup_problem
from app.modules.physics.prompt import build_physics_augmentation
from app.modules.physics.reply_policy import PHYSICS_REPLY_POLICY, physics_prompt_hints
from app.services.solving import SubjectAugmentation, VerifiedPhysicsBlock
from app.services.subject_hints import SubjectHints

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.solving import VerifiedSolveBlock
    from app.services.subjects.registry import SubjectRequest


def _physics_request_text(user_content: str) -> str:
    """The problem a physics turn verifies.

    A scanned photo's caption is a protocol line. When the student confirmed
    what the scanner read, that reading is the problem; without one, the
    caption alone gets the unverified physics note.
    """
    from app.services.subject_scan import confirmed_scan_reading, scanner_camera_subject

    if scanner_camera_subject(user_content) != "physics":
        return user_content
    return confirmed_scan_reading(user_content) or user_content


_HINTS = SubjectHints(
    physics_prompt_hints,
    (PHYSICS_REPLY_POLICY,),
    shared_math_ink=False,
    followup=(PHYSICS_FOLLOWUP_HINT,),
)


@dataclass(frozen=True)
class PhysicsFollowups:
    def problem(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> str | None:
        return physics_followup_problem(query, recent)

    def continues(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> bool:
        return physics_followup_problem(query, recent) is not None

    def previous_result(self, reply: str) -> str | None:
        return None

    def continues_alone(self, line: str) -> bool:
        return False

    def borrows_earlier(self, line: str) -> bool:
        return False

    def asks_to_see(self, line: str, recent: Sequence[Any] | None = None) -> bool:
        return False

    def shown_problem(self, line: str, recent: Sequence[Any]) -> str | None:
        return None


@dataclass(frozen=True)
class PhysicsFence:
    """Physics checks the replies it verified (chat's finalize passes)."""

    def needs_check(self, text: str, verified: VerifiedSolveBlock | None) -> bool:
        return True

    def check(
        self, text: str, verified: VerifiedSolveBlock | None, correct: bool, user_text: str
    ) -> str:
        from app.modules.physics.fence import validate_physics_fences

        return validate_physics_fences(
            text, verified=_physics_block(verified), correct=correct, user_text=user_text
        )

    def recover(self, text: str, verified: VerifiedSolveBlock | None) -> str:
        from app.modules.physics.fence import replace_unclosed_physics_fences_safe

        return replace_unclosed_physics_fences_safe(text, _physics_block(verified))

    def cards(self, verified: VerifiedSolveBlock) -> tuple[str, ...]:
        from app.modules.physics.fence import solver_cards

        block = _physics_block(verified)
        return solver_cards(block) if block is not None else ()

    def unverified_note(self, text: str) -> str:
        # An unverified physics turn's note is in its prompt, not under the reply.
        return text

    def draws(self, text: str, settings: Settings) -> bool:
        return False

    def draw(self, text: str, settings: Settings) -> str:
        return text

    def tidy(self, text: str, user_text: str, verified: VerifiedSolveBlock | None) -> str:
        return text


def _physics_block(verified: VerifiedSolveBlock | None) -> VerifiedPhysicsBlock | None:
    return verified if isinstance(verified, VerifiedPhysicsBlock) else None


@dataclass(frozen=True)
class PhysicsSubject:
    name: Literal["physics"] = "physics"
    hints: SubjectHints = _HINTS
    followups: PhysicsFollowups = PhysicsFollowups()
    fence: PhysicsFence = PhysicsFence()
    # No photo reader and no model tool of its own.
    photo: None = None
    tool: None = None

    def asks(self, text: str, *, has_image_attachment: bool = False) -> bool:
        return needs_physics(text)

    def reads(self, text: str) -> bool:
        from app.modules.physics.extract import extract_physics_intent

        return extract_physics_intent(text) is not None

    def fast_lane(self, text: str, *, tools_on: bool) -> bool | None:
        from app.modules.physics.lane import physics_fast_lane

        return physics_fast_lane(text, tools_on=tools_on)

    def instant_reply(self, text: str, *, prior_reply: str | None) -> str | None:
        return None

    def warm(self) -> None:
        return None

    def solve_timeouts(self) -> AbstractContextManager[list[str]]:
        return nullcontext([])

    async def solve(self, request: SubjectRequest, settings: Settings) -> SubjectAugmentation:
        block, physics_verified, solve_failed = await build_physics_augmentation(
            _physics_request_text(request.text),
            settings,
            needs_subject=True,
        )
        return SubjectAugmentation(
            subject="physics",
            prompt_block=block,
            verified=physics_verified,
            # No matching template is not a failed check. The prompt note still
            # tells the model not to claim a check. The reply does not say it
            # could not be verified.
            unverified=solve_failed,
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
        if not isinstance(verified, VerifiedPhysicsBlock):
            return None
        from app.modules.physics.direct import maybe_direct_physics_reply

        return maybe_direct_physics_reply(
            verified,
            user_text,
            has_image_attachment=has_image_attachment,
        )


PHYSICS_SUBJECT = PhysicsSubject()
