"""Maths as the subject registry asks it (``services/subjects/registry``).

The adapter calls what maths already has: the verified block through ``tools.prompt``, the
direct reply through ``tools.direct``, and its prompt copy from ``reply_policy`` and
``followup``.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from app.modules.math.followup import (
    MATH_FOLLOWUP_HINT,
    answer_claim_problem,
    is_math_followup,
    math_working_followup_problem,
    offered_equation_problem,
    pronoun_math_problem,
    readable_standalone_answer,
    restated_math_problem,
)
from app.modules.math.reply_policy import MATH_REPLY_POLICY, math_prompt_hints
from app.modules.math.tools.prompt import (
    NOTHING_TO_GRAPH,
    build_math_augmentation,
    needs_symbolic_math,
)
from app.services.solving import SubjectAugmentation, VerifiedMathBlock
from app.services.subject_hints import SubjectHints

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.modules.math.schemas import MathImageExtract
    from app.services.solving import VerifiedSolveBlock
    from app.services.subjects.registry import SubjectRequest


_HINTS = SubjectHints(
    math_prompt_hints,
    (MATH_REPLY_POLICY,),
    shared_math_ink=False,
    followup=(MATH_REPLY_POLICY, MATH_FOLLOWUP_HINT),
)


@dataclass(frozen=True)
class MathFollowups:
    def problem(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> str | None:
        # Its verified working first. "Do it" after the assistant wrote a new equation is
        # not a request to re-solve the user's earlier line: the offered equation is solved
        # instead. "check my answer: x = 6" is checked against the open problem, and
        # "simplify it" works on the user's last expression. Alone, each one used to be
        # solved as typed: ``x = 6`` verified itself and "it" was ``i t``.
        found = math_working_followup_problem(query, recent, blocked=blocked)
        if found is None:
            found = offered_equation_problem(query, recent)
        if found is None:
            found = (
                answer_claim_problem(query, recent, blocked=blocked)
                or pronoun_math_problem(query, recent, blocked=blocked)
                or restated_math_problem(query, recent, blocked=blocked)
            )
        return found

    def continues(
        self,
        query: str | None,
        recent: Sequence[Any],
        *,
        blocked: Callable[[str], bool] | None = None,
    ) -> bool:
        return is_math_followup(query, recent, blocked=blocked)

    def previous_result(self, reply: str) -> str | None:
        return readable_standalone_answer(reply)

    def continues_alone(self, line: str) -> bool:
        # "graph it" / "plot this equation" with no new formula.
        from app.modules.math.tools.extract import is_graph_followup

        return is_graph_followup(line)

    def borrows_earlier(self, line: str) -> bool:
        from app.modules.math.tools.prompt import borrows_earlier_lines

        return borrows_earlier_lines(line)

    def asks_to_see(self, line: str, recent: Sequence[Any] | None = None) -> bool:
        return False

    def shown_problem(self, line: str, recent: Sequence[Any]) -> str | None:
        return None


@dataclass(frozen=True)
class MathFence:
    """Maths owns every reply chemistry or physics did not verify (chat's finalize passes)."""

    def needs_check(self, text: str, verified: VerifiedSolveBlock | None) -> bool:
        from app.modules.math.fence import needs_math_fence_validate

        return needs_math_fence_validate(text, _math_block(verified))

    def check(
        self, text: str, verified: VerifiedSolveBlock | None, correct: bool, user_text: str
    ) -> str:
        from app.modules.math.fence import validate_math_fences_worker

        return validate_math_fences_worker(text, _math_block(verified), correct)

    def recover(self, text: str, verified: VerifiedSolveBlock | None) -> str:
        from app.modules.math.fence import replace_unclosed_graph_fence_safe

        canonical = verified.canonical_fence if verified is not None else None
        return replace_unclosed_graph_fence_safe(text, canonical)

    def cards(self, verified: VerifiedSolveBlock) -> tuple[str, ...]:
        from app.modules.math.cards import solver_cards

        block = _math_block(verified)
        return solver_cards(block) if block is not None else ()

    def unverified_note(self, text: str) -> str:
        from app.modules.math.fence import append_unverified_math_note

        return append_unverified_math_note(text)

    def draws(self, text: str, settings: Settings) -> bool:
        # A chart the model wrote as a formula: the phone never evaluates one.
        from app.modules.math.chart_formula import has_formula_chart

        return has_formula_chart(text)

    def draw(self, text: str, settings: Settings) -> str:
        from app.modules.math.chart_formula import formula_charts_to_graphs

        return formula_charts_to_graphs(text, settings)

    def tidy(self, text: str, user_text: str, verified: VerifiedSolveBlock | None) -> str:
        # A graph drawn in text characters on a graph turn.
        from app.modules.math.text_plot import strip_text_plots_on_graph_turn

        return strip_text_plots_on_graph_turn(text, user_text, verified)


def _math_block(verified: VerifiedSolveBlock | None) -> VerifiedMathBlock | None:
    """The turn's block when it is maths' (chat asks maths only when no peer verified)."""
    return verified if isinstance(verified, VerifiedMathBlock) else None


@dataclass(frozen=True)
class MathPhoto:
    """The equation in a turn's photo (``camera``), so SymPy can verify the answer."""

    async def read(
        self,
        content: str,
        *,
        image_attachments: list[tuple[str, str]],
        load_image: Callable[[str], Awaitable[bytes | None]],
        settings: Settings,
        on_status: Callable[[str], Awaitable[None]] | None,
    ) -> tuple[MathImageExtract | None, str]:
        from app.modules.math.camera import read_camera_maths

        return await read_camera_maths(
            content,
            image_attachments=image_attachments,
            load_image=load_image,
            settings=settings,
            on_status=on_status,
        )


@dataclass(frozen=True)
class MathTool:
    """The ``sympy`` model tool (``tool.py``), as the tool loop checks its calls."""

    def refuses(self, name: str, raw_args: Any, user_text: str) -> bool:
        # The trig solver owns all-real solutions: the tool schema cannot express the
        # requested interval or another domain.
        if name != "sympy":
            return False
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (TypeError, ValueError):
            return False  # Let the registry report malformed arguments normally.
        if not isinstance(args, dict):
            return False
        if str(args.get("action") or "solve").strip().lower() != "solve":
            return False
        from app.modules.math.tools.extract import trig_domain_would_be_dropped

        return trig_domain_would_be_dropped(
            f"{args.get('lhs') or ''} {args.get('rhs') or ''}", user_text
        )

    def call_matches(self, raw_args: Any, user_texts: list[str]) -> str | None:
        from app.modules.math.tool_check import matched_user_text

        return matched_user_text(raw_args, user_texts)

    def draws_curve(self, fence: dict[str, Any] | None) -> bool:
        from app.modules.math.text_plot import is_curve_fence

        return is_curve_fence(fence)

    def asks_for_earlier_curve(self, text: str) -> bool:
        from app.modules.math.text_plot import asks_for_an_earlier_curve

        return asks_for_an_earlier_curve(text)


@dataclass(frozen=True)
class MathSubject:
    name: Literal["math"] = "math"
    hints: SubjectHints = _HINTS
    followups: MathFollowups = MathFollowups()
    fence: MathFence = MathFence()
    photo: MathPhoto = MathPhoto()
    tool: MathTool = MathTool()

    def asks(self, text: str, *, has_image_attachment: bool = False) -> bool:
        return needs_symbolic_math(text, has_image_attachment=has_image_attachment)

    def reads(self, text: str) -> bool:
        from app.modules.math.tools.extract import extract_math_intent

        return extract_math_intent(text) is not None

    def fast_lane(self, text: str, *, tools_on: bool) -> bool | None:
        """SymPy already covers these; a reasoning model only writes a CoT essay.

        Keep equations / calculus / graphs on the maths lane (False). Bare factorial
        ("4!") and "what is 1+1" style arithmetic stay on the fast model.
        """
        from app.modules.math.match import (
            bare_arithmetic_expr,
            combinatorics_signal,
            prepare,
            written_arithmetic_request,
        )

        cleaned = prepare(text)
        if not cleaned:
            return False
        sig = combinatorics_signal(cleaned)
        if sig is not None and sig[0] == "factorial":
            return True
        # Same whole-message helper as the SymPy gate — a lone "1+1" inside a
        # harder question must not keep the turn on the fast model.
        return (
            bare_arithmetic_expr(cleaned) is not None
            or written_arithmetic_request(cleaned) is not None
        )

    def instant_reply(self, text: str, *, prior_reply: str | None) -> str | None:
        # "3x" alone: what it means, an example, what to ask next.
        from app.modules.math.match import bare_expression_reply

        return bare_expression_reply(text, prior_assistant=prior_reply)

    def warm(self) -> None:
        from app.modules.math.sympy_warmup import warm_math_worker

        warm_math_worker()

    def solve_timeouts(self) -> AbstractContextManager[list[str]]:
        # A pre-solve that ran out of time: the tool loop does not run it again.
        from app.modules.math.tools.solve_timeouts import recording

        return recording()

    async def solve(self, request: SubjectRequest, settings: Settings) -> SubjectAugmentation:
        block, math_verified = await build_math_augmentation(
            request.math_text,
            settings,
            has_image_attachment=request.has_image_attachment,
            image_math_extract=request.image_math_extract,
            needs_math=True,
            prior_user_messages=request.prior_user_messages,
            response_intent_text=request.response_intent_text,
        )
        return SubjectAugmentation(
            subject="math",
            prompt_block=block,
            verified=math_verified,
            # Asking which function to graph is not an unverified answer.
            unverified=(
                block is not None and math_verified is None and block is not NOTHING_TO_GRAPH
            ),
        )

    def direct_reply(
        self,
        verified: VerifiedSolveBlock,
        user_text: str,
        *,
        has_image_attachment: bool,
        verified_request_text: str | None,
    ) -> str | None:
        if not isinstance(verified, VerifiedMathBlock):
            return None
        from app.modules.math.tools.direct import maybe_direct_math_reply

        return maybe_direct_math_reply(
            verified,
            user_text,
            has_image_attachment=has_image_attachment,
            verified_request_text=verified_request_text,
        )


MATH_SUBJECT = MathSubject()
