"""Verified-solve primitives shared by every subject that solves and verifies
homework (math, physics, and any solver-backed subject after them).

This module deliberately holds no subject's business logic — no equation
solving, no physics formulas, no chemistry stoichiometry. It holds only the
vocabulary subjects use to hand a verified result to the chat turn: the
subjects' names, the error a solve raises when it declines, the block that
carries a verified answer (plus optional fence/trajectory data) into the system
prompt, and what a subject's solve returns (``SubjectAugmentation``).

Math and physics both import from here directly instead of one importing
through the other's package — see docs/SUBJECT_SEPARATION_TICKETS.md (S2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.services.workout import GIVEN

# TYPE_CHECKING only: `math.solve` imports `SolveServiceError` from this module
# (see below), so a real import of `math.solve.key_steps` here — which would
# run `math/solve/__init__.py` first, like any submodule import does — would
# cycle straight back before this module finishes defining that name. Every
# use of KeyStep below is an annotation (`from __future__ import annotations`
# makes them lazy strings), so no runtime import is needed at all.
if TYPE_CHECKING:
    from app.modules.math.response_intent import MathResponseIntent
    from app.modules.math.schemas import GeometryRequest, NewtonMethodInput, NewtonMethodResult
    from app.modules.math.solve.key_steps import KeyStep
    from app.modules.physics.schemas import PhysicsIntent
    from app.modules.physics.schemas.symbolic import SymbolicPhysicsRequest

# The subjects a turn is solved by. The subject registry (``services/subjects/registry``)
# holds one adapter per name; the name is here, beside the block each subject hands back,
# because every subject's block names it and the registry imports the subjects.
SubjectName = Literal["math", "physics", "chemistry"]

VERIFIED_MATH_BEGIN = "[BEGIN VERIFIED MATH]"
VERIFIED_MATH_END = "[END VERIFIED MATH]"
VERIFIED_PHYSICS_BEGIN = "[BEGIN VERIFIED PHYSICS]"
VERIFIED_PHYSICS_END = "[END VERIFIED PHYSICS]"
_VERIFIED_MARKERS = (
    VERIFIED_MATH_BEGIN,
    VERIFIED_MATH_END,
    VERIFIED_PHYSICS_BEGIN,
    VERIFIED_PHYSICS_END,
)


class SolveServiceError(ValueError):
    """A deterministic subject solve declined invalid or unsupported input."""


@dataclass(frozen=True)
class VerifiedSolveBlock:
    """Subject-neutral transport for one deterministic, verified solve.

    Subject algorithms own extraction, solving, traces, and presentation.
    Chat owns only this canonical transport: prompt text, exact result fences,
    and optional subject-rendered direct output.  Subject-specific state lives
    on the subclasses below rather than turning math into physics' container.

    ``canonical_fences`` collects fences across multiple tool-loop rounds
    (e.g. a geometry fence from round 1 and a graph fence from round 2) so
    ``validate_math_fences`` can match each by type instead of only using
    the last round's fence. ``canonical_fence`` stays the primary/first for
    backward compatibility."""

    text: str
    subject: SubjectName
    canonical_fence: dict[str, Any] | None = None
    canonical_answer: str | None = None
    # Optional user-facing spelling of the same verified value. Geometry uses
    # this to retain a numeric canonical value for guards while showing the
    # correct linear/square unit in the checked answer card.
    display_answer: str | None = None
    canonical_fences: list[dict[str, Any]] = field(default_factory=list)
    # Some results need language around the canonical data; closed requests
    # may return a subject-rendered reply without asking a model to recalculate.
    allow_direct: bool = True
    direct_reply: str | None = None
    direct_request_text: str | None = None
    direct_answer_binding: str | None = None
    domain_conditions: tuple[str, ...] = ()
    excluded_values: tuple[str, ...] = ()
    # A question in parts, each part verified on its own: every part's block, in order.
    # This block (the first part's) stands for the turn; the fence check keeps each
    # part's card and pictures (``chat.finalize_subjects``).
    question_parts: tuple[VerifiedSolveBlock, ...] = ()


@dataclass(frozen=True)
class VerifiedMathBlock(VerifiedSolveBlock):
    """Math-only verified state and deterministic teaching traces."""

    subject: Literal["math"] = "math"
    # Ordered inverse-operation (or factor / formula) trace for equation lessons.
    key_steps: tuple[KeyStep, ...] = ()
    given_latex: str | None = None
    # Which section holds the problem line: GIVEN for an equation; REQUIRED when the
    # problem line is the question itself (a derivative or an integral to evaluate).
    given_label: str = GIVEN
    check_latex: str | None = None
    alternate_method_note: str | None = None
    # The worked layout for a closed result (formula, then substitution). Unlike
    # ``direct_reply`` it is shown only after every direct-reply guard passes,
    # so "and explain why" still reaches the model.
    worked_reply: str | None = None
    # Paired snapshots of the actual Newton solve; never reconstruct iterations.
    newton_input: NewtonMethodInput | None = None
    newton_result: NewtonMethodResult | None = None
    # Standard derivatives/integrals additionally use the strict calculus
    # whole-request grammar; calculus applications have their own extractors
    # and therefore leave this false.
    direct_requires_calculus_guard: bool = False
    # Presentation is classified once for the turn, then enforced by direct
    # routing, prompt guidance, and final fence attachment. In particular,
    # ``reveal_answer=False`` is a hard policy boundary for tutoring hints.
    response_intent: MathResponseIntent | None = None
    # What the question asked, copied from the intent so presentation never
    # reads the question again. Server-side only: no reply or record holds it.
    geometry_request: GeometryRequest | None = None
    plot_point: tuple[float, float] | None = None


@dataclass(frozen=True)
class PhysicsPartWorking:
    """One part of a physics question in parts, worked and answered on its own."""

    op: str
    symbol: str
    title: str
    formulas: tuple[str, ...]
    substitutions: tuple[str, ...]
    # Its own card: the value alone, as plain text and as LaTeX.
    answer: str
    display_answer: str


@dataclass(frozen=True)
class VerifiedPhysicsBlock(VerifiedSolveBlock):
    """Physics-only verified state used by physics presentation guards."""

    subject: Literal["physics"] = "physics"
    physics_intent: PhysicsIntent | None = None
    physics_working: str | None = None
    physics_formulas: tuple[str, ...] = ()
    physics_substitutions: tuple[str, ...] = ()
    # A question in parts: each part's working and card, in the order asked.
    physics_parts: tuple[PhysicsPartWorking, ...] = ()
    symbolic_request: SymbolicPhysicsRequest | None = None


@dataclass(frozen=True)
class SubjectAugmentation:
    """What a subject's solve hands the turn (``services/subjects/registry``)."""

    subject: SubjectName | None
    prompt_block: str | None
    verified: VerifiedSolveBlock | None
    unverified: bool = False
    # Both halves of "…, and also …", or each question of a problem in parts, already
    # rendered. Chat shows this and does not ask the model to redo any of them.
    direct_text: str | None = None


def wrap_verified_math(text: str) -> str:
    body = text.strip()
    if VERIFIED_MATH_BEGIN in body or VERIFIED_PHYSICS_BEGIN in body:
        return body
    return f"{VERIFIED_MATH_BEGIN}\n{body}\n{VERIFIED_MATH_END}"


def wrap_verified_physics(text: str) -> str:
    body = text.strip()
    if VERIFIED_PHYSICS_BEGIN in body or VERIFIED_MATH_BEGIN in body:
        return body
    return f"{VERIFIED_PHYSICS_BEGIN}\n{body}\n{VERIFIED_PHYSICS_END}"


def strip_verified_solve_markers(text: str) -> str:
    """Remove the verified-math sentinels if a model echoed them into its reply.

    ``wrap_verified_math`` puts these around the block injected into the
    prompt. They are scaffolding: the model is told never to mention a system
    block, but instruction is not enforcement, and the same class of leak has
    already reached a user once (the SymPy note under an anatomy answer).

    The text *between* the markers is kept. A model that echoed the block
    usually put the real answer inside it, and an empty reply is worse than a
    slightly formal one — stripping the scaffolding is enough to make it read
    as prose. Blank runs left behind are collapsed so removing a marker that
    sat on its own line does not leave a gap.
    """
    if not any(marker in text for marker in _VERIFIED_MARKERS):
        return text
    stripped = text
    for marker in _VERIFIED_MARKERS:
        stripped = stripped.replace(marker, "")
    return re.sub(r"\n{3,}", "\n\n", stripped).strip()
