"""Physics-owned prompt augmentation and verified-solve boundary."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Literal

from app.core.config import Settings
from app.modules.physics.block import _build_physics_block
from app.modules.physics.extract import extract_physics_intent, needs_physics
from app.modules.physics.parts import asks_count
from app.modules.physics.reply_policy import PHYSICS_REPLY_POLICY
from app.modules.physics.split_parts import solve_in_parts
from app.services.solving import VerifiedPhysicsBlock, wrap_verified_physics
from app.services.workout import PHYSICS_WORKOUT_PARTS_PROMPT, SELF_CHECK_PROMPT_RULE

logger = logging.getLogger(__name__)


def _unverified_physics_note() -> str:
    return (
        "Physics note: a physics request was detected, but no complete verified "
        "solver result is available. Do not claim verification or drop units. "
        "Still finish under Answer with the result and units in inline math. "
        "Never end on the Answer heading. If there is no unique result, say "
        "what is missing instead of leaving Answer blank. Do not emit answer, "
        "graph, or simulation fences.\n\n"
        f"{PHYSICS_REPLY_POLICY} {PHYSICS_WORKOUT_PARTS_PROMPT}\n\n"
        "No verified numbers were produced for this request, so the copy-verified "
        "rule does not apply. Compute the result and write it under Answer. "
        f"{SELF_CHECK_PROMPT_RULE}"
    )


PhysicsOutcome = Literal["skip", "note", "failed", "symbolic", "verified", "picture"]


def solve_physics_request(
    user_content: str, settings: Settings, needs_subject: bool | None
) -> tuple[PhysicsOutcome, VerifiedPhysicsBlock | None]:
    """Read a physics request and solve it, in the SymPy pool (never on the event loop).

    ``skip``: not physics. ``note``: physics with no template, so the prompt note.
    ``failed``: a template matched and its solve failed. ``symbolic`` and ``verified``
    carry the block; ``picture`` carries a free-body diagram and no result ("draw the
    forces on a box on a 30° incline" names no mass and no μ).
    """
    detected = needs_physics(user_content) if needs_subject is None else needs_subject
    if not detected:
        return "skip", None
    from app.modules.physics.symbolic.request import (
        is_symbolic_physics_request,
        parse_symbolic_physics_request,
    )

    if is_symbolic_physics_request(user_content):
        request = parse_symbolic_physics_request(user_content)
        if request is None:
            return "note", None
        from app.modules.physics.symbolic.solver import build_symbolic_physics_block

        try:
            return "symbolic", build_symbolic_physics_block(request, user_content)
        except Exception:
            logger.info("symbolic physics model declined", exc_info=True)
            return "failed", None
    intent = extract_physics_intent(user_content)
    block: VerifiedPhysicsBlock | None = None
    if intent is not None:
        try:
            block = _build_physics_block(intent, settings, [])
        except Exception:
            logger.warning("physics solve failed for kind=%s", intent.kind, exc_info=True)
    # A question in parts the solve answered one part of: every part, or that one.
    if block is None or (len(block.physics_parts) < 2 and asks_count(user_content) > 1):
        block = solve_in_parts(user_content, settings) or block
    if block is None:
        return _picture_or(user_content, "note" if intent is None else "failed")
    return "verified", replace(block, text=wrap_verified_physics(block.text))


def _picture_or(
    user_content: str, outcome: PhysicsOutcome
) -> tuple[PhysicsOutcome, VerifiedPhysicsBlock | None]:
    """Nothing solved, but the forces it asks to see can still be drawn."""
    from app.modules.physics.force_pictures import force_picture_block

    block = force_picture_block(user_content)
    return ("picture", block) if block is not None else (outcome, None)


async def build_physics_augmentation(
    user_content: str,
    settings: Settings,
    *,
    needs_subject: bool | None = None,
) -> tuple[str | None, VerifiedPhysicsBlock | None, bool]:
    """Build physics context without passing through math extraction or blocks.

    The third value is true only when a matching template was solved and that
    solve failed. A physics question with no template still gets the prompt
    note, and it is not reported as a failed check.
    """
    if not settings.math_tools_enabled:
        return None, None, False
    from app.core.sympy_executor import run_sympy

    try:
        outcome, block = await run_sympy(
            solve_physics_request,
            user_content,
            settings,
            needs_subject,
            timeout=settings.stem_solve_timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "physics read and solve timed out after %ss", settings.stem_solve_timeout_seconds
        )
        return _unverified_physics_note(), None, True
    except Exception:
        logger.warning("physics read and solve failed", exc_info=True)
        return _unverified_physics_note(), None, True
    if outcome == "skip":
        return None, None, False
    if outcome == "note":
        return _unverified_physics_note(), None, False
    if outcome == "picture" and block is not None:
        return block.text, block, False
    if block is None:
        return _unverified_physics_note(), None, True
    return f"{block.text}\n\n{PHYSICS_REPLY_POLICY}", block, False
