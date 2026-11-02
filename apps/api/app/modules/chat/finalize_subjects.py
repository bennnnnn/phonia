"""Finalize passes that keep the answer card the server's.

The model's reply is prepared first: it cannot forge the server's check. Then the
subject that verified the turn checks the reply's fences against its block
(chemistry and physics by their own ``fence.py``; maths owns every other reply),
and the reply gets the notes and the working check an unverified answer needs.
``chat/finalize_passes.py`` lists these passes in order.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, TypeGuard

from app.core import sympy_executor
from app.modules.chat.verification_claims import strip_verification_claims
from app.modules.chat.working_check import is_worked_solution, working_note
from app.services.answer_fence import (
    demote_answer_fences,
    land_answer_card,
    mark_server_answer_fences,
    normalize_owned_fences,
    strip_forged_verified_markers,
    strip_model_simulation_fences,
)
from app.services.part_answer_cards import land_part_answer_cards
from app.services.part_fences import keep_part_fences
from app.services.solving import (
    VerifiedMathBlock,
    VerifiedPhysicsBlock,
    VerifiedSolveBlock,
    strip_verified_solve_markers,
)
from app.services.subjects.registry import subject_adapter

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

logger = logging.getLogger(__name__)

# A line that may say a result was checked, for when reading its claims fails.
_CHECK_WORDS = re.compile(r"checked|confirmed|sympy|[✅✔☑✓]", re.IGNORECASE)


def fallback_text(raw: str, *, server_text: bool) -> str:
    """What persists when finalizing fails: never a check the server did not write."""
    try:
        if server_text:
            return mark_server_answer_fences(raw)
        return strip_forged_verified_markers(raw)
    except Exception:
        logger.exception("answer-card fallback failed; dropping marker lines")
        return _without_marker_lines(raw)


def _without_marker_lines(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if "verified" not in line.lower())


def drop_check_lines(text: str) -> str:
    """What stands in when preparing the model's reply fails: no line that could carry
    a check marker, none of its own check claims and none of its own scenes."""
    text = _without_marker_lines(text)
    try:
        return strip_model_simulation_fences(strip_verification_claims(text))
    except Exception:
        logger.exception("check-claim strip failed; dropping lines that name a check")
        return "\n".join(line for line in text.split("\n") if not _CHECK_WORDS.search(line))


def prepare_model_reply(state: FinalizeState) -> str:
    """Model text before any server card is added to it.

    The model cannot forge the server's ``verified: true`` line, every spelling
    of its answer fences is put in the one form the subject passes demote, and
    its own "✅ Verified with SymPy" claims go: on an unverified turn they fake
    the check, and on a verified one the card says it (a claim beside a wrong
    value would contradict it). A ```simulation scene is solver-sampled, so the
    model's own never ships; a verified physics turn replaces it in its pass.
    """
    if state.server_text:
        return state.text
    text = normalize_owned_fences(strip_forged_verified_markers(state.text))
    text = strip_verification_claims(text)
    if not isinstance(state.ctx.verified_subject, VerifiedPhysicsBlock):
        text = strip_model_simulation_fences(text)
    return text


def _check_part_fences(state: FinalizeState) -> str | None:
    """A question in parts: each part's card and pictures held to that part's verified
    result, whichever subject verified it; a fence no part verified goes. ``None`` for a
    turn with one verified result, which its subject checks."""
    verified = state.ctx.verified_subject
    parts = verified.question_parts if verified is not None else ()
    if len(parts) < 2:
        return None
    cards = [card for part in parts for card in subject_adapter(part.subject).fence.cards(part)]
    return keep_part_fences(state.text, cards)


def _chemistry_verified(verified: VerifiedSolveBlock | None) -> bool:
    return verified is not None and verified.subject == "chemistry"


def check_chemistry_fences(state: FinalizeState) -> str:
    """Chemistry answer text is not algebra: the maths rewrite would read its
    formulas and slash-units as expressions, so chemistry checks its own turns."""
    verified = state.ctx.verified_subject
    if not _chemistry_verified(verified):
        return state.text
    in_parts = _check_part_fences(state)
    if in_parts is not None:
        return in_parts
    # The server never corrects its own text: only model prose can state a value
    # that differs from the verified one.
    return subject_adapter("chemistry").fence.check(
        state.text, verified, not state.server_text, state.ctx.user_message_content
    )


def recover_chemistry_fences(state: FinalizeState) -> str:
    return subject_adapter("chemistry").fence.recover(state.text, state.ctx.verified_subject)


def _physics_block(state: FinalizeState) -> VerifiedPhysicsBlock | None:
    verified = state.ctx.verified_subject
    return verified if isinstance(verified, VerifiedPhysicsBlock) else None


def check_physics_fences(state: FinalizeState) -> str:
    verified = _physics_block(state)
    if verified is None:
        return state.text
    in_parts = _check_part_fences(state)
    if in_parts is not None:
        return in_parts
    return subject_adapter("physics").fence.check(
        state.text, verified, not state.server_text, state.ctx.user_message_content
    )


def recover_physics_fences(state: FinalizeState) -> str:
    return subject_adapter("physics").fence.recover(state.text, _physics_block(state))


def _math_owns(verified: VerifiedSolveBlock | None) -> TypeGuard[VerifiedMathBlock | None]:
    """Maths checks every reply chemistry or physics did not verify; the block is maths'."""
    return not _chemistry_verified(verified) and not isinstance(verified, VerifiedPhysicsBlock)


async def check_math_fences(state: FinalizeState) -> str:
    verified = state.ctx.verified_subject
    if not _math_owns(verified):
        return state.text
    in_parts = _check_part_fences(state)
    if in_parts is not None:
        return in_parts
    math_fence = state.deps.math_fence
    if state.server_text:
        # Two solved problems have no single verified subject. Their answer
        # fences are the results. The unverified rewrite unwraps every
        # ```answer, which printed "notation: chemistry" and raw LaTeX under
        # the reply.
        if verified is None:
            return state.text
        # Direct verified replies already carry ```answer. Running that rewrite
        # on the SymPy pool can queue behind an integral for no benefit — keep
        # it in-process.
        return math_fence.check(state.text, verified, False, state.ctx.user_message_content)
    if not math_fence.needs_check(state.text, verified):
        return state.text
    if state.on_status is not None:
        # The reply has streamed; this check (up to the SymPy timeout) runs
        # before it saves, while the phone still shows it as working.
        await state.on_status("checking")
    try:
        # Through the module: tests swap the SymPy pool for an inline runner there.
        return await sympy_executor.run_sympy(
            math_fence.check,
            state.text,
            verified,
            True,
            state.ctx.user_message_content,
            timeout=state.settings.stem_solve_timeout_seconds,
        )
    finally:
        if state.on_status is not None:
            # The check is over: its label must not stay up while the reply saves.
            await state.on_status("finishing")


async def draw_formula_charts(state: FinalizeState) -> str:
    """A chart the model wrote as a formula (``"fn": "sin(x)"``): the phone never
    evaluates one, so SymPy samples it into a ```graph, or a note takes its place.
    After the maths pass, which would strip a ```graph no solver wrote."""
    maths = subject_adapter("math").fence
    if not maths.draws(state.text, state.settings):
        return state.text
    return await sympy_executor.run_sympy(
        maths.draw,
        state.text,
        state.settings,
        timeout=state.settings.stem_solve_timeout_seconds,
    )


def recover_math_fences(state: FinalizeState) -> str:
    """The maths rewrite did not run, so the model's own answer fences are
    demoted here (no solver needed): a timed-out pool must not let a model's
    ```answer through as a card. Wholly server text keeps its cards.
    """
    text = state.deps.math_fence.recover(state.text, state.ctx.verified_subject)
    if state.server_text:
        return text
    return demote_answer_fences(text)


def mark_server_cards(state: FinalizeState) -> str:
    if not state.server_text:
        return state.text
    return mark_server_answer_fences(state.text)


def append_unverified_notes(state: FinalizeState) -> str:
    """Every reply, checked or not, gets the maths note when it needs one: the
    check mark is the only signal. A declined chemistry solve gets its own."""
    text = subject_adapter("math").fence.unverified_note(state.text)
    ctx = state.ctx
    if ctx.solver_unverified is True and ctx.unverified_subject == "chemistry":
        text = subject_adapter("chemistry").fence.unverified_note(text)
    return text


def check_working(state: FinalizeState) -> str:
    """Working the model wrote with no verified result behind it: a slip in one
    multiplication carries into the answer, so name the first one. Its final
    answer goes in the same card a verified one does, without the check.
    """
    ctx = state.ctx
    text = state.text
    if state.server_text or ctx.verified_subject is not None or state.was_cancelled:
        return text
    if ctx.solver_unverified is True or is_worked_solution(text):
        note = working_note(text)
        # A reply in parts gets a card under each part's Answer heading.
        text = land_part_answer_cards(text) or land_answer_card(text, None)
        if note:
            text = f"{text.rstrip()}\n\n{note}"
    return text


def strip_text_plots(state: FinalizeState) -> str:
    """A graph drawn in text characters on a graph turn: the prompt forbids it,
    and the phone shows it as broken rows of symbols."""
    ctx = state.ctx
    return subject_adapter("math").fence.tidy(
        state.text, ctx.user_message_content, ctx.verified_subject
    )


def strip_solve_markers(state: FinalizeState) -> str:
    """Prompt scaffolding must never survive into the reply. The model is told
    not to mention a system block, but instruction is not enforcement — this is
    the enforcement."""
    return strip_verified_solve_markers(state.text)


async def enrich_chemistry_fences(state: FinalizeState) -> str:
    chemistry = subject_adapter("chemistry").fence
    if not chemistry.draws(state.text, state.settings):
        return state.text
    return await sympy_executor.run_sympy(
        chemistry.draw,
        state.text,
        state.settings,
        timeout=state.settings.stem_solve_timeout_seconds,
    )
